"""Audit resolved EDK2 compiler dependencies against the two allowed roots.

Accepts Linux/WSL paths and, on Windows, resolves WSL /mnt/<drive> paths to
their native equivalents. Records hashes, tracked-input and clean-tree checks.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def host_path(text):
    match = re.match(r'^/mnt/([a-z])/(.*)$', str(text)) if os.name == 'nt' else None
    return Path(f'{match[1]}:/{match[2]}' if match else text).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, help='EDK2 build report for this invocation')
    parser.add_argument('--ufs-inf', type=Path, help='active staged INF used by this Shell build')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = host_path(args.build)
    if not build.is_relative_to(root / 'Build'):
        raise SystemExit('Expected a build beneath this workspace')
    lock = json.loads((root / 'sources.lock.json').read_text())
    git = shutil.which('git')
    repository = str(root / 'edk2')
    if os.name != 'nt' and shutil.which('git.exe') and shutil.which('wslpath'):
        git = shutil.which('git.exe')
        repository = subprocess.check_output(['wslpath', '-w', repository], text=True).strip()

    def git_output(*arguments):
        return subprocess.check_output([git, '-C', repository, *arguments],
                                       text=True, encoding='utf-8').strip()

    if git_output('rev-parse', 'HEAD') != lock['edk2']['commit']:
        raise SystemExit('EDK2 commit mismatch')
    if git_output('remote', 'get-url', 'origin') != lock['edk2']['url']:
        raise SystemExit('EDK2 upstream URL mismatch')
    if subprocess.run([git, '-C', repository, 'diff', '--quiet', 'HEAD', '--']).returncode:
        raise SystemExit('EDK2 tracked source changes found')
    tracked = set(git_output('ls-files', '-z').split('\0'))
    paths = set()
    transport_root = (root / 'build/ufs-transport').resolve()
    transport = None
    if args.ufs_inf:
        stage_tool = [sys.executable, str(root / 'tools/stage_ufs_transport.py'), '--verify-only']
        inf = subprocess.check_output(stage_tool, text=True, cwd=root).strip()
        staged_inf = (root / inf).resolve()
        if staged_inf != (root / args.ufs_inf).resolve() or args.report is None:
            raise SystemExit('Active UFS module differs from the verified lock or lacks a build report')
        # BuildReport wraps long INF paths at a directory separator. File GUID
        # is the next field of the module summary, including on Windows.
        fields = re.findall(r'^Module INF Path:[ \t]*(.*?)\nFile GUID:',
                            args.report.read_text(), re.M | re.S)
        reported = [''.join(value.splitlines()).strip() for value in fields]
        ufs_modules = [(root / item).resolve() for item in reported
                       if Path(item).name == 'UfsPassThruDxe.inf']
        if ufs_modules != [staged_inf]:
            raise SystemExit(f'Unexpected UFS module(s) in build report: {ufs_modules}')
        transport = staged_inf.parent

    # Cached outputs from previous recipes can share the platform target dir.
    # Verify the module selected by this build and reject links to older recipes.
    transport_outputs = build / 'AARCH64/build/ufs-transport'
    active_outputs = (build / 'AARCH64' / transport.relative_to(root)) if transport else None

    def obsolete_module(path):
        return (path.is_relative_to(transport_outputs) and active_outputs is not None
                and not path.is_relative_to(active_outputs))

    lists = sorted(path for path in build.rglob('deps.txt') if not obsolete_module(path))
    if transport and not any(path.is_relative_to(active_outputs) for path in lists):
        raise SystemExit('Missing dependency list for the selected UFS module')
    if not lists:
        raise SystemExit('No compiler dependency lists found')
    for listing in lists:
        for text in listing.read_text().splitlines():
            if text.strip():
                paths.add(text.strip())
    input_paths = {host_path(text) for text in paths}
    archives = set()
    for listing in build.rglob('static_library_files.lst'):
        if obsolete_module(listing):
            continue
        for text in listing.read_text().splitlines():
            if text.strip():
                archives.add(text.strip())
    # The fixed EDK2 GCC5 link flags additionally search this upstream archive.
    archives.add(str(root / 'edk2/ArmPkg/Library/GccLto/liblto-aarch64.a'))
    records = []
    rejected = []
    # Resolve each distinct input once; the same EDK2 header occurs in many
    # module lists and repeated drvfs symlink checks are particularly costly.
    for path in sorted(input_paths | {host_path(text) for text in archives}):
        if path.is_relative_to(root / 'edk2'):
            origin = 'upstream-edk2'
            if path.relative_to(root / 'edk2').as_posix() not in tracked:
                rejected.append(str(path))
                continue
        elif path == root / 'OculusGoPkg/Include/third-party/edk2/ConsoleFont.h':
            origin = 'adapted-edk2-font'
        elif path.is_relative_to(root / 'OculusGoPkg'):
            origin = 'original-project'
        elif transport is not None and path.is_relative_to(transport):
            origin = 'adapted-edk2-ufs'
        elif path.is_relative_to(transport_root) or obsolete_module(path):
            rejected.append(str(path))
            continue
        elif path.is_relative_to(build):
            origin = 'edk2-generated'
        else:
            rejected.append(str(path))
            continue
        if not path.is_file():
            rejected.append(str(path))
            continue
        records.append({'file': path.relative_to(root).as_posix(), 'origin': origin,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {'result': 'FAIL' if rejected else 'PASS', 'edk2': lock['edk2'],
        'upstreamTreeClean': True, 'upstreamInputsTracked': not rejected,
        'dependencyLists': len(lists), 'linkArchives': len(archives),
        'files': records, 'rejected': rejected,
        'scope': 'compiler dependency lists and static link archives; not physical behavior'}
    records.sort(key=lambda record: record['file'])
    host_path(args.output).write_text(json.dumps(result, indent=2) + '\n',
                                     encoding='utf-8', newline='\n')
    counts = {kind: sum(r['origin'] == kind for r in records)
              for kind in ('original-project', 'upstream-edk2', 'edk2-generated', 'adapted-edk2-font', 'adapted-edk2-ufs')}
    print(json.dumps({'result': result['result'], 'counts': counts,
        'dependencyLists': len(lists), 'rejected': rejected}, indent=2))
    if rejected:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
