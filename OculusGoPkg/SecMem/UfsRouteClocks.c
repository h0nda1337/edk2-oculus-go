/** Read the RPM-identified AGGRE2 GCC status after the Pacific EVT handoff.
    The addresses and their origin are recorded in docs/UFS_ROUTE_CLOCKS.md.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

STATIC CONST struct { CONST CHAR8 *Name; UINT32 Address; } mRouteSamples[] = {
  { "DOM", 0x383004 }, { "NAX", 0x383008 }, { "NAH", 0x38300c },
  { "SAX", 0x38301c }, { "SAH", 0x383020 }
};

VOID
GoUfsSnapshot (CONST VOID *Fdt)
{
  UINT32 Value;

  if (!GoUfsValidatePacificFdt (Fdt)) {
    return;
  }
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 7, "FD BUS UNKNOWN");
  for (UINTN I = 0; I < ARRAY_SIZE (mRouteSamples); ++I) {
    CONST CHAR8 *Name = mRouteSamples[I].Name;
    GoUfsHeading ("READ", Name);
    if (!GoUfsRead32 (mRouteSamples[I].Address, &Value)) {
      GoUfsHeading ("FAULT", Name);
      return;
    }
    GoUfsDraw (0, I + 1, Name);
    GoUfsDrawHex (4, I + 1, Value);
    if (Value == MAX_UINT32) {
      GoUfsHeading ("INVALID", Name);
      return;
    }
    if (I == 0 && ((Value & BIT31) == 0 || (Value & BIT0) != 0)) {
      GoUfsHeading ("STOP", Name);
      return;
    }
  }
  GoUfsHeading ("CLOCKS", "SAMPLED");
}
