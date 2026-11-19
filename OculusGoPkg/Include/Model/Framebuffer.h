/** @file
  Memory shared by the SEC and DXE sides of the QEMU GOP model.
  Geometry provenance: docs/SEC_VISUAL_PHYSICAL_REVIEW.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#ifndef OCULUS_GO_MODEL_FRAMEBUFFER_H_
#define OCULUS_GO_MODEL_FRAMEBUFFER_H_

#define GO_MODEL_FB_BASE             0x83401000U
#define GO_MODEL_FB_WIDTH            1440U
#define GO_MODEL_FB_HEIGHT           2560U
#define GO_MODEL_FB_BYTES_PER_PIXEL  3U
#define GO_MODEL_FB_STRIDE           (GO_MODEL_FB_WIDTH * GO_MODEL_FB_BYTES_PER_PIXEL)
#define GO_MODEL_FB_SIZE             (GO_MODEL_FB_HEIGHT * GO_MODEL_FB_STRIDE)

#endif
