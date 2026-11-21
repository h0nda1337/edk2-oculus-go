#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-2-Clause-Patent
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
mkdir -p build/tests
gcc -std=c11 -fshort-wchar -DMDEPKG_NDEBUG -Wall -Wextra -Werror \
  -Wno-unused-parameter -Iedk2/MdePkg/Include -Iedk2/MdePkg/Include/X64 \
  -IOculusGoPkg/Include tests/trustmebro_host.c -o build/tests/trustmebro_host
build/tests/trustmebro_host
console=OculusGoPkg/Drivers/InheritedGopDxe
gcc -std=c11 -fshort-wchar -DMDEPKG_NDEBUG -Wall -Wextra -Werror -Wno-unused-parameter \
  -Iedk2/MdePkg/Include -Iedk2/MdePkg/Include/X64 -IOculusGoPkg/Include -I"$console" \
  tests/text_console_host.c "$console/TextConsole.c" -o build/tests/text_console_host
build/tests/text_console_host
python3 -m unittest discover -s tests -p 'test_*.py' -v
