"""Audit resolved EDK2 compiler dependencies against the two allowed roots.

Run under the same Linux/WSL environment as the build so absolute dependency
paths resolve correctly. Records hashes, not just repository names.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = args.build.resolve()
    if not build.is_relative_to(root / 'Build'):
        raise SystemExit('Expected a build beneath this workspace')
    paths = set()
    lists = sorted(build.rglob('deps.txt'))
    if not lists:
        raise SystemExit('No compiler dependency lists found')
    for listing in lists:
        for text in listing.read_text().splitlines():
            if text.strip():
                paths.add(Path(text.strip()).resolve())
    records = []
    rejected = []
    for path in sorted(paths):
        if path.is_relative_to(root / 'edk2'):
            origin = 'upstream-edk2'
        elif path.is_relative_to(root / 'OculusGoPkg'):
            origin = 'original-project'
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
    lock = json.loads((root / 'sources.lock.json').read_text())
    result = {'result': 'FAIL' if rejected else 'PASS', 'edk2': lock['edk2'],
        'dependencyLists': len(lists), 'files': records, 'rejected': rejected,
        'scope': 'resolved compiler dependency lists; does not prove physical behavior'}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    counts = {kind: sum(r['origin'] == kind for r in records)
              for kind in ('original-project', 'upstream-edk2', 'edk2-generated')}
    print(json.dumps({'result': result['result'], 'counts': counts,
        'dependencyLists': len(lists), 'rejected': rejected}, indent=2))
    if rejected:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
