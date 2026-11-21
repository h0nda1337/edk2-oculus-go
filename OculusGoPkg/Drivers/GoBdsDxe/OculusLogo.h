/** Original Oculus emblem sampled at boot from the Go. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_OCULUS_LOGO_H_
#define GO_OCULUS_LOGO_H_

#include <Protocol/GraphicsOutput.h>

#define GO_LOGO_WIDTH   68
#define GO_LOGO_HEIGHT  42

typedef struct {
  UINT8 Luma[GO_LOGO_HEIGHT][GO_LOGO_WIDTH];
} GO_OCULUS_LOGO;

BOOLEAN
GoReadOculusLogo (OUT GO_OCULUS_LOGO *Logo);

#endif
