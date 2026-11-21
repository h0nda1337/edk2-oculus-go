"""Run the terminal SEC_MEM FD on QEMU virt with observable guest RAM.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from emulate_entry import Remote
from emulate_sec_handoff import symbols
from sec_c_qemu import GUARD, RAM_START, until
from verify_fd import BASE, SIZE, verify
from verify_sec_visual_data import FB_BASE, SURFACE_BYTES, band_ranges


FDT = 0x82000000
FDT_LIMIT = 512 * 1024
POOL, POOL_END = 0x94000000, 0x98000000
SAMPLES = (POOL, POOL_END - 96)
ARENA, ARENA_END = BASE + 0x200, BASE + 0x800
STACK_TOP = BASE + 0x1000
RUNTIME_SHA = '0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929'
SYMBOLS = ('_ModuleEntryPoint', 'HobConstructor', 'SecMemFdtReturn', 'SecMemHobReturn',
           'SecMemValidateHob', 'SecMemPoolRead', 'SecMemStackRead', 'SecMemPaint',
           'SecMemComplete', 'SecMemEntryRejected', 'SecMemFdtRejected', 'SecMemHobRejected',
           'SecMemException', 'SecMemVectors')
ENTRY_REJECTS = ('relocated', 'dcache', 'wrong-x0', 'mmu-el1')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixtures(capture):
    # The only real blob is a previous Android snapshot supplied locally.
    # The other trees are reproducible inputs with no unit-specific data.
    source = """
