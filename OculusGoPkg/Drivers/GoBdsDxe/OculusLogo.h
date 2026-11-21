/** Original Oculus emblem sampled at boot from the Go. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_OCULUS_LOGO_H_
#define GO_OCULUS_LOGO_H_

#include <Protocol/GraphicsOutput.h>
#include <Library/GoUfsSplashLib.h>

#include <Protocol/GoConsoleEmblem.h>

typedef enum { GoLogoAbsent, GoLogoPartition, GoLogoFramebuffer, GoLogoUfs } GO_LOGO_SOURCE;

BOOLEAN
GoDecodeSplash (GO_READ_SPLASH_BYTES Read, VOID *Context, UINT64 Bytes, GO_OCULUS_LOGO *Logo);

BOOLEAN
GoReadPartitionLogo (OUT GO_OCULUS_LOGO *Logo);

GO_LOGO_SOURCE
GoReadOculusLogo (OUT GO_OCULUS_LOGO *Logo);

#endif
