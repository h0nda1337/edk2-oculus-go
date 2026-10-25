"""Import only backup metadata, never partition contents or host/device IDs.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
raw = args.manifest.read_bytes()
records = json.loads(raw.decode('utf-8-sig'))
rows = []
seen = set()
for record in records:
    name = record['Name']
    if not re.fullmatch(r'[a-z0-9_]+', name) or name in seen:
        raise SystemExit('Unexpected or duplicate partition name')
    seen.add(name)
    if not re.fullmatch(r'/dev/block/sd[a-z][0-9]+', record['BlockDevice']):
        raise SystemExit('Unexpected block path')
    if not re.fullmatch(r'[a-f0-9]{64}', record['Sha256']):
        raise SystemExit('Invalid dump hash')
    if not isinstance(record['SizeBytes'], int) or record['SizeBytes'] <= 0:
        raise SystemExit('Invalid dump size')
    rows.append({'name': name, 'blockDevice': record['BlockDevice'],
        'size': record['SizeBytes'], 'sha256': record['Sha256'], 'modify': False})
result = {'scope': 'historical backup metadata; no new device reads or dump rehash',
    'sourceManifestSha256': hashlib.sha256(raw).hexdigest(),
    'partitions': sorted(rows, key=lambda r: r['name'])}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
print(f'Imported metadata for {len(rows)} existing dumps; no binary contents')
