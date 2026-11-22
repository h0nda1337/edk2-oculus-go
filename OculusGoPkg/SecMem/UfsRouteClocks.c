/** Read the RPM-identified AGGRE2 GCC status after the Pacific EVT handoff.
    The addresses and their origin are recorded in docs/UFS_ROUTE_CLOCKS.md.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

STATIC CONST struct { CONST CHAR8 *Name; UINT32 Address; } mRouteSamples[] = {
  { "DOM", 0x383004 }, { "NAX", 0x383008 }, { "NAH", 0x38300c },
  { "SAX", 0x38301c }, { "SAH", 0x383020 },
#ifdef GO_UFS_ROUTE_VIEW
  // Normal-world GR0 of the ANOC2 node verified in the runtime FDT.
  { "ID0", 0x1680020 }, { "ID1", 0x1680024 }, { "ID2", 0x1680028 },
  { "CR0", 0x1680000 },
#endif
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
#ifdef GO_UFS_ROUTE_VIEW
  GoUfsDraw (0, 6, "UFS SID UNKNOWN");
#endif
  GoUfsDraw (0, 7, "FD BUS UNKNOWN");
  for (UINTN I = 0; I < ARRAY_SIZE (mRouteSamples); ++I) {
    CONST CHAR8 *Name = mRouteSamples[I].Name;
    GoUfsHeading ("READ", Name);
    if (!GoUfsRead32 (mRouteSamples[I].Address, &Value)) {
      GoUfsHeading ("FAULT", Name);
      return;
    }
#ifdef GO_UFS_ROUTE_VIEW
    UINTN Col = (I % 2) * 15;
    UINTN Row = 1 + I / 2;
#else
    UINTN Col = 0;
    UINTN Row = I + 1;
#endif
    GoUfsDraw (Col, Row, Name);
    GoUfsDrawHex (Col + 4, Row, Value);
    if (Value == MAX_UINT32) {
      GoUfsHeading ("INVALID", Name);
      return;
    }
    if (I == 0 && ((Value & BIT31) == 0 || (Value & BIT0) != 0)) {
      GoUfsHeading ("STOP", Name);
      return;
    }
#ifdef GO_UFS_ROUTE_VIEW
    // Require powered, running clocks again in this handoff before GR0.
    if (I >= 1 && I <= 4 &&
        (Value == 0 || ((Value >> 28) != 0 && (Value >> 28) != 2))) {
      GoUfsHeading ("STOP", Name);
      return;
    }
    if ((I == 5 && (Value & (BIT30 | BIT29 | BIT28)) == 0) ||
        (I == 6 && ((Value & 255U) == 0 || ((Value >> 16) & 255U) > (Value & 255U)))) {
      GoUfsHeading ("INVALID", Name);
      return;
    }
#endif
  }
#ifdef GO_UFS_ROUTE_VIEW
  GoUfsHeading ("ROUTE", "SAMPLED");
#else
  GoUfsHeading ("CLOCKS", "SAMPLED");
#endif
}
