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
#ifdef OCULUS_GO_DXE_GOP
#include <Protocol/GraphicsOutput.h>
STATIC CONST EFI_GUID mGopFile = {0x8cd15dc8,0xf091,0x4917,{0xb7,0x79,0x34,0x2c,0x1e,0x0a,0xa2,0xde}};
VOID TrialGopBlt (UINTN Start, UINTN Limit, CONST EFI_GUID *File);
#endif
#ifdef OCULUS_GO_APP
#include "AppLaunch.h"
EFI_HANDLE mTrialFvHandle;
STATIC EFI_LOADED_IMAGE_PROTOCOL *mSealedApp;
#endif
STATIC UINTN mStarted;
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

STATIC BOOLEAN
ChangeTextAccess (UINTN Start, UINTN Limit, BOOLEAN Execute)
{
  UINT64 El;
  volatile UINT64 *L3 = (volatile UINT64 *)(UINTN)GO_ARENA_L3;
  __asm__ volatile ("mrs %0, CurrentEL" : "=r"(El));
  if (Start == 0 || (El != 4 && El != 8)) {
    return FALSE;
  }
  UINT64 Attr = TT_TYPE_BLOCK_ENTRY_LEVEL3 | TT_AF | TT_SH_INNER_SHAREABLE | TT_ATTR_INDX_MEMORY_NON_CACHEABLE;
  UINT64 Rw = Attr | TT_XN_MASK | (El == 4 ? TT_PXN_MASK : 0);
  UINT64 Rx = Attr | TT_AP_NO_RO | (El == 4 ? TT_UXN_MASK : 0);
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    if (L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] != (Va | (Execute ? Rw : Rx))) {
      return FALSE;
    }
  }
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] = 0;
  }
  InvalidateTranslations (El);
  for (UINTN Va = Start; Va < Limit; Va += EFI_PAGE_SIZE) {
    L3[(Va - GO_DXE_POOL) / EFI_PAGE_SIZE] = Va | (Execute ? Rx : Rw);
  }
  InvalidateTranslations (El);
  __asm__ volatile ("ic iallu\n dsb sy\n isb" ::: "memory");
  return TRUE;
}

// Relocation has completed into RW/XN memory. Change only whole text pages,
// after validating every section, the entry RVA and the original descriptors.
STATIC BOOLEAN
SealImageText (EFI_LOADED_IMAGE_PROTOCOL *Image, UINT16 Subsystem)
{
  UINTN Base = (UINTN)Image->ImageBase;
  UINTN Size = Image->ImageSize;
  EFI_IMAGE_DOS_HEADER *Dos = Image->ImageBase;
  EFI_IMAGE_NT_HEADERS64 *Nt;
  EFI_IMAGE_SECTION_HEADER *Section;
  UINTN End, PreviousEnd, Start = 0, Limit = 0;
  if ((Base & EFI_PAGE_MASK) || (Size & EFI_PAGE_MASK) || Size < EFI_PAGE_SIZE ||
      !TrialSpan (Base, Size, GO_DXE_POOL, GO_DXE_POOL_END) || Dos->e_magic != EFI_IMAGE_DOS_SIGNATURE ||
      Dos->e_lfanew > Size - sizeof (*Nt) || (Dos->e_lfanew & 7)) {
    return FALSE;
  }
  Nt = (VOID *)(Base + Dos->e_lfanew);
  if (Nt->Signature != EFI_IMAGE_NT_SIGNATURE || Nt->FileHeader.Machine != IMAGE_FILE_MACHINE_ARM64 ||
      Nt->FileHeader.SizeOfOptionalHeader != sizeof (Nt->OptionalHeader) ||
      Nt->OptionalHeader.Magic != EFI_IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
      Nt->OptionalHeader.Subsystem != Subsystem ||
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
  if (!ChangeTextAccess (Start, Limit, TRUE)) {
    return FALSE;
  }
  mTextBase = Start;
  mTextEnd = Limit;
  return TRUE;
}

#ifdef OCULUS_GO_APP
BOOLEAN
TrialSealApplication (EFI_LOADED_IMAGE_PROTOCOL *Image)
{
  if (mSealedApp != NULL || !SealImageText (Image, EFI_IMAGE_SUBSYSTEM_EFI_APPLICATION)) {
    return FALSE;
  }
  mSealedApp = Image;
  return TRUE;
}

VOID __real_UnprotectUefiImage (EFI_LOADED_IMAGE_PROTOCOL *Image, EFI_DEVICE_PATH_PROTOCOL *Path);

VOID
__wrap_UnprotectUefiImage (EFI_LOADED_IMAGE_PROTOCOL *Image, EFI_DEVICE_PATH_PROTOCOL *Path)
{
  if (mSealedApp != NULL && Image == mSealedApp) {
    if (!ChangeTextAccess (mTextBase, mTextEnd, FALSE)) {
      TrialDispatchRejected ();
    }
    mSealedApp = NULL;
  }
  __real_UnprotectUefiImage (Image, Path);
}
#endif

STATIC BOOLEAN
DevicePathResponds (VOID)
{
  EFI_DEVICE_PATH_UTILITIES_PROTOCOL *Utilities;
  EFI_DEVICE_PATH_PROTOCOL End = { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (End), 0 } };
  return gBS->LocateProtocol (&gEfiDevicePathUtilitiesProtocolGuid, NULL, (VOID **)&Utilities) == EFI_SUCCESS &&
         TrialSpan ((UINTN)Utilities->GetDevicePathSize, 4, mTextBase, mTextEnd) &&
         Utilities->GetDevicePathSize (&End) == sizeof (End);
}

