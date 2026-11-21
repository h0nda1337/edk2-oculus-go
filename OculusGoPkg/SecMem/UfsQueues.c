/** Read-only UFSHCI 1.1 queue geometry and CPU-side window inspection.
    All addresses returned by the host are opaque DMA addresses.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

enum { Cap, TrLow, TrHigh, TmLow, TmHigh, QueueFields };
typedef struct { CONST CHAR8 *Name; UINT32 Address; } GO_UFS_REGISTER;
STATIC CONST GO_UFS_REGISTER mQueueRegs[] = {
  { "CAP", 0x624000 }, { "TRL", 0x624050 }, { "TRH", 0x624054 },
  { "TML", 0x624070 }, { "TMH", 0x624074 }
};
STATIC_ASSERT (ARRAY_SIZE (mQueueRegs) == QueueFields, "queue register inventory");

STATIC CONST GO_UFS_REGISTER mFinalRegs[] = {
  { "HCE", 0x624034 }, { "HCS", 0x624030 },
  { "TRR", 0x624060 }, { "TRD", 0x624058 }, { "TMR", 0x624080 }, { "TMD", 0x624078 }
};

STATIC BOOLEAN
Sample (CONST GO_UFS_REGISTER *Register, UINT32 *Value)
{
  GoUfsHeading ("READ", Register->Name);
  if (!GoUfsRead32 (Register->Address, Value)) {
    GoUfsHeading ("FAULT", Register->Name);
    return FALSE;
  }
  return TRUE;
}

STATIC VOID
ShowField (UINTN I, UINT32 Value)
{
  // Bases use high then low dword in worn orientation.
  if (I == Cap) {
    GoUfsDrawHex (4, 1, Value);
  } else {
    GoUfsDrawHex (((I == TrHigh) || (I == TmHigh)) ? 4 : 13,
                  ((I == TrLow) || (I == TrHigh)) ? 2 : 3, Value);
  }
}

// Return the exclusive bound if it can be represented with a checked add.
STATIC BOOLEAN
ListEnd (UINT64 Base, UINT32 Length, BOOLEAN Wide, UINT64 *End)
{
  if ((Base == 0) || ((Base & 1023) != 0) || (Base > MAX_UINT64 - Length)) {
    return FALSE;
  }
  *End = Base + Length;
  return Wide || (*End <= 0x100000000ULL);
}

VOID
GoUfsCaptureQueues (CONST VOID *Fdt)
{
  UINT32 Fields[QueueFields], Value, TrBytes, TmBytes;
  UINT64 Tr, Tm, TrEnd, TmEnd;
  STATIC CONST UINT32 Masks[] = { BIT0, 0x3f, MAX_UINT32, MAX_UINT32, MAX_UINT32, MAX_UINT32 };
  STATIC CONST UINT32 Ready[] = { 1, 0x0f, 1, 0, 1, 0 };
  BOOLEAN Wide;
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 1, "CAP");
  GoUfsDraw (0, 2, "UTR");
  GoUfsDraw (0, 3, "UTM");
  GoUfsDraw (0, 7, "DMA MAP UNKNOWN");
  for (UINTN Pass = 0; Pass < 2; ++Pass) {
    for (UINTN I = 0; I < QueueFields; ++I) {
      if (!Sample (&mQueueRegs[I], &Value)) {
        return;
      }
      if (Pass == 0) {
        Fields[I] = Value;
        ShowField (I, Value);
      } else if (Fields[I] != Value) {
        GoUfsHeading ("CHANGED", mQueueRegs[I].Name);
        return;
      }
    }
  }
  for (UINTN I = 0; I < ARRAY_SIZE (mFinalRegs); ++I) {
    if (!Sample (&mFinalRegs[I], &Value)) {
      return;
    }
    if ((Value == MAX_UINT32) || ((Value & Masks[I]) != Ready[I])) {
      GoUfsHeading ("CHANGED", mFinalRegs[I].Name);
      return;
    }
  }
  if (Fields[Cap] == MAX_UINT32) {
    GoUfsHeading ("INVALID", "CAP");
    return;
  }
  // NUTRS/NUTMRS are encoded as N-1. UTRD = 8 dwords; UTMRD = 20 dwords.
  TrBytes = ((Fields[Cap] & 31) + 1) * 32;
  TmBytes = (((Fields[Cap] >> 16) & 7) + 1) * 80;
  Wide = (Fields[Cap] & BIT24) != 0;
  GoUfsDraw (15, 1, Wide ? "ADDR 64" : "ADDR 32");
  GoUfsDraw (0, 4, "LEN");
  GoUfsDrawHex (4, 4, TrBytes);
  GoUfsDrawHex (13, 4, TmBytes);
  Tr = ((UINT64)Fields[TrHigh] << 32) | Fields[TrLow];
  Tm = ((UINT64)Fields[TmHigh] << 32) | Fields[TmLow];
  if (!ListEnd (Tr, TrBytes, Wide, &TrEnd)) {
    GoUfsHeading ("INVALID", "UTR");
    return;
  }
  if (!ListEnd (Tm, TmBytes, Wide, &TmEnd)) {
    GoUfsHeading ("INVALID", "UTM");
    return;
  }
  if ((Tr < TmEnd) && (Tm < TrEnd)) {
    GoUfsHeading ("OVERLAP", "LISTS");
    return;
  }
  GoUfsDraw (0, 5, "FD");
  GoUfsDrawHex (4, 5, GO_QUEUE_WINDOW_START);
  GoUfsDrawHex (13, 5, GO_QUEUE_WINDOW_END - GO_QUEUE_WINDOW_START);
  // A numeric intersection is grounds to skip, even without a proved bus mapping.
  if (((Tr < GO_QUEUE_WINDOW_END) && (GO_QUEUE_WINDOW_START < TrEnd)) ||
      ((Tm < GO_QUEUE_WINDOW_END) && (GO_QUEUE_WINDOW_START < TmEnd))) {
    GoUfsHeading ("OVERLAP", "FD");
    return;
  }
  if (!GoUfsWindowClearInFdt (Fdt)) {
    GoUfsHeading ("CONFLICT", "FDT");
    return;
  }
  GoUfsHeading ("CHECK", "FD");
  // Read only the fixed window supplied by our image. No queue-base dereferences.
  for (UINTN Addr = GO_QUEUE_WINDOW_START; Addr < GO_QUEUE_WINDOW_END; Addr += sizeof (UINT32)) {
    if (*(volatile CONST UINT32 *)Addr != MAX_UINT32) {
      GoUfsHeading ("DIRTY", "FD");
      return;
    }
  }
  GoUfsDraw (0, 6, "CPU WINDOW CLEAN");
  GoUfsHeading ("QUEUES", "DONE");
}
