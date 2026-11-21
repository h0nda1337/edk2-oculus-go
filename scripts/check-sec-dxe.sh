#!/usr/bin/env bash
# Re-extract the exact Android payload and audit the SEC -> DXE candidate offline.
# SPDX-License-Identifier: BSD-2-Clause-Patent
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
out=${1:?Specify the SEC_DXE build directory}
image=${2:?Specify the matching local Android image}
python3 - "$out" "$image" <<'PY'
from pathlib import Path
import sys, zlib
sys.path.insert(0,'tools')
from android_boot import DTB_SHA, HEADER, PAGE, digest, verify_container
out=Path(sys.argv[1])
fd=(out/'OCULUS_GO_DIRECT.fd').read_bytes()
image=Path(sys.argv[2]).read_bytes()
kernel=image[PAGE:PAGE+HEADER.unpack_from(image)[1]]
decoder=zlib.decompressobj(31)
payload=decoder.decompress(kernel,len(fd)+1)
if not decoder.eof or payload!=fd or digest(decoder.unused_data)!=DTB_SHA:
    raise SystemExit('Android container does not reproduce the reviewed firmware')
verify_container(image,fd,decoder.unused_data)
(out/'container-extracted.fd').write_bytes(payload)
PY
profile=()
case "$(basename "$out")" in
  DEBUG-SEC_DXE-*) dir=Build/OculusGoSecDxe/DEBUG_GCC5 ;;
  DEBUG-DXE_TEXT-*) dir=Build/OculusGoDxeText/DEBUG_GCC5; profile=(--text --driver-pe "$dir/AARCH64/DevicePathDxe.efi" --gop-pe "$dir/AARCH64/InheritedGopDxe.efi") ;;
  DEBUG-DXE_GOP-*) dir=Build/OculusGoDxeGop/DEBUG_GCC5; profile=(--driver-pe "$dir/AARCH64/DevicePathDxe.efi" --gop-pe "$dir/AARCH64/InheritedGopDxe.efi") ;;
  DEBUG-DXE_DISPATCH-*) dir=Build/OculusGoDxeDispatch/DEBUG_GCC5; profile=(--driver-pe "$dir/AARCH64/DevicePathDxe.efi") ;;
  DEBUG-DXE_DEBUG-*) dir=Build/OculusGoDxeDebug/DEBUG_GCC5; profile=(--debug-image) ;;
  DEBUG-DXE_TABLES-*) dir=Build/OculusGoDxeTables/DEBUG_GCC5; profile=(--tables) ;;
  DEBUG-DXE_GCD-*) dir=Build/OculusGoDxeGcd/DEBUG_GCC5; profile=(--gcd) ;;
  DEBUG-DXE_MEM-*) dir=Build/OculusGoDxeMem/DEBUG_GCC5; profile=(--memory) ;;
  *) echo 'Unknown diagnostic build profile' >&2; exit 2 ;;
esac
args=("${profile[@]}" --fd "$out/container-extracted.fd" --fv "$dir/FV/FVTRIALDXE.Fv"
      --pe "$dir/AARCH64/DxeCore.efi" --sec-elf "$dir/AARCH64/OculusGoSecDxe.debug"
      --dxe-elf "$dir/AARCH64/DxeCore.debug")
trial_reports=$(mktemp -d)
reports=(STATIC.json QEMU.json)
if [[ $(basename "$out") == DEBUG-DXE_TEXT-* ]]; then
  export DXE_TEXT_CAPTURE="$trial_reports"
  reports+=(eye-el1.png eye-el2.png)
fi
trap 'for report in "${reports[@]}"; do rm -f -- "$trial_reports/$report"; done; rmdir -- "$trial_reports"' EXIT
python3 tests/sec_dxe_static.py "${args[@]}" --report "$trial_reports/STATIC.json"
python3 tests/sec_dxe_qemu.py "${args[@]}" --report "$trial_reports/QEMU.json"
for name in "${reports[@]}"; do
  if [[ -e "$out/$name" ]]; then
    cmp -- "$out/$name" "$trial_reports/$name"
  fi
done
for name in "${reports[@]}"; do
  [[ -e "$out/$name" ]] || cp -- "$trial_reports/$name" "$out/$name"
done
