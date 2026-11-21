/** @file
  Check the Pacific loader's memory description before two read-only samples.
  Format and addresses are tied to the captures listed in docs/MEMORY_MAP.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <Base.h>

#define MAX_FDT_BYTES  (512U * 1024U)
#define POOL_SAMPLE    0x94000000ULL
#define STACK_SAMPLE   0x97ffffa0ULL

STATIC UINT32
Be32 (CONST UINT8 *P)
{
  return ((UINT32)P[0] << 24) | ((UINT32)P[1] << 16) | ((UINT32)P[2] << 8) | P[3];
}

STATIC UINT64
Be64 (CONST UINT8 *P)
{
  return ((UINT64)Be32 (P) << 32) | Be32 (P + 4);
}

// Compare against a short, terminated literal without reading past End.
STATIC BOOLEAN
NameIs (CONST UINT8 *P, CONST UINT8 *End, CONST CHAR8 *Name)
{
  while ((P < End) && (*Name != '\0') && (*P == (UINT8)*Name)) {
    ++P;
    ++Name;
  }
  return (P < End) && (*P == 0) && (*Name == '\0');
}

STATIC BOOLEAN
IsMemoryNode (CONST UINT8 *Start, CONST UINT8 *Terminator)
{
  CONST CHAR8 *Base = "memory";
  while ((*Base != '\0') && (Start < Terminator) && (*Start == (UINT8)*Base)) {
    ++Start;
    ++Base;
  }
  return (*Base == '\0') && ((Start == Terminator) ||
                             ((*Start == '@') && (Start + 1 < Terminator)));
}

STATIC BOOLEAN
ClearOfSamples (CONST UINT8 *Range)
{
  UINT64 Base;
  UINT64 Size;
  UINT64 End;

  Base = Be64 (Range);
  Size = Be64 (Range + 8);
  if ((Size == 0) || (Size > MAX_UINT64 - Base)) {
    return FALSE;
  }
  End = Base + Size;
  return ((End <= POOL_SAMPLE) || (Base >= POOL_SAMPLE + 8)) &&
         ((End <= STACK_SAMPLE) || (Base >= STACK_SAMPLE + 8));
}

enum { OtherNode, MemoryNode, ReservedNode };
enum {
  RootAddress = 1, RootSize = 2, RamType = 4, RamReg = 8,
  ReservedAddress = 16, ReservedSize = 32, ReservedRanges = 64
};

STATIC BOOLEAN
CheckProperty (
  UINT32 Depth, UINT32 Branch, CONST UINT8 *Name, CONST UINT8 *NamesEnd,
  CONST UINT8 *Value, UINT32 Bytes, UINT32 *Seen
  )
{
  UINT32 Flag;
  UINT32 Idx;

  Flag = 0;
  if ((Depth == 1) || ((Depth == 2) && (Branch == ReservedNode))) {
    if (NameIs (Name, NamesEnd, "#address-cells")) {
      Flag = (Depth == 1) ? RootAddress : ReservedAddress;
    } else if (NameIs (Name, NamesEnd, "#size-cells")) {
      Flag = (Depth == 1) ? RootSize : ReservedSize;
    }
    if (Flag != 0) {
      if ((Bytes != 4) || (Be32 (Value) != 2)) {
        return FALSE;
      }
    } else if ((Depth == 2) && NameIs (Name, NamesEnd, "ranges")) {
      Flag = ReservedRanges;
      if (Bytes != 0) {
        return FALSE;
      }
    }
  } else if ((Depth == 2) && (Branch == MemoryNode)) {
    if (NameIs (Name, NamesEnd, "device_type")) {
      Flag = RamType;
      if ((Bytes != 7) || !NameIs (Value, Value + Bytes, "memory")) {
        return FALSE;
      }
    } else if (NameIs (Name, NamesEnd, "reg")) {
      Flag = RamReg;
      // The observed board has a single 64-bit base/size tuple containing both words.
      if ((Bytes != 16) || (Be64 (Value) != 0x80000000ULL) ||
          (Be64 (Value + 8) != 0xbeac0000ULL)) {
        return FALSE;
      }
    }
  } else if ((Depth == 3) && (Branch == ReservedNode) && NameIs (Name, NamesEnd, "reg")) {
    if ((Bytes == 0) || ((Bytes % 16) != 0)) {
      return FALSE;
    }
    for (Idx = 0; Idx < Bytes; Idx += 16) {
      if (!ClearOfSamples (Value + Idx)) {
        return FALSE;
      }
    }
  }
  if (((Depth == 1) || ((Depth == 2) && (Branch != OtherNode))) &&
      NameIs (Name, NamesEnd, "status") &&
      !((Bytes == 5 && NameIs (Value, Value + Bytes, "okay")) ||
        (Bytes == 3 && NameIs (Value, Value + Bytes, "ok")))) {
    return FALSE;
  }
  if ((*Seen & Flag) != 0) {
    return FALSE;
  }
  *Seen |= Flag;
  return TRUE;
}

// Entry has already required the captured FDT address before calling this function.
// Traversal is iterative. The capture uses the v17 layout: header, reservations,
// structure, strings. Reject unsupported layouts before following any offset.
STATIC BOOLEAN
ValidateFdt (IN CONST VOID *Fdt, IN BOOLEAN RequirePacific)
{
  CONST UINT8 *Data = Fdt;
  CONST UINT8 *Name;
  UINT32 Total, Struct, Strings, Reserve, StructSize, StringsSize, End, Pos;
  UINT32 Depth = 0, Branch = OtherNode, Seen = 0;
  BOOLEAN PacificModel = FALSE;
  BOOLEAN RootSeen = FALSE, MemorySeen = FALSE, ReservedSeen = FALSE;
  UINT32 Token, Bytes, NameOffset, Start;

  if ((Data == NULL) || (Be32 (Data) != 0xd00dfeedU)) {
    return FALSE;
  }
  Total = Be32 (Data + 4);
  if ((Total < 40) || (Total > MAX_FDT_BYTES) || (Be32 (Data + 20) != 17) ||
      (Be32 (Data + 24) != 16)) {
    return FALSE;
  }
  Struct = Be32 (Data + 8);
  Strings = Be32 (Data + 12);
  Reserve = Be32 (Data + 16);
  StringsSize = Be32 (Data + 32);
  StructSize = Be32 (Data + 36);
  if ((Reserve < 40) || ((Reserve & 7) != 0) || (Reserve > Struct) ||
      ((Struct & 3) != 0) || ((StructSize & 3) != 0) || (Struct > Strings) ||
      (Strings > Total) || (StructSize > Strings - Struct) ||
      (StringsSize == 0) || (StringsSize > Total - Strings) ||
      (Data[Strings + StringsSize - 1] != 0)) {
    return FALSE;
  }
  Pos = Reserve;
  for (;;) {
    if (Struct - Pos < 16) {
      return FALSE;
    }
    if ((Be64 (Data + Pos) == 0) && (Be64 (Data + Pos + 8) == 0)) {
      break;
    }
    if (!ClearOfSamples (Data + Pos)) {
      return FALSE;
    }
    Pos += 16;
  }

  End = Struct + StructSize;
  Pos = Struct;
  while (Pos < End) {
    Token = Be32 (Data + Pos);
    Pos += 4;
    switch (Token) {
      case 1: // FDT_BEGIN_NODE
        Start = Pos;
        while ((Pos < End) && (Data[Pos] != 0)) {
          ++Pos;
        }
        if ((Pos == End) || (Depth >= 64)) {
          return FALSE;
        }
        Name = Data + Start;
        if (Depth == 0) {
          if (RootSeen || (Pos != Start)) {
            return FALSE;
          }
          RootSeen = TRUE;
        } else if (Depth == 1) {
          Branch = OtherNode;
          if (IsMemoryNode (Name, Data + Pos)) {
            if (MemorySeen) {
              return FALSE;
            }
            MemorySeen = TRUE;
            Branch = MemoryNode;
          } else if (NameIs (Name, Data + End, "reserved-memory")) {
            if (ReservedSeen) {
              return FALSE;
            }
            ReservedSeen = TRUE;
            Branch = ReservedNode;
          }
        } else if ((Depth >= 3) && (Branch == ReservedNode)) {
          return FALSE; // No nested address translations in the captured reservations.
        }
        ++Depth;
        Pos = (Pos + 4) & ~3U;
        break;
      case 2: // FDT_END_NODE
        if (Depth == 0) {
          return FALSE;
        }
        if (--Depth == 1) {
          Branch = OtherNode;
        }
        break;
      case 3: // FDT_PROP
        if ((Depth == 0) || (End - Pos < 8)) {
          return FALSE;
        }
        Bytes = Be32 (Data + Pos);
        NameOffset = Be32 (Data + Pos + 4);
        Pos += 8;
        if ((Bytes > End - Pos) || (NameOffset >= StringsSize) ||
            !CheckProperty (Depth, Branch, Data + Strings + NameOffset,
                            Data + Strings + StringsSize, Data + Pos, Bytes, &Seen)) {
          return FALSE;
        }
        if (RequirePacific && (Depth == 1) &&
            NameIs (Data + Strings + NameOffset, Data + Strings + StringsSize, "model")) {
          if (PacificModel || (Bytes != sizeof ("Oculus Pacific EVT")) ||
              !NameIs (Data + Pos, Data + Pos + Bytes, "Oculus Pacific EVT")) {
            return FALSE;
          }
          PacificModel = TRUE;
        }
        Pos += (Bytes + 3) & ~3U;
        break;
      case 4: // FDT_NOP
        break;
      case 9: // FDT_END
        return (!RequirePacific || PacificModel) && (Pos == End) && (Depth == 0) &&
               (Seen == (RootAddress | RootSize | RamType | RamReg |
                         ReservedAddress | ReservedSize | ReservedRanges));
      default:
        return FALSE;
    }
  }
  return FALSE;
}

BOOLEAN
OculusGoSecMemValidateFdt (IN CONST VOID *Fdt)
{
  return ValidateFdt (Fdt, FALSE);
}

BOOLEAN
GoUfsValidatePacificFdt (IN CONST VOID *Fdt)
{
  return ValidateFdt (Fdt, TRUE);
}
