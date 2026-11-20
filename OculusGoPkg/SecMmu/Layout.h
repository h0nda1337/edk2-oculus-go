// SEC_MMU and SEC_DXE. All ends are exclusive. SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef GO_SEC_MMU_LAYOUT_H
#define GO_SEC_MMU_LAYOUT_H
#include <Trial/StackLayout.h>
#ifdef OCULUS_GO_DXE_DEBUG
#include <Trial/DebugPage.h>
#endif
#define GO_PAGE_BYTES    0x1000
#define GO_CODE_START    0x80081000
#ifdef OCULUS_GO_SEC_DXE
#define GO_CODE_END      0x80100000
#ifdef OCULUS_GO_DXE_GOP
#include <Display/Framebuffer.h>
#define GO_TABLE_COUNT   11
#else
#define GO_TABLE_COUNT   8
#endif
#define GO_STACK_PAGE    GO_DXE_STACK_BASE
#else
#define GO_CODE_END      0x80085000
#define GO_TABLE_COUNT   7
#define GO_STACK_PAGE    0x8047e000
#endif
#define GO_TABLE_BASE    0x8043f000
#define GO_STACK_TOP     GO_TRIAL_STACK_TOP
#define GO_BAND_ONE      0x836a4000
#define GO_BAND_TWO      0x83bea000
#define GO_BAND_BYTES    (32 * 4320)
#define GO_BAND_PAGES    34
#endif
