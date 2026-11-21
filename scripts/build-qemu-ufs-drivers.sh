#!/usr/bin/env bash
# Build the guest application and two transport providers on the project toolchain.
# SPDX-License-Identifier: BSD-2-Clause-Patent
set -euo pipefail
cd "$(dirname "$0")/.."
export WORKSPACE="$PWD" PACKAGES_PATH="$PWD/edk2:$PWD" CONF_PATH="$PWD/build/ufs-test-conf"
export EDK_TOOLS_PATH="$PWD/edk2/BaseTools" GCC5_AARCH64_PREFIX=aarch64-linux-gnu-
export PYTHONWARNINGS=ignore::SyntaxWarning
export PYTHONPATH="$EDK_TOOLS_PATH/Source/Python" PYTHON_COMMAND=python3
export PATH="$PWD/scripts/wrappers:$EDK_TOOLS_PATH/Source/C/bin:$PATH"
mkdir -p "$CONF_PATH"
exec 9>"$CONF_PATH/.lock"
flock 9
for name in target tools_def build_rule; do
  cp "$PWD/Conf/$name.txt" "$CONF_PATH/$name.txt"
done
expected=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["edk2"]["commit"])')
source_git=(git -C "$PWD/edk2")
if command -v git.exe >/dev/null && command -v wslpath >/dev/null; then
  source_git=(git.exe -C "$(wslpath -w "$PWD/edk2")")
fi
test "$("${source_git[@]}" rev-parse HEAD | tr -d '\r')" = "$expected"
"${source_git[@]}" diff --quiet HEAD --
# Generate just this nine-file EDK2 module from the pinned checkout. Use
# canonical Git blobs independently of checkout line-ending settings.
module=MdeModulePkg/Bus/Ufs/UfsPassThruDxe
overlay=build/ufs-test-sources/UfsPassThruDxe
mkdir -p "$overlay"
git -C edk2 archive "$expected:$module" | tar -x -C "$overlay"
sed -i 's/\r$//' "$overlay/UfsPassThru.c"
patch --batch --fuzz=0 -d "$overlay" -p1 < tests/UfsSplashApp/ufs-sparse-units.patch
python3 "$EDK_TOOLS_PATH/Source/Python/build/build.py" -a AARCH64 -t GCC5 -b DEBUG \
  -p tests/UfsSplashApp/Transport.dsc -n 12
