/** Original Oculus emblem sampled at boot from the Go. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_OCULUS_LOGO_H_
#define GO_OCULUS_LOGO_H_

#include <Protocol/GraphicsOutput.h>

#include <Protocol/GoConsoleEmblem.h>

typedef enum { GoLogoAbsent, GoLogoPartition, GoLogoFramebuffer } GO_LOGO_SOURCE;

BOOLEAN
GoReadPartitionLogo (OUT GO_OCULUS_LOGO *Logo);

GO_LOGO_SOURCE
GoReadOculusLogo (OUT GO_OCULUS_LOGO *Logo);

#endif
