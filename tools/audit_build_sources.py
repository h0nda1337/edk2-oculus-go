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


def host_path(text):
    match = re.match(r'^/mnt/([a-z])/(.*)$', str(text)) if os.name == 'nt' else None
    return Path(f'{match[1]}:/{match[2]}' if match else text).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
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
    lists = sorted(build.rglob('deps.txt'))
    if not lists:
        raise SystemExit('No compiler dependency lists found')
    for listing in lists:
        for text in listing.read_text().splitlines():
            if text.strip():
                paths.add(text.strip())
    archives = set()
    for listing in build.rglob('static_library_files.lst'):
        for text in listing.read_text().splitlines():
            if text.strip():
                archives.add(text.strip())
    # The fixed EDK2 GCC5 link flags additionally search this upstream archive.
    archives.add(str(root / 'edk2/ArmPkg/Library/GccLto/liblto-aarch64.a'))
    records = []
    rejected = []
    # Resolve each distinct input once; the same EDK2 header occurs in many
    # module lists and repeated drvfs symlink checks are particularly costly.
    for path in sorted({host_path(text) for text in paths | archives}):
        if path.is_relative_to(root / 'edk2'):
            origin = 'upstream-edk2'
            if path.relative_to(root / 'edk2').as_posix() not in tracked:
                rejected.append(str(path))
                continue
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
    result = {'result': 'FAIL' if rejected else 'PASS', 'edk2': lock['edk2'],
        'upstreamTreeClean': True, 'upstreamInputsTracked': not rejected,
        'dependencyLists': len(lists), 'linkArchives': len(archives),
        'files': records, 'rejected': rejected,
        'scope': 'compiler dependency lists and static link archives; not physical behavior'}
    records.sort(key=lambda record: record['file'])
    host_path(args.output).write_text(json.dumps(result, indent=2) + '\n',
                                     encoding='utf-8', newline='\n')
    counts = {kind: sum(r['origin'] == kind for r in records)
              for kind in ('original-project', 'upstream-edk2', 'edk2-generated')}
    print(json.dumps({'result': result['result'], 'counts': counts,
        'dependencyLists': len(lists), 'rejected': rejected}, indent=2))
    if rejected:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
