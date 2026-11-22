/** Host bindings for the production FDT and passive board handoff paths.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#pragma GCC visibility push(default)
#include <string.h>
#include <stdarg.h>
#pragma GCC visibility pop
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Platform/PacificUfs.h>
#include "../OculusGoPkg/Drivers/PacificUfsDxe/PacificUfsDxe.c"

UINT32 EFIAPI SwapBytes32 (UINT32 Value) { return __builtin_bswap32 (Value); }
INTN EFIAPI CompareMem (CONST VOID *A, CONST VOID *B, UINTN N) { return memcmp (A, B, N); }
VOID *EFIAPI ScanMem8 (CONST VOID *P, UINTN N, UINT8 Byte) { return memchr (P, Byte, N); }
UINTN EFIAPI AsciiStrLen (CONST CHAR8 *P) { return strlen (P); }
UINTN EFIAPI AsciiStrnLenS (CONST CHAR8 *P, UINTN N) { return strnlen (P, N); }
INTN EFIAPI AsciiStrnCmp (CONST CHAR8 *A, CONST CHAR8 *B, UINTN N) { return strncmp (A, B, N); }
CHAR8 *EFIAPI AsciiStrStr (CONST CHAR8 *A, CONST CHAR8 *B) { return strstr (A, B); }

__attribute__((visibility("default"))) BOOLEAN
HostParse (CONST VOID *Tree, UINTN Size, GO_PACIFIC_UFS_RESOURCE *Out)
{
  return GoPacificUfsFromFdt (Tree, Size, Out);
}

STATIC UINT32 Registers[6];
STATIC UINTN Reads, Release;
STATIC EFI_STATUS EFIAPI
ConfirmReleased (GO_PACIFIC_UFS_HANDOFF_PROTOCOL *This, EFI_HANDLE Controller)
{
  if (Controller != mController || Controller == NULL) {
    __builtin_trap ();
  }
  return Release == 2 ? EFI_SUCCESS : EFI_NOT_READY;
}

STATIC GO_PACIFIC_UFS_HANDOFF_PROTOCOL Handoff = { ConfirmReleased };
EFI_GUID gGoPacificUfsHandoffProtocolGuid;
STATIC EFI_STATUS EFIAPI
OpenBoardRelease (EFI_HANDLE Handle, EFI_GUID *Guid, VOID **Interface)
{
  if (Handle != mController || Guid != &gGoPacificUfsHandoffProtocolGuid) {
    __builtin_trap ();
  }
  if (Release == 0) {
    return EFI_UNSUPPORTED;
  }
  *Interface = &Handoff;
  return EFI_SUCCESS;
}

STATIC EFI_BOOT_SERVICES Services = { .HandleProtocol = OpenBoardRelease };
EFI_BOOT_SERVICES *gBS = &Services;
UINT32 EFIAPI
MmioRead32 (UINTN Address)
{
  STATIC CONST UINTN Offsets[] = { 0x08, 0x34, 0x60, 0x80, 0x58, 0x78 };
  for (UINTN I = 0; I < ARRAY_SIZE (Offsets); ++I) {
    if (Address == PACIFIC_UFS_BASE + Offsets[I] && Release == 2) {
      ++Reads;
      return Registers[I];
    }
  }
  __builtin_trap ();
}

__attribute__((visibility("default"))) EFI_STATUS
HostPrepare (UINTN State, CONST UINT32 *Snapshot, UINTN *ActualReads)
{
  EFI_ACPI_ADDRESS_SPACE_DESCRIPTOR Mmio = { .AddrRangeMin = PACIFIC_UFS_BASE, .AddrLen = PACIFIC_UFS_LENGTH };
  NON_DISCOVERABLE_DEVICE Device = { .Resources = &Mmio };
  mController = (EFI_HANDLE)&Device;
  Release = State;
  Reads = 0;
  memcpy (Registers, Snapshot, sizeof (Registers));
  EFI_STATUS Status = PacificUfsPrepare (&Device);
  *ActualReads = Reads;
  return Status;
}

STATIC struct {
  EFI_HOB_GUID_TYPE Header;
  GO_PACIFIC_UFS_RESOURCE Resource;
} Published;
STATIC BOOLEAN HobPresent;
STATIC UINTN Registrations;
EFI_GUID gOculusGoUfsResourceGuid;

VOID * EFIAPI
GetFirstGuidHob (CONST EFI_GUID *Guid)
{
  if (Guid != &gOculusGoUfsResourceGuid) {
    __builtin_trap ();
  }
  return HobPresent ? &Published : NULL;
}

EFI_STATUS EFIAPI
RegisterNonDiscoverableMmioDevice (NON_DISCOVERABLE_DEVICE_TYPE Type,
  NON_DISCOVERABLE_DEVICE_DMA_TYPE DmaType, NON_DISCOVERABLE_DEVICE_INIT Init,
  EFI_HANDLE *Handle, UINTN Count, ...)
{
  va_list Args;
  va_start (Args, Count);
  UINTN Base = va_arg (Args, UINTN);
  UINTN Length = va_arg (Args, UINTN);
  va_end (Args);
  if (Type != NonDiscoverableDeviceTypeUfs || Init != PacificUfsPrepare ||
      Handle != &mController || *Handle != NULL || Count != 1 ||
      Base != PACIFIC_UFS_BASE || Length != PACIFIC_UFS_LENGTH ||
      DmaType != (Published.Resource.DmaCoherent ? NonDiscoverableDeviceDmaTypeCoherent :
                                                   NonDiscoverableDeviceDmaTypeNonCoherent)) {
    __builtin_trap ();
  }
  ++Registrations;
  *Handle = (EFI_HANDLE)&Published;
  return EFI_SUCCESS;
}

__attribute__((visibility("default"))) EFI_STATUS
HostRegister (BOOLEAN Present, INT32 SizeAdjustment, GO_PACIFIC_UFS_RESOURCE *Resource,
  UINTN *ActualRegistrations)
{
  HobPresent = Present;
  Published.Header.Header.HobLength = sizeof (Published) + SizeAdjustment;
  Published.Resource = *Resource;
  mController = NULL;
  Registrations = 0;
  Release = 0; // Any attempted MMIO would fail inside the mock.
  EFI_STATUS Status = PacificUfsEntry (NULL, NULL);
  *ActualRegistrations = Registrations;
  return Status;
}
