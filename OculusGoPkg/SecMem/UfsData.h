/** Capacity-only UFS data-in probe. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

VOID GoUfsDataControl (UINT64 Tr, UINT64 Tm);
BOOLEAN GoUfsLkIdle (VOID);
BOOLEAN GoUfsLkPrior (CONST UINT32 *Descriptor);
VOID GoUfsRingNopSlot (VOID);
// Caller must own the four CPU pages and their complete, writable UFS bus mapping.
VOID GoUfsDataWindow (CONST UINT64 BusPages[4]);
