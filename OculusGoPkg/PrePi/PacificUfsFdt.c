/** Discover the verified EVT controller while the incoming FDT is accessible.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Platform/PacificUfs.h>
#include <libfdt.h>

// The pinned libfdt checks structure offsets during traversal, but its string
// accessor assumes that the structure's property-name offsets are already valid.
STATIC BOOLEAN
BoundedTree (CONST VOID *Fdt, UINTN Available)
{
  CONST UINT8 *Data = Fdt;
  if (Fdt == NULL || Available < sizeof (struct fdt_header) ||
      (((UINTN)Fdt & 7) != 0) || fdt_magic (Fdt) != FDT_MAGIC ||
      fdt_version (Fdt) != 17 || fdt_last_comp_version (Fdt) != 16) {
    return FALSE;
  }
  UINT32 Total = fdt_totalsize (Fdt);
  UINT32 Struct = fdt_off_dt_struct (Fdt);
  UINT32 Size = fdt_size_dt_struct (Fdt);
  UINT32 Strings = fdt_off_dt_strings (Fdt);
  UINT32 Names = fdt_size_dt_strings (Fdt);
  UINT32 Reserve = fdt_off_mem_rsvmap (Fdt);
  if (Total > Available || Total > PACIFIC_MAX_FDT_BYTES || Reserve < sizeof (struct fdt_header) ||
      (Reserve & 7) != 0 || Reserve > Struct || Struct - Reserve < 16 || (Struct & 3) != 0 ||
      Struct > Strings || Size > Strings - Struct || (Size & 3) != 0 || Strings >= Total ||
      Names == 0 || Names > Total - Strings || Data[Strings + Names - 1] != 0) {
    return FALSE;
  }
  INT32 Depth = 0;
  INT32 Next = 0;
  BOOLEAN RootSeen = FALSE;
  while ((UINT32)Next < Size) {
    INT32 Current = Next;
    CONST struct fdt_property *Prop = (CONST struct fdt_property *)(Data + Struct + Current);
    if (fdt32_to_cpu (Prop->tag) == FDT_PROP &&
        (Size - Current < sizeof (*Prop) || fdt32_to_cpu (Prop->len) > Size - Current - sizeof (*Prop) ||
         fdt32_to_cpu (Prop->nameoff) >= Names)) {
      return FALSE;
    }
    UINT32 Tag = fdt_next_tag (Fdt, Current, &Next);
    if (Next <= Current || (UINT32)Next > Size) {
      return FALSE;
    }
    switch (Tag) {
      case FDT_BEGIN_NODE:
        if (Depth == 0 && (RootSeen || Data[Struct + Current + FDT_TAGSIZE] != 0)) {
          return FALSE;
        }
        RootSeen = TRUE;
        ++Depth;
        break;
      case FDT_END_NODE:
        if (--Depth < 0) {
          return FALSE;
        }
        break;
      case FDT_PROP:
        if (Depth == 0) {
          return FALSE;
        }
        break;
      case FDT_NOP:
        break;
      case FDT_END:
        return RootSeen && Depth == 0 && (UINT32)Next == Size;
      default:
        return FALSE;
    }
  }
  return FALSE;
}

STATIC BOOLEAN
PropertyIs (CONST VOID *Fdt, INT32 Node, CONST CHAR8 *Name, CONST VOID *Value, UINTN Length)
{
  INT32 Size;
  CONST VOID *Prop = fdt_getprop (Fdt, Node, Name, &Size);
  return Prop != NULL && Size == (INT32)Length && CompareMem (Prop, Value, Length) == 0;
}

STATIC BOOLEAN
Compatible (CONST VOID *Fdt, INT32 Node, CONST CHAR8 *Wanted)
{
  INT32 Size;
  CONST CHAR8 *List = fdt_getprop (Fdt, Node, "compatible", &Size);
  if (List == NULL || Size <= 0 || List[Size - 1] != 0) {
    return FALSE;
  }
  return fdt_stringlist_contains (List, Size, Wanted) == 1;
}

STATIC BOOLEAN
Enabled (CONST VOID *Fdt, INT32 Node)
{
  INT32 Size;
  CONST VOID *Status = fdt_getprop (Fdt, Node, "status", &Size);
  if (Status == NULL) {
    return Size == -FDT_ERR_NOTFOUND;
  }
  return (Size == sizeof ("ok") && CompareMem (Status, "ok", Size) == 0) ||
         (Size == sizeof ("okay") && CompareMem (Status, "okay", Size) == 0);
}

BOOLEAN
GoPacificUfsFromFdt (CONST VOID *Fdt, UINTN Available, GO_PACIFIC_UFS_RESOURCE *Resource)
{
  if (Resource == NULL || !BoundedTree (Fdt, Available)) {
    return FALSE;
  }
  INT32 Soc = fdt_path_offset (Fdt, "/soc");
  INT32 Ufs = fdt_path_offset (Fdt, "/soc/ufshc@624000");
  STATIC CONST UINT8 Translation[] = { 0,0,0,0, 0,0,0,0, 0,0,0,0, 0xff,0xff,0xff,0xff };
  if (Soc < 0 || Ufs < 0 || !Enabled (Fdt, 0) || !Enabled (Fdt, Soc) || !Enabled (Fdt, Ufs) ||
      !PropertyIs (Fdt, 0, "model", "Oculus Pacific EVT", sizeof ("Oculus Pacific EVT")) ||
      !Compatible (Fdt, 0, "qcom,apq8096") ||
      !Compatible (Fdt, Soc, "simple-bus") ||
      !Compatible (Fdt, Ufs, "jedec,ufs-1.1") ||
      fdt_address_cells (Fdt, 0) != 2 || fdt_size_cells (Fdt, 0) != 2 ||
      fdt_address_cells (Fdt, Soc) != 1 || fdt_size_cells (Fdt, Soc) != 1 ||
      !PropertyIs (Fdt, Soc, "ranges", Translation, sizeof (Translation))) {
    return FALSE;
  }
  INT32 Size;
  CONST fdt32_t *Reg = fdt_getprop (Fdt, Ufs, "reg", &Size);
  if (Reg == NULL || Size != 2 * sizeof (*Reg) ||
      fdt32_to_cpu (Reg[0]) != PACIFIC_UFS_BASE || fdt32_to_cpu (Reg[1]) != PACIFIC_UFS_LENGTH) {
    return FALSE;
  }
  UINT32 Coherent = FALSE;
  CONST INT32 Ancestors[] = { 0, Soc, Ufs };
  for (UINTN Idx = 0; Idx < ARRAY_SIZE (Ancestors); ++Idx) {
    INT32 NonCoherentSize;
    CONST VOID *Positive = fdt_getprop (Fdt, Ancestors[Idx], "dma-coherent", &Size);
    CONST VOID *Negative = fdt_getprop (Fdt, Ancestors[Idx], "dma-noncoherent", &NonCoherentSize);
    if ((Positive != NULL && (Size != 0 || Negative != NULL)) ||
        (Negative != NULL && NonCoherentSize != 0)) {
      return FALSE;
    }
    if (Positive != NULL || Negative != NULL) {
      Coherent = Positive != NULL;
    }
  }
  Resource->Base = fdt32_to_cpu (Reg[0]);
  Resource->Length = fdt32_to_cpu (Reg[1]);
  Resource->DmaCoherent = Coherent;
  return TRUE;
}
