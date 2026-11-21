/** Passive UFS snapshot on the Pacific EVT. Register provenance in docs/UFS_HANDOFF.md.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Protocol/SimpleTextOut.h>
#include <Display/Framebuffer.h>
#include <third-party/edk2/ConsoleFont.h>

#include "UfsPanel.h"

enum { Power, Reset, Ahb, Axi, SysNoc, Aggre, Version, Enable, Status,
       TransferRun, TransferDoor, TaskRun, TaskDoor, SampleCount };

STATIC CONST struct { CONST CHAR8 *Name; UINT32 Address; } mSamples[] = {
  { "PWR", 0x375004 }, { "RST", 0x375000 }, { "AHB", 0x37500c },
  { "AXI", 0x375008 }, { "NOC", 0x375038 }, { "AGG", 0x383014 },
  { "VER", 0x624008 }, { "HCE", 0x624034 }, { "HCS", 0x624030 },
  { "TRR", 0x624060 }, { "TRD", 0x624058 }, { "TMR", 0x624080 },
  { "TMD", 0x624078 }
};
STATIC_ASSERT (ARRAY_SIZE (mSamples) == SampleCount, "register inventory");

// 29 columns x 8 lines inside the optically confirmed central viewport.
// Coordinates increase right and down in worn orientation.
VOID
GoUfsDraw (UINTN Col, UINTN Row, CONST CHAR8 *Text)
{
  while (*Text != 0) {
    CONST UINT8 *Glyph = mAsciiFont[(UINT8)*Text++ - ' '];
    for (UINTN V = 0; V < 38; ++V) {
      UINTN X = GO_FB_WIDTH - 1 - ((GO_FB_WIDTH - 8 * 38) / 2 + Row * 38 + V);
      for (UINTN U = 0; U < 16; ++U) {
        UINT8 Gray = (Glyph[V / 2] & (0x80U >> (U / 2))) ? 255 : 0;
        UINTN Y = (GO_FB_HEIGHT / 2 - 29 * 16) / 2 + Col * 16 + U;
        for (UINTN Eye = 0; Eye < 2; ++Eye) {
          UINTN Offset = (Y + Eye * GO_FB_HEIGHT / 2) * GO_FB_STRIDE + X * 3;
          volatile UINT8 *Pixel = (volatile UINT8 *)(UINTN)(GO_FB_BASE + Offset);
          Pixel[0] = Gray;
          Pixel[1] = Gray;
          Pixel[2] = Gray;
        }
      }
    }
    ++Col;
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

VOID
GoUfsHeading (CONST CHAR8 *State, CONST CHAR8 *Name)
{
  GoUfsDraw (0, 0, "                             ");
  GoUfsDraw (0, 0, "UFS");
  GoUfsDraw (4, 0, State);
  GoUfsDraw (14, 0, Name);
}

VOID
GoUfsDrawHex (UINTN Col, UINTN Row, UINT32 Value)
{
  CHAR8 Hex[9];
  for (UINTN N = 0; N < 8; ++N) {
    Hex[N] = "0123456789ABCDEF"[(Value >> (28 - N * 4)) & 15];
  }
  Hex[8] = 0;
  GoUfsDraw (Col, Row, Hex);
}

STATIC BOOLEAN
ClockRunning (UINT32 Value)
{
  UINT32 State = Value >> 28;
  return (State == 0) || (State == 2);
}

VOID
GoUfsSnapshot (CONST VOID *Fdt)
{
  UINT32 Value;
  CONST CHAR8 *Name;
  CONST CHAR8 *Stop;
  if (!GoUfsValidatePacificFdt (Fdt)) {
    // Unknown platform: even the scanout address is untrusted.
    return;
  }
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  for (UINTN I = 0; I < SampleCount; ++I) {
    Name = mSamples[I].Name;
    GoUfsHeading ("READ", Name);
    if (!GoUfsRead32 (mSamples[I].Address, &Value)) {
      GoUfsHeading ("FAULT", Name);
      return;
    }
    UINTN Col = (I % 2) * 15;
    UINTN Row = 1 + I / 2;
    GoUfsDraw (Col, Row, Name);
    GoUfsDrawHex (Col + 4, Row, Value);
    Stop = NULL;
    if ((Value == MAX_UINT32) || ((I == Version) && (Value == 0))) {
      Stop = "INVALID";
    } else if (((I == Power) && (((Value & BIT31) == 0) || ((Value & BIT0) != 0))) ||
               ((I == Reset) && ((Value & BIT0) != 0)) ||
               ((I >= Ahb) && (I <= Aggre) && !ClockRunning (Value))) {
      Stop = "GATED";
    } else if ((I == Enable) && ((Value & BIT0) == 0)) {
      Stop = "DISABLED";
    }
#ifdef GO_UFS_QUEUES
    if ((I == Version) && (Value != 0x00010100)) {
      Stop = "VERSION";
    } else if (((I == Status) && ((Value & 0x3f) != 0x0f)) ||
               (((I == TransferRun) || (I == TaskRun)) && (Value != 1))) {
      Stop = "NOT READY";
    } else if (((I == TransferDoor) || (I == TaskDoor)) && (Value != 0)) {
      Stop = "BUSY";
    }
#endif
    if (Stop != NULL) {
      GoUfsHeading (Stop, Name);
      return;
    }
  }
#ifdef GO_UFS_QUEUES
  GoUfsCaptureQueues (Fdt);
#else
  GoUfsHeading ("DONE", "");
#endif
}
