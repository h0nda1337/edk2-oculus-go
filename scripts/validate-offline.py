"""Run the complete offline validation, without ADB/Fastboot or headset access.

Run with Python on Linux/WSL. Logs/results stay in an ignored timestamped
directory. SEC/DXE validation only accepts FDs pinned by the handoff harness.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-dir', type=Path, required=True)
args = parser.parse_args()
build_dir = args.build_dir.resolve()
if not build_dir.is_relative_to(root / 'build'):
    raise SystemExit('Expected a successful build beneath this project')
fd = build_dir / 'OCULUS_GO_DIRECT.fd'
sec = root / 'Build/OculusGo/DEBUG_GCC5/AARCH64/OculusGoPkg/PrePi/PrePi/DEBUG/OculusGoSec.dll'
dxe = root / 'Build/OculusGo/DEBUG_GCC5/AARCH64/MdeModulePkg/Core/Dxe/DxeMain/DEBUG/DxeCore.dll'
for path in (fd, sec, dxe):
    if not path.is_file():
        raise SystemExit(f'Missing artifact: {path}')
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
output = root / 'build' / f'validation-{stamp}'
output.mkdir(exist_ok=False)
steps = [
    ('host', ['bash', 'scripts/test-host.sh']),
    ('fd', [sys.executable, 'tools/verify_fd.py', str(fd), '--report', str(output / 'FD.json')]),
    ('sources', [sys.executable, 'tools/audit_build_sources.py', '--build',
                 'Build/OculusGo/DEBUG_GCC5', '--output', str(output / 'SOURCES.json')]),
    ('entry', [sys.executable, 'tools/emulate_entry.py', '--fd', str(fd),
               '--output', str(output / 'entry')]),
    ('sec', [sys.executable, 'tools/emulate_sec_handoff.py', '--fd', str(fd),
             '--sec-elf', str(sec), '--output', str(output / 'sec')]),
    ('dxe', [sys.executable, 'tools/emulate_sec_handoff.py', '--fd', str(fd),
             '--sec-elf', str(sec), '--dxe-elf', str(dxe), '--output', str(output / 'dxe')]),
]
report = {'result': 'IN-PROGRESS', 'physicalExecution': 'UNKNOWN', 'deviceAccess': False,
          'fdSha256': hashlib.sha256(fd.read_bytes()).hexdigest(), 'steps': []}
failure = False
try:
    for name, command in steps:
        log = output / f'{name}.log'
        with log.open('wb') as stream:
            process = subprocess.run(command, cwd=root, stdout=stream,
                                     stderr=subprocess.STDOUT, timeout=180)
        result = {'name': name, 'exitCode': process.returncode,
                  'log': log.name, 'logSha256': hashlib.sha256(log.read_bytes()).hexdigest()}
        report['steps'].append(result)
        print(name, 'PASS' if process.returncode == 0 else 'FAIL', flush=True)
        if process.returncode:
            failure = True
            break
except Exception as error:
    failure = True
    report['error'] = str(error)
finally:
    report['result'] = 'FAIL' if failure else 'PASS'
    (output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
print('Results:', output)
raise SystemExit(1 if failure else 0)
