/** QEMU-only transport setup. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#pragma once
#include <Uefi.h>

EFI_STATUS ConnectProvider (EFI_HANDLE Image, EFI_HANDLE Esp, CHAR16 *Name, EFI_GUID *Input);
