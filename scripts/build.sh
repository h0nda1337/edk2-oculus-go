#!/usr/bin/env bash
# Original build entry; only project and pinned upstream EDK2 in PACKAGES_PATH.
# SPDX-License-Identifier: BSD-2-Clause-Patent
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_target=${1:-DEBUG}
jobs=${2:-4}
build_mode=${3:-NORMAL}
[[ "$build_target" == DEBUG || "$build_target" == RELEASE ]] || exit 2
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || exit 2
build_flavor=OculusGo
build_arguments=()
case "$build_mode" in
  NORMAL) ;;
  SHELL_QEMU) build_flavor=OculusGoShellQemu ;;
  SEC_VISUAL) build_flavor=OculusGoSecVisual ;;
  GOP_MODEL) build_flavor=OculusGoGopModel ;;
  SEC_C) build_flavor=OculusGoSecC ;;
  SEC_MEM) build_flavor=OculusGoSecMem ;;
  DXE_APP) build_flavor=OculusGoDxeApp ;;
  DXE_TEXT) build_flavor=OculusGoDxeText ;;
  DXE_GOP) build_flavor=OculusGoDxeGop ;;
  DXE_DISPATCH) build_flavor=OculusGoDxeDispatch ;;
  DXE_DEBUG) build_flavor=OculusGoDxeDebug ;;
  DXE_TABLES) build_flavor=OculusGoDxeTables ;;
  DXE_GCD) build_flavor=OculusGoDxeGcd ;;
  DXE_MEM) build_flavor=OculusGoDxeMem ;;
  SEC_DXE) build_flavor=OculusGoSecDxe ;;
  SEC_MMU) build_flavor=OculusGoSecMmu ;;
  UFS_DATA) build_flavor=OculusGoUfsData ;;
  UFS_BOUNCE) build_flavor=OculusGoUfsBounce ;;
  UFS_HEAP4K) build_flavor=OculusGoUfsHeap ;;
  UFS_ZERO4K) build_flavor=OculusGoUfsZero4k ;;
  UFS_BUF4K) build_flavor=OculusGoUfsBuf4k ;;
  UFS_GPT_MODEL) build_flavor=OculusGoUfsGptModel ;;
  UFS_NOP11) build_flavor=OculusGoUfsNop11 ;;
  UFS_LK_MAP) build_flavor=OculusGoUfsLkMap ;;
  UFS_QUEUES) build_flavor=OculusGoUfsQueues ;;
  UFS_HANDOFF) build_flavor=OculusGoUfsHandoff ;;
  SEC_STACK) build_flavor=OculusGoSecStack ;;
  *) echo "Unknown build mode: $build_mode" >&2; exit 2 ;;
esac
if [[ "$build_mode" != NORMAL ]]; then
  [[ "$build_target" == DEBUG ]] || { echo "$build_mode requires DEBUG" >&2; exit 2; }
  build_arguments=(-D "GO_BUILD_FLAVOR=$build_flavor")
fi
if [[ "$build_mode" == SEC_VISUAL ]]; then
  build_arguments+=(--pcd gOculusGoPkgTokenSpaceGuid.PcdSecVisualDiagnostic=TRUE)
fi
export WORKSPACE="$project_root"
export PACKAGES_PATH="$project_root/edk2:$project_root"
export EDK_TOOLS_PATH="$project_root/edk2/BaseTools"
export CONF_PATH="$project_root/Conf"
export GCC5_AARCH64_PREFIX=aarch64-linux-gnu-
export PYTHON_COMMAND=python3
export PYTHONPATH="$EDK_TOOLS_PATH/Source/Python"
export PYTHONWARNINGS=ignore::SyntaxWarning
export PATH="$project_root/scripts/wrappers:$EDK_TOOLS_PATH/Source/C/bin:$PATH"
cd "$project_root"
mkdir -p build
exec 9>build/.build.lock
flock -n 9 || { echo 'Another build is running in this workspace' >&2; exit 4; }
expected=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["edk2"]["commit"])')
git_command=(git)
git_root="$project_root/edk2"
# Git for Windows owns the checkout's index/line-ending configuration on WSL.
# Use it for the read-only source check instead of restatting through drvfs.
if command -v git.exe >/dev/null && command -v wslpath >/dev/null; then
  git_command=(git.exe)
  git_root=$(wslpath -w "$git_root")
fi
actual=$("${git_command[@]}" -C "$git_root" rev-parse HEAD | tr -d '\r')
[[ "$actual" == "$expected" ]] || { echo 'EDK2 commit mismatch' >&2; exit 3; }
"${git_command[@]}" -C "$git_root" diff --quiet HEAD -- || { echo 'EDK2 source modifications found' >&2; exit 3; }
mkdir -p "$CONF_PATH" "$project_root/logs"
for name in target tools_def build_rule; do
  [[ -f "$CONF_PATH/$name.txt" ]] || cp "$EDK_TOOLS_PATH/Conf/$name.template" "$CONF_PATH/$name.txt"
done
# No recursive submodule checkout. These targets do not require Brotli/OpenSSL.
make -C "$EDK_TOOLS_PATH/Source/C" -j"$jobs" GenFfs GenFv GenFw GenSec LzmaCompress VolInfo
chmod +x "$project_root/scripts/wrappers/Trim"
stamp=$(date -u +%Y%m%d-%H%M%S)
report_dir="$project_root/build/$build_target-$build_mode-$stamp"
mkdir -p "$report_dir"
python3 "$EDK_TOOLS_PATH/Source/Python/build/build.py" \
  -a AARCH64 -t GCC5 -b "$build_target" -p OculusGoPkg/OculusGoPkg.dsc \
  -n "$jobs" "${build_arguments[@]}" -y "$report_dir/BUILD_REPORT.txt" 2>&1 | tee "$project_root/logs/build-$stamp.log"
cp "$project_root/Build/$build_flavor/${build_target}_GCC5/FV/OCULUS_GO_DIRECT.fd" "$report_dir/"
cp "$project_root/Build/$build_flavor/${build_target}_GCC5/FV/Guid.xref" "$report_dir/"
python3 "$project_root/tools/verify_fd.py" "$report_dir/OCULUS_GO_DIRECT.fd" --report "$report_dir/VERIFY.json"
python3 "$project_root/tools/audit_build_sources.py" \
  --build "$project_root/Build/$build_flavor/${build_target}_GCC5" --output "$report_dir/SOURCES.json"
echo "Output: $report_dir"
