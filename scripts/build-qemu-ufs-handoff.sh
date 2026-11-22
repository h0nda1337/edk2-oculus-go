#!/usr/bin/env bash
# Build the QEMU-only idle task-list model alongside the distribution binary.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "usage: $0 /path/to/qemu-10.0.13.tar.xz /path/to/work-directory" >&2
  exit 2
fi
# Use Linux headers and libraries when running under WSL.
export PATH=$(getconf PATH)
repo=$(cd "$(dirname "$0")/.." && pwd)
archive=$(realpath "$1")
mkdir -p "$2"
work=$(cd "$2" && pwd)
src="$work/qemu-10.0.13"
patchfile="$repo/tests/qemu/ufs-idle-task-list-10.0.13.patch"
printf '%s  %s\n' 4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa "$archive" | sha256sum -c -
if [[ ! -d "$src" ]]; then
  tar -xf "$archive" -C "$work"
fi
stock=de7a763215a8ea4082f78be1cc626e44cfd152a474112a28a1886ccabf21353f
if [[ $(sha256sum "$src/hw/ufs/ufs.c" | cut -d' ' -f1) == "$stock" ]]; then
  patch --batch --forward --fuzz=0 -d "$src" -p1 < "$patchfile"
fi
printf '%s  %s\n' 1c806576ada8f5277a7ccb2ace1777307ac1376d998e9e1001485cf7e13b287f "$src/hw/ufs/ufs.c" | sha256sum -c -
cp "$repo/tests/qemu/ufs-virt.mak" "$src/configs/devices/aarch64-softmmu/ufs-virt.mak"
mkdir -p "$work/build"
cd "$work/build"
"$src/configure" --prefix=/usr --target-list=aarch64-softmmu --disable-docs \
  --disable-tools --disable-guest-agent --disable-werror --disable-debug-info \
  --disable-sdl --disable-gtk --disable-curses --disable-opengl --disable-vnc \
  --without-default-devices --with-devices-aarch64=ufs-virt --enable-trace-backends=log
ninja -j "${JOBS:-18}" qemu-system-aarch64
"$work/build/qemu-system-aarch64" --version
