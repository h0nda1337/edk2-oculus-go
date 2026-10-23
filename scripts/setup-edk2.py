"""Fetch only the pinned, permitted upstream EDK2 checkout.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
source = json.loads((root / 'sources.lock.json').read_text())['edk2']
if source['url'] != 'https://github.com/tianocore/edk2.git':
    raise SystemExit('Upstream EDK2 URL must be reviewed')
dest = root / 'edk2'


def git(*arguments):
    return subprocess.check_output(['git', *map(str, arguments)], text=True).strip()


if not dest.exists():
    git('init', dest)
    git('-C', dest, 'config', 'core.autocrlf', 'false')
    git('-C', dest, 'remote', 'add', 'origin', source['url'])
    git('-C', dest, 'fetch', '--depth=1', 'origin', source['commit'])
    git('-C', dest, 'checkout', '--detach', source['commit'])
if git('-C', dest, 'remote', 'get-url', 'origin') != source['url']:
    raise SystemExit('Existing EDK2 remote mismatch')
if git('-C', dest, 'rev-parse', 'HEAD') != source['commit']:
    raise SystemExit('Existing EDK2 revision mismatch; left untouched')
if git('-C', dest, 'status', '--porcelain', '--untracked-files=no'):
    raise SystemExit('Existing EDK2 has tracked changes; left untouched')
# MdeModulePkg.dec lists this optional include directory unconditionally.
# Our target never uses Brotli. An empty directory satisfies metadata path
# validation without fetching, compiling or substituting third-party code.
(dest / 'MdeModulePkg/Library/BrotliCustomDecompressLib/brotli/c/include').mkdir(
    parents=True, exist_ok=True)
print('Pinned upstream EDK2 ready:', source['commit'])
