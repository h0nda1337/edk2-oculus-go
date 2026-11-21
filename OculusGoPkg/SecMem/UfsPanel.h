/** Passive SEC diagnostics. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_PANEL_H_
#define GO_UFS_PANEL_H_
#include <Base.h>

VOID GoUfsDraw (UINTN Col, UINTN Row, CONST CHAR8 *Text);
VOID GoUfsHeading (CONST CHAR8 *State, CONST CHAR8 *Name);
VOID GoUfsDrawHex (UINTN Col, UINTN Row, UINT32 Value);
BOOLEAN GoUfsRead32 (UINTN Address, UINT32 *Value);
BOOLEAN GoUfsValidatePacificFdt (CONST VOID *Fdt);

#ifdef GO_UFS_QUEUES
// Private, 16 KiB, within the loaded diagnostic FD; see its FDF regions.
#define GO_QUEUE_WINDOW_START  0x80440000U
#define GO_QUEUE_WINDOW_END    0x80444000U
BOOLEAN GoUfsWindowClearInFdt (CONST VOID *Fdt);
#ifdef GO_UFS_LK_MAP
#ifdef GO_UFS_DATA
VOID GoUfsDataControl (UINT64 Tr, UINT64 Tm);
#endif
#ifdef GO_UFS_NOP11
VOID GoUfsNop11 (UINT64 Tr, UINT64 Tm);
#endif
VOID GoUfsLkMap (UINT64 Tr, UINT64 Tm);
#endif
VOID GoUfsCaptureQueues (CONST VOID *Fdt);
#endif
#endif
