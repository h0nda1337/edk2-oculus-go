#!/usr/bin/env python3
"""Reconstruct and verify the shared EDK2 UFS transport from Git."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE_ROOT = ROOT / "build/ufs-transport"


def tree_hashes(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"invalid module directory {directory}")
    hashes = {}
    for child in directory.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(f"unexpected module entry {child}")
        hashes[child.name] = hashlib.sha256(child.read_bytes()).hexdigest()
    return hashes


def reconstruct(directory, lock):
    edk2 = ROOT / "edk2"
    recipe = lock["ufsTransport"]
    git = ["git", "-c", f"safe.directory={edk2.as_posix()}", "-C", str(edk2)]
    tree = lock["edk2"]["commit"] + ":" + recipe["module"]
    entries = subprocess.check_output([*git, "ls-tree", tree]).decode().splitlines()
    for entry in entries:
        metadata, filename = entry.split("\t")
        mode, kind, obj = metadata.split()
        if mode != "100644" or kind != "blob" or Path(filename).name != filename:
            raise ValueError(f"unexpected upstream tree entry {entry}")
        source = subprocess.check_output([*git, "cat-file", "blob", obj])
        (directory / filename).write_bytes(source.replace(b"\r\n", b"\n"))
    # Ignore the outer checkout so git applies paths relative to this fresh module.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(directory.parent))
    for item in recipe["patches"]:
        filename, digest = item["path"], item["sha256"]
        patch = (ROOT / filename).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(patch).hexdigest() != digest:
            raise ValueError(f"patch digest mismatch: {filename}")
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", "apply", "--no-index",
             "--unidiff-zero", "--whitespace=nowarn", "-"],
            input=patch, cwd=directory, env=env, check=True,
        )


def module_path(lock):
    manifest = lock["ufsTransport"]["generatedSha256"]
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    key = hashlib.sha256(canonical).hexdigest()
    return STAGE_ROOT / key / "UfsPassThruDxe"


def stage(lock, destination, verify_only):
    expected = lock["ufsTransport"]["generatedSha256"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        module = Path(tmp) / "UfsPassThruDxe"
        module.mkdir()
        reconstruct(module, lock)
        if tree_hashes(module) != expected:
            raise ValueError("generated UFS source differs from the recorded lock")
        if not verify_only and not destination.exists():
            try:
                module.rename(destination)
            except OSError:
                # Another process may have atomically published the same module.
                if not destination.is_dir():
                    raise
        if tree_hashes(destination) != expected:
            raise ValueError(f"staged module differs from the lock: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--verify-only", action="store_true",
                       help="verify the current module and print its INF path")
    modes.add_argument("--path", action="store_true",
                       help="print the relative INF path without staging or verifying")
    try:
        args = parser.parse_args()
        lock = json.loads((ROOT / "sources.lock.json").read_bytes())
        destination = module_path(lock)
        if not args.path:
            stage(lock, destination, args.verify_only)
        print((destination / "UfsPassThruDxe.inf").relative_to(ROOT).as_posix())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"UFS staging failed: {error}") from error