/dts-v1/;
{reserve}
/ {{
    #address-cells = <2>;
    #size-cells = <2>;
    memory@80000000 {{
        device_type = "memory";
        reg = <0 0x80000000 0 {size}>;
    }};
    reserved-memory {{
        #address-cells = <2>;
        #size-cells = <2>;
        ranges;
        {child}
    }};
}};
"""
    trees = {}
    for name in ('valid-fdt', 'short-ram', 'reserved-pool', 'reserved-stack'):
        text = source.format(reserve='/memreserve/ 0x97ffffa0 8;' if name == 'reserved-stack' else '',
                             child='test@94000000 { reg = <0 0x94000000 0 8>; };'
                             if name == 'reserved-pool' else '',
                             size='0x10000000' if name == 'short-ram' else '0xbeac0000')
        trees[name] = subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb'],
                                     input=text.encode(), capture_output=True, check=True).stdout
    trees['bad-magic'] = bytes(4) + trees['valid-fdt'][4:]
    if capture is not None:
        tree = capture.read_bytes()
        require(len(tree) <= FDT_LIMIT and digest(tree) == RUNTIME_SHA,
                'Unexpected archived runtime FDT')
        trees['captured-fdt'] = tree
    return trees


def expected_screen(initial):
    cyan, yellow, white = bytes.fromhex('ffff00'), bytes.fromhex('00ffff'), b'\xff' * 3
    band = b''.join(color * 288 for color in (cyan, yellow, white, yellow, cyan)) * 32
    expected = bytearray(initial)
    for first, end in band_ranges():
        require(len(band) == end - first, 'Marker geometry does not match the measured bands')
        start = GUARD + first - FB_BASE
        expected[start:start + len(band)] = band
    return expected


def expect_hob(remote):
    raw = remote.read(ARENA, 64)
    # Two PI HOBs: PHIT with five 64-bit addresses, followed by the end node.
    expected = struct.pack('<HHIII5QHHI', 1, 56, 0, 9, 0, ARENA_END, ARENA,
                           ARENA_END, ARENA + 64, ARENA + 56, 0xffff, 8, 0)
    require(raw == expected, 'PI handoff table or end-of-list marker differs')


def check_vectors(fd, sym):
    base, handler = sym['SecMemVectors'], sym['SecMemException']
    require(base % 2048 == 0 and BASE <= base <= BASE + len(fd) - 2048,
            f'Physical VBAR is not a complete 2048-aligned table in this FD: {base:#x}')
    for slot in range(16):
        pc = base + slot * 128
        word, = struct.unpack_from('<I', fd, pc - BASE)
        imm = word & 0x03ffffff
        if imm & 0x02000000:
            imm -= 0x04000000
        require(word >> 26 == 0x5 and pc + imm * 4 == handler,
                f'Bad physical exception vector {slot} at {pc:#x}')
    return {'address': hex(base), 'handler': hex(handler), 'slotsVerified': 16}


def watch(remote, kind, start, end, enabled=True):
    cmd = 'Z' if enabled else 'z'
    require(remote.command(f'{cmd}{kind},{start:x},{end-start:x}') == 'OK',
            f'Cannot configure QEMU watchpoint for {start:#x}..{end:#x}')


def observe_load(remote, address, label, pool_data):
    # A read watchpoint covers the *whole* 64 MiB pool and stops before access.
    # QEMU reports its watchpoint base on some versions. Decode the concrete
    # instruction and effective address at the stop instead of trusting the RSP address.
    stop = remote.command('c')
    require('rwatch:' in stop and remote.register(32) == label,
            f'Unexpected high-memory access at {remote.register(32):#x}, expected {label:#x}')
    word, = struct.unpack('<I', remote.read(label, 4))
    require(word & 0xffc00000 == 0xf9400000, 'Expected one unsigned-offset 64-bit LDR')
    rn, rt, imm = (word >> 5) & 31, word & 31, (word >> 10) & 0xfff
    effective = remote.register(rn) + imm * 8
    require(rt < 31 and effective == address, f'Unexpected LDR register or address {effective:#x}')
    watch(remote, 3, POOL, POOL_END, False)
    step = remote.command('s')
    require(step.startswith(('T', 'S')) and remote.register(32) == label + 4, 'LDR did not retire')
    value, = struct.unpack_from('<Q', pool_data, address - POOL)
    require(remote.register(rt) == value, 'Loaded u64 differs from the synthetic model bytes')
    watch(remote, 3, POOL, POOL_END)
    return hex(effective)


def exercise(remote, ram, fd, sym, el, scenario, tree, pool):
    load = BASE + (0x100000 if scenario == 'relocated' else 0)
    shift = load - BASE
    fd_offset = load - RAM_START
    screen_offset = FB_BASE - GUARD - RAM_START
    screen = b'\xa5' * (SURFACE_BYTES + 2 * GUARD)
    fdt_window = tree.ljust(FDT_LIMIT, b'\xcd')
    # Connecting the chardev can precede QEMU's reset/load handlers. Exchange
    # packets with its stopped vCPU before inspecting or seeding the RAM file.
    remote.command('qSupported:qXfer:features:read+')
    remote.command('qXfer:features:read:target.xml:0,fff')
    remote.command('Hg0')
    remote.command('?')
    require(os.pread(ram, SIZE, fd_offset) == fd, 'QEMU loader FD mismatch')
    for start, buf in ((POOL, pool), (FDT, fdt_window), (FB_BASE - GUARD, screen)):
        require(os.pwrite(ram, buf, start - RAM_START) == len(buf), 'Incomplete QEMU fixture')
    incoming = {0: FDT + (8 if scenario == 'wrong-x0' else 0), 1: 23, 2: 47, 3: 83,
                30: 0x55667788, 31: 0x90010000}
    remote.set_register(33, 0x3c0 | (9 if el == 2 else 5))
    for n, val in incoming.items():
        remote.set_register(n, val)
    remote.set_register(18, 4 if scenario == 'dcache' else 0)
    remote.set_register(20, load)
    remote.set_register(32, 0x41000000 + (64 if el == 2 else 0))
    until(remote, load)
    if scenario == 'mmu-el1':
        require(el == 1 and remote.register(22) & 0x1005 == 1, 'EL1 translation is not active')

    # Trap physical writes anywhere in modeled RAM except these four spans.
    # High reads get their own watchpoint, active from FD header to terminal.
    previous = RAM_START
    for first, end in sorted(((ARENA + shift, ARENA + shift + 64),
                              (ARENA_END + shift, STACK_TOP + shift), *band_ranges())):
        watch(remote, 2, previous, first)
        previous = end
    watch(remote, 2, previous, RAM_START + (2 << 30))
    watch(remote, 3, POOL, POOL_END)
    require(remote.command(f'Z1,{sym["SecMemException"]+shift:x},4') == 'OK',
            'Cannot arm exception trap')
    until(remote, sym['_ModuleEntryPoint'] + shift)
    valid = scenario in ('valid-fdt', 'captured-fdt')
    exception = scenario == 'undefined-instruction'
    hob_case = valid or exception or scenario == 'bad-phit'
    reads = []
    if scenario in ENTRY_REJECTS:
        terminal = sym['SecMemEntryRejected'] + shift
    else:
        until(remote, sym['SecMemFdtReturn'])
        if not hob_case:
            require(remote.register(0) == 0, 'Invalid FDT accepted')
            terminal = sym['SecMemFdtRejected']
        else:
            require(remote.register(0) != 0, 'Valid FDT rejected')
            until(remote, sym['HobConstructor'])
            require([remote.register(n) for n in range(4)] ==
                    [ARENA, ARENA_END-ARENA, ARENA, ARENA_END], 'Wrong HobConstructor bounds')
            until(remote, sym['SecMemValidateHob'])
            expect_hob(remote)
            if scenario == 'bad-phit':
                # Fault injection on paused model RAM only: change PHIT's version.
                remote.write(ARENA + 8, bytes(4))
            until(remote, sym['SecMemHobReturn'])
            require(bool(remote.register(0)) == (valid or exception), 'HOB validation result differs')
            if exception:
                # Redirect the model PC to a synthetic UDF #0 in the harness's
                # zero-filled RAM. Every delivered firmware instruction stays intact.
                until(remote, sym['SecMemPoolRead'])
                fault_site = 0x41002000
                require(remote.read(fault_site, 4) == bytes(4), 'Bad model UDF fixture')
                remote.set_register(32, fault_site)
                until(remote, sym['SecMemVectors'] + 0x200)  # Current EL, SPx, synchronous.
                terminal = sym['SecMemException']
            elif valid:
                for addr, name in zip(SAMPLES, ('SecMemPoolRead', 'SecMemStackRead')):
                    reads.append(observe_load(remote, addr, sym[name], pool))
                until(remote, sym['SecMemPaint'])
                terminal = sym['SecMemComplete']
            else:
                terminal = sym['SecMemHobRejected']
    if exception:
        # The permanent exception breakpoint is already armed.
        require(remote.command('c').startswith(('T', 'S')) and remote.register(32) == terminal,
                'Exception vector missed its handler')
    else:
        until(remote, terminal)
    require(remote.read(terminal, 4) == bytes.fromhex('00000014'), 'Terminal is not a self-branch')
    require(all(remote.register(n) == val for n, val in incoming.items()),
            'Incoming x0-x3, SP or LR changed')
    expected = expected_screen(screen) if valid else screen
    require(os.pread(ram, len(expected), screen_offset) == expected, 'Screen/guard mismatch')
    require(os.pread(ram, len(pool), POOL-RAM_START) == pool, '64 MiB high pool changed')
    require(os.pread(ram, len(fdt_window), FDT-RAM_START) == fdt_window, 'FDT/guard changed')
    after = os.pread(ram, SIZE, fd_offset)
    require(after[:0x200] == fd[:0x200] and after[0x240:0x800] == fd[0x240:0x800]
            and after[0x1000:] == fd[0x1000:], 'FD changed outside its private scratch')
    if scenario in ENTRY_REJECTS:
        require(after == fd, 'Rejected entry modified even the FD scratch')
    if not hob_case:
        require(after[0x200:0x240] == fd[0x200:0x240], 'Rejected FDT touched the HOB arena')
    if valid or exception:
        expect_hob(remote)
    return {'el': el, 'scenario': scenario, 'rejected': not valid, 'terminalPc': hex(terminal),
            'fdtSha256': digest(tree), 'hobVerified': valid or exception, 'highReadAddresses': reads,
            'debuggerInducedSynchronousException': exception,
            'debuggerCorruptedPhitVersion': scenario == 'bad-phit',
            'highPoolUnchanged': True, 'unexpectedCpuRamWrites': 0,
            'fullSurfaceAndGuardsMatched': True, 'fdOutsideScratchUnchanged': True,
            'fdtAndGuardsUnchanged': True, 'incomingRegistersRestored': True}


@contextmanager
def guest(fd_path, harness, el, load, extra_args=()):
    with tempfile.TemporaryFile() as memory, socket.socket() as listener:
        memory.truncate(2 << 30)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]
        ram = memory.fileno()
        cmd = ['qemu-system-aarch64', '-accel', 'tcg', '-cpu', 'cortex-a57', '-m', '2048',
               '-object', f'memory-backend-file,id=ram,size=2G,mem-path=/proc/self/fd/{ram},share=on',
               '-machine', f'virt,secure=off,virtualization={"on" if el == 2 else "off"},memory-backend=ram',
               '-S', '-nodefaults', '-display', 'none', '-serial', 'none', '-monitor', 'none',
               '-chardev', f'socket,id=debug,host=127.0.0.1,port={port},server=off',
               '-gdb', 'chardev:debug', '-device', f'loader,file={harness},addr=0x41000000,force-raw=on',
               '-device', f'loader,file={fd_path},addr={load:#x},force-raw=on', *extra_args]
        with subprocess.Popen(cmd, pass_fds=(ram,)) as process:
            try:
                stream, _ = listener.accept()
                with stream:
                    yield Remote(stream), ram
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


def run(fd_path, data, harness, sym, el, scenario, tree, pool):
    load = BASE + (0x100000 if scenario == 'relocated' else 0)
    with guest(fd_path, harness, el, load) as (remote, ram):
        return exercise(remote, ram, data, sym, el, scenario, tree, pool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--sec-elf', type=Path, required=True)
    parser.add_argument('--runtime-fdt', type=Path, help='Private archived runtime-fdt.dtb')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    data = args.fd.read_bytes()
    require(data[64:0x1000] == b'\xff' * (0x1000-64), 'Expected unused FD header page')
    info = verify(data)
    names = symbols(args.sec_elf)
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    sym = {k: bias + names[k] for k in SYMBOLS}
    vectors = check_vectors(data, sym)
    trees = fixtures(args.runtime_fdt)
    # Vary bytes across all 64 MiB, including both sampled words. Same deterministic
    # fixture is reused per case in a fresh VM, independent of the real handset.
    pool = hashlib.shake_256(b'Pacific SEC_MEM QEMU synthetic high pool').digest(POOL_END - POOL)
    cases = []
    with tempfile.TemporaryDirectory() as folder:
        harnesses = {}
        for name in ('entry_harness', 'sec_visual_mmu_el1'):
            obj, image = (Path(folder) / (name + ext) for ext in ('.o', '.bin'))
            subprocess.run(['aarch64-linux-gnu-gcc', '-c', ROOT / 'tests' / (name + '.S'),
                            '-o', obj], check=True)
            subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, image], check=True)
            harnesses[name] = image
        for el in (1, 2):
            for scenario in (*trees, *ENTRY_REJECTS, 'bad-phit', 'undefined-instruction'):
                if scenario == 'mmu-el1' and el != 1:
                    continue
                harness = harnesses['sec_visual_mmu_el1' if scenario == 'mmu-el1' else 'entry_harness']
                try:
                    result = run(args.fd.resolve(), data, harness, sym, el, scenario,
                                 trees.get(scenario, trees['valid-fdt']), pool)
                except Exception as error:
                    raise RuntimeError(f'EL{el} {scenario}: {error}') from error
                cases.append(result)
                print(f'EL{el} {scenario}: PASS', flush=True, file=sys.stderr)
    report = {'result': 'PASS-QEMU-SEC-MEM', 'fdSha256': info['sha256'],
              'elfSha256': digest(args.sec_elf.read_bytes()), 'physicalExecution': 'UNKNOWN',
              'scope': 'QEMU virt Cortex-A57 TCG guest CPU accesses and modeled RAM; no physical hardware or DMA',
              'highPoolSyntheticSha256': digest(pool), 'physicalVectorTable': vectors,
              'cases': cases}
    encoded = json.dumps(report, indent=2) + '\n'
    if args.report:
        with args.report.open('x', encoding='utf-8', newline='\n') as out:
            out.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
