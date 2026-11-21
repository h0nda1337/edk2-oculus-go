/** Read-only access to the Pacific splash. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_SPLASH_LIB_H_
#define GO_UFS_SPLASH_LIB_H_

#include <Uefi.h>
#include <Protocol/GoConsoleEmblem.h>

typedef EFI_STATUS (*GO_READ_SPLASH_BYTES)(VOID *Context, UINT64 Offset, UINTN Size, VOID *Buffer);
typedef BOOLEAN (*GO_DECODE_SPLASH)(GO_READ_SPLASH_BYTES Read, VOID *Context, UINT64 Bytes, GO_OCULUS_LOGO *Logo);

BOOLEAN
GoReadUfsLogo (GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo);

#endif