EFI_STATUS EFIAPI
__wrap_CoreStartImage (EFI_HANDLE Handle, UINTN *Size, CHAR16 **Data)
{
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH *Path;
  STATIC CONST EFI_GUID * CONST Files[] = {
    &mDevicePathFile
#ifdef OCULUS_GO_DXE_GOP
    , &mGopFile
#endif
  };
#ifdef OCULUS_GO_APP
  if (Handle != NULL && Handle == mTrialAppHandle && mSealedApp != NULL) {
    return __real_CoreStartImage (Handle, Size, Data);
  }
#endif
  if (mStarted >= ARRAY_SIZE (Files) || Size != NULL || Data != NULL ||
      gBS->HandleProtocol (Handle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image) != EFI_SUCCESS ||
      Image->SystemTable != gST || Image->ParentHandle != gImageHandle || Image->ImageCodeType != EfiBootServicesCode ||
      Image->ImageDataType != EfiBootServicesData || Image->FilePath == NULL) {
    TrialDispatchRejected ();
  }
  Path = (VOID *)Image->FilePath;
  if (Path->Header.Type != MEDIA_DEVICE_PATH || Path->Header.SubType != MEDIA_PIWG_FW_FILE_DP ||
      Path->Header.Length[0] != sizeof (*Path) || Path->Header.Length[1] != 0 ||
      !CompareGuid (&Path->FvFileName, Files[mStarted]) || !SealImageText (Image, EFI_IMAGE_SUBSYSTEM_EFI_BOOT_SERVICE_DRIVER)) {
    TrialDispatchRejected ();
  }
  if (mStarted == 0) {
    TrialPaint (0xffff00, 0x0000ff);
  }
  if (__real_CoreStartImage (Handle, Size, Data) != EFI_SUCCESS) {
    TrialDispatchRejected ();
  }
#ifdef OCULUS_GO_APP
  mTrialFvHandle = Image->DeviceHandle;
#endif
  ++mStarted;
#ifdef OCULUS_GO_DXE_GOP
  if (mStarted == 1) {
    if (!DevicePathResponds ()) {
      TrialDispatchRejected ();
    }
    TrialPaint (0xff8000, 0x00ff00);
  }
#endif
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
__wrap_CoreDispatcher (VOID)
{
  VOID *Interface;
  if (gBS->LocateProtocol (&gEfiDevicePathUtilitiesProtocolGuid, NULL, &Interface) != EFI_NOT_FOUND) {
    TrialDispatchRejected ();
  }
#ifdef OCULUS_GO_DXE_GOP
  if (gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, &Interface) != EFI_NOT_FOUND) {
    TrialDispatchRejected ();
  }
#endif
  TrialPaint (0x00ffff, 0x0000ff);
  EFI_STATUS Status = __real_CoreDispatcher ();
#ifdef OCULUS_GO_DXE_GOP
  if (Status != EFI_SUCCESS || mStarted != 2) {
    TrialDispatchRejected ();
  }
  TrialGopBlt (mTextBase, mTextEnd, &mGopFile);
#else
  if (Status != EFI_SUCCESS || mStarted != 1 || !DevicePathResponds ()) {
    TrialDispatchRejected ();
  }
  TrialPaint (0xff8000, 0x00ff00);
  __asm__ volatile (".global TrialDispatchComplete\nTrialDispatchComplete: b TrialDispatchComplete");
#endif
  __builtin_unreachable ();
}
