#!/usr/bin/env bash
# Run the text/grid integration test against the original GOP in AArch64 QEMU.
# SPDX-License-Identifier: BSD-2-Clause-Patent
set -euo pipefail
cd "$(dirname -- "$0")/.."
mkdir -p build/tests
console=OculusGoPkg/Drivers/InheritedGopDxe
aarch64-linux-gnu-gcc -std=gnu11 -O2 -static -fshort-wchar -DMDEPKG_NDEBUG \
  -Wall -Wextra -Werror -Wno-unused-parameter -Iedk2/MdePkg/Include \
  -Iedk2/MdePkg/Include/AArch64 -IOculusGoPkg/Include -I"$console" \
  tests/text_scroll_qemu.c "$console/TextConsole.c" "$console/InheritedGopDxe.c" \
  -o build/tests/text_scroll_aarch64
qemu-aarch64 build/tests/text_scroll_aarch64
