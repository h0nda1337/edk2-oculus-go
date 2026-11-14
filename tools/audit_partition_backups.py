"""Verify local partition backups without running a device tool or writing files.

Only emit checksums/size agreement and coarse container identification.
Nothing in this tool verifies signatures, fuses, or the live boot policy.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat


def file_format(prefix):
    if prefix.startswith(b'ANDROID!'):
        return 'android-boot-magic'
    if prefix.startswith(b'\x7fELF') and len(prefix) >= 6 and prefix[5] in (1, 2):
        return {1: 'elf32-magic', 2: 'elf64-magic'}.get(prefix[4], 'unclassified')
    if prefix[1080:1082] == b'\x53\xef':
        return 'ext-superblock-magic-at-standard-offset'
    return 'unclassified'


def validated_records(records):
    if not isinstance(records, list) or not records:
        raise ValueError('Inventory must contain a nonempty partition list')
    result = {}
    for row in records:
        name = row['name']
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]+', name) or name in result:
            raise ValueError('Inventory contains an invalid or duplicate name')
        if type(row['size']) is not int or row['size'] <= 0:
            raise ValueError('Invalid inventory size')
        if not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid inventory SHA-256')
        result[name] = row
    return result


def inspect_backup(folder, name, expected):
    result = {'name': name}
    try:
        path = folder / f'{name}.img'
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.resolve().parent != folder:
            return {**result, 'status': 'NOT-A-LOCAL-REGULAR-FILE'}
        if info.st_size != expected['size']:
            return {**result, 'status': 'SIZE-MISMATCH', 'size': info.st_size}
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            prefix = stream.read(min(expected['size'], 4096))
            digest.update(prefix)
            size = len(prefix)
            # Bound streaming reads even if a file changes after lstat.
            while size <= expected['size']:
                chunk = stream.read(min(8 * 1024 * 1024, expected['size'] + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
    except FileNotFoundError:
        return {**result, 'status': 'MISSING'}
    except OSError:
        return {**result, 'status': 'UNREADABLE'}
    if size != expected['size']:
        return {**result, 'status': 'SIZE-MISMATCH', 'size': size}
    actual_hash = digest.hexdigest()
    if actual_hash != expected['sha256']:
        return {**result, 'status': 'HASH-MISMATCH', 'size': size, 'sha256': actual_hash}
    return {**result, 'status': 'MATCH', 'size': size, 'sha256': actual_hash,
            'format_hint': file_format(prefix)}


def audit(folder, inventory):
    rows = validated_records(json.loads(inventory.decode('utf-8-sig'))['partitions'])
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Backup directory is not a folder')
    results = [inspect_backup(folder, name, rows[name]) for name in sorted(rows)]
    matches = [record for record in results if record['status'] == 'MATCH']
    return {'scope': 'local-backup-integrity-and-format-hints-only',
            'result': 'PASS' if len(matches) == len(rows) else 'FAIL',
            'inventory_sha256': hashlib.sha256(inventory).hexdigest(),
            'expected_count': len(rows), 'matched_count': len(matches),
            'matched_bytes': sum(row['size'] for row in matches), 'partitions': results,
            'signature_verification_performed': False, 'device_contacted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--inventory', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'docs/evidence/partitions.json')
    args = parser.parse_args(argv)
    try:
        result = audit(args.backup_dir, args.inventory.read_bytes())
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(2, 'error: missing backup directory or invalid inventory\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
