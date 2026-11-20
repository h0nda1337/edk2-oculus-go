/** @file
  Inherited splash surface shared by SEC, GOP and the model.
  Geometry provenance: docs/SEC_VISUAL_PHYSICAL_REVIEW.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#ifndef OCULUS_GO_DISPLAY_FRAMEBUFFER_H_
#define OCULUS_GO_DISPLAY_FRAMEBUFFER_H_

#define GO_FB_BASE             0x83401000
#define GO_FB_WIDTH            1440
#define GO_FB_HEIGHT           2560
#define GO_FB_BYTES_PER_PIXEL  3
#define GO_FB_STRIDE           (GO_FB_WIDTH * GO_FB_BYTES_PER_PIXEL)
#define GO_FB_SIZE             (GO_FB_HEIGHT * GO_FB_STRIDE)

#endif
