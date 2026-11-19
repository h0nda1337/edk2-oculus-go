/** Run one upstream FV driver using the bounded DXE trial memory map.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Chipset/AArch64Mmu.h>
#include <IndustryStandard/PeImage.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/DevicePathUtilities.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Trial/DispatchLayout.h>
#include <Trial/DxeLayout.h>

EFI_STATUS EFIAPI __real_CoreStartImage (EFI_HANDLE Handle, UINTN *Size, CHAR16 **Data);
EFI_STATUS EFIAPI __real_CoreDispatcher (VOID);
STATIC CONST EFI_GUID mDevicePathFile = {0x9b680fce,0xad6b,0x4f3a,{0xb6,0x0b,0xf5,0x98,0x99,0x00,0x34,0x43}};
STATIC BOOLEAN mStarted;
STATIC UINTN mTextBase, mTextEnd;

STATIC __attribute__((noinline,noreturn)) VOID
TrialDispatchRejected (VOID)
{
  for (;;) {
    __asm__ volatile ("wfe");
  }
}

STATIC VOID
InvalidateTranslations (UINT64 El)
{
  __asm__ volatile ("dsb sy" ::: "memory");
  if (El == 4) {
    __asm__ volatile ("tlbi vmalle1" ::: "memory");
  } else {
    __asm__ volatile ("tlbi alle2" ::: "memory");
  }
  __asm__ volatile ("dsb sy\n isb" ::: "memory");
}

// Relocation has completed into RW/XN memory. Change only whole text pages,
// after validating every section, the entry RVA and the original descriptors.
STATIC BOOLEAN
SealDriverText (EFI_LOADED_IMAGE_PROTOCOL *Image)
{
  UINTN Base = (UINTN)Image->ImageBase;
  UINTN Size = Image->ImageSize;
  EFI_IMAGE_DOS_HEADER *Dos = Image->ImageBase;
  EFI_IMAGE_NT_HEADERS64 *Nt;
  EFI_IMAGE_SECTION_HEADER *Section;
  UINTN End, PreviousEnd, Start = 0, Limit = 0;
  UINT64 El;
  volatile UINT64 *L3 = (volatile UINT64 *)(UINTN)GO_ARENA_L3;
  if ((Base & EFI_PAGE_MASK) || (Size & EFI_PAGE_MASK) || Size < EFI_PAGE_SIZE ||
      !TrialSpan (Base, Size, GO_DXE_POOL, GO_DXE_POOL_END) || Dos->e_magic != EFI_IMAGE_DOS_SIGNATURE ||
      Dos->e_lfanew > Size - sizeof (*Nt) || (Dos->e_lfanew & 7)) {
    return FALSE;
  }
  Nt = (VOID *)(Base + Dos->e_lfanew);
  if (Nt->Signature != EFI_IMAGE_NT_SIGNATURE || Nt->FileHeader.Machine != IMAGE_FILE_MACHINE_ARM64 ||
      Nt->FileHeader.SizeOfOptionalHeader != sizeof (Nt->OptionalHeader) ||
      Nt->OptionalHeader.Magic != EFI_IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
      Nt->OptionalHeader.Subsystem != EFI_IMAGE_SUBSYSTEM_EFI_BOOT_SERVICE_DRIVER ||
      Nt->OptionalHeader.SizeOfImage != Size || Nt->OptionalHeader.SectionAlignment != EFI_PAGE_SIZE ||
      Nt->OptionalHeader.SizeOfHeaders > Size || Nt->FileHeader.NumberOfSections == 0 ||
      Nt->FileHeader.NumberOfSections > 16) {
    return FALSE;
  }
  Section = (VOID *)(Nt + 1);
  if (!TrialSpan ((UINTN)Section, Nt->FileHeader.NumberOfSections * sizeof (*Section), Base,
                  Base + Nt->OptionalHeader.SizeOfHeaders)) {
    return FALSE;
  }
  PreviousEnd = ALIGN_VALUE (Nt->OptionalHeader.SizeOfHeaders, EFI_PAGE_SIZE);
  for (UINTN I = 0; I < Nt->FileHeader.NumberOfSections; ++I, ++Section) {
    UINTN Rva = Section->VirtualAddress;
    UINTN Bytes = MAX (Section->Misc.VirtualSize, Section->SizeOfRawData);
    if ((Rva & EFI_PAGE_MASK) || Rva < PreviousEnd || !TrialSpan (Rva, Bytes, 0, Size)) {
      return FALSE;
    }
    End = ALIGN_VALUE (Rva + Bytes, EFI_PAGE_SIZE);
    if (Section->Characteristics & EFI_IMAGE_SCN_MEM_EXECUTE) {
      if (Start != 0 || (Section->Characteristics & EFI_IMAGE_SCN_MEM_WRITE) ||
          !TrialSpan (Nt->OptionalHeader.AddressOfEntryPoint, 4, Rva, Rva + Bytes)) {
        return FALSE;
      }
      Start = Base + Rva;
      Limit = Base + End;
    }
    PreviousEnd = End;
  }
  __asm__ volatile ("mrs %0, CurrentEL" : "=r"(El));
  if (Start == 0 || (El != 4 && El != 8)) {
    return FALSE;
  }
  UINT64 Attr = TT_TYPE_BLOCK_ENTRY_LEVEL3 | TT_AF | TT_SH_INNER_SHAREABLE | TT_ATTR_INDX_MEMORY_NON_CACHEABLE;
  UINT64 Rw = Attr | TT_XN_MASK | (El == 4 ? TT_PXN_MASK : 0);
  UINT64 Rx = Attr | TT_AP_NO_RO | (El == 4 ? TT_UXN_MASK : 0);
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    if (L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] != (Va | Rw)) {
      return FALSE;
    }
  }
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] = 0;
  }
  InvalidateTranslations (El);
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] = Va | Rx;
  }
  InvalidateTranslations (El);
  __asm__ volatile ("ic iallu\n dsb sy\n isb" ::: "memory");
  mTextBase = Start;
  mTextEnd = Limit;
  return TRUE;
}

EFI_STATUS EFIAPI
__wrap_CoreStartImage (EFI_HANDLE Handle, UINTN *Size, CHAR16 **Data)
{
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH *Path;
  if (mStarted || Size != NULL || Data != NULL ||
      gBS->HandleProtocol (Handle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image) != EFI_SUCCESS ||
      Image->SystemTable != gST || Image->ParentHandle != gImageHandle || Image->ImageCodeType != EfiBootServicesCode ||
      Image->ImageDataType != EfiBootServicesData || Image->FilePath == NULL) {
    TrialDispatchRejected ();
  }
  Path = (VOID *)Image->FilePath;
  if (Path->Header.Type != MEDIA_DEVICE_PATH || Path->Header.SubType != MEDIA_PIWG_FW_FILE_DP ||
      Path->Header.Length[0] != sizeof (*Path) || Path->Header.Length[1] != 0 ||
      !CompareGuid (&Path->FvFileName, &mDevicePathFile) || !SealDriverText (Image)) {
    TrialDispatchRejected ();
  }
  TrialPaint (0xffff00, 0x0000ff);
  if (__real_CoreStartImage (Handle, Size, Data) != EFI_SUCCESS) {
    TrialDispatchRejected ();
  }
  mStarted = TRUE;
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
__wrap_CoreDispatcher (VOID)
{
  EFI_DEVICE_PATH_UTILITIES_PROTOCOL *Utilities;
  EFI_DEVICE_PATH_PROTOCOL End = { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (End), 0 } };
  if (gBS->LocateProtocol (&gEfiDevicePathUtilitiesProtocolGuid, NULL, (VOID **)&Utilities) != EFI_NOT_FOUND) {
    TrialDispatchRejected ();
  }
  TrialPaint (0x00ffff, 0x0000ff);
  if (__real_CoreDispatcher () != EFI_SUCCESS || !mStarted ||
      gBS->LocateProtocol (&gEfiDevicePathUtilitiesProtocolGuid, NULL, (VOID **)&Utilities) != EFI_SUCCESS ||
      !TrialSpan ((UINTN)Utilities->GetDevicePathSize, 4, mTextBase, mTextEnd) ||
      Utilities->GetDevicePathSize (&End) != sizeof (End)) {
    TrialDispatchRejected ();
  }
  TrialPaint (0xff8000, 0x00ff00);
  __asm__ volatile (".global TrialDispatchComplete\nTrialDispatchComplete: b TrialDispatchComplete");
  __builtin_unreachable ();
}
