/** DXE_TABLES checkpoints at library construction and configuration table publication.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Guid/DxeServices.h>
#include <Guid/HobList.h>
#include <Guid/MemoryTypeInformation.h>
#include <Library/BaseMemoryLib.h>
#include <Library/ExtractGuidedSectionLib.h>
#include <Library/HobLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Trial/DxeLayout.h>
#include <Trial/StackLayout.h>

extern EFI_SYSTEM_TABLE *gDxeCoreST;
extern EFI_DXE_SERVICES *gDxeCoreDS;
extern EFI_HANDLE gDxeCoreImageHandle;
extern EFI_MEMORY_TYPE_INFORMATION gMemoryTypeInformation[];
VOID EFIAPI __real_ProcessLibraryConstructorList (EFI_HANDLE Handle, EFI_SYSTEM_TABLE *Table);

VOID EFIAPI
__wrap_ProcessLibraryConstructorList (EFI_HANDLE Handle, EFI_SYSTEM_TABLE *Table)
{
  EFI_GUID *Handlers = NULL;
  if (Handle == NULL || Handle != gDxeCoreImageHandle || Table == NULL || Table != gDxeCoreST) {
    goto Rejected;
  }
  __real_ProcessLibraryConstructorList (Handle, Table);
  if (gST != Table || gImageHandle != Handle || gBS != Table->BootServices ||
      gRT != Table->RuntimeServices || gBS == NULL || gRT == NULL ||
      ExtractGuidedSectionGetGuidList (&Handlers) != 0 ||
      !TrialSpan ((UINTN)Handlers, sizeof (*Handlers), GO_DXE_POOL, GO_DXE_POOL_END)) {
    goto Rejected;
  }
  TrialPaint (0x0000ff, 0xffff00);
  return;

Rejected:
  __asm__ volatile (".global TrialConstructorsRejected\nTrialConstructorsRejected: b TrialConstructorsRejected");
}

STATIC __attribute__((noinline, noreturn)) VOID
TrialTablesRejected (VOID)
{
  for (;;) {
    __asm__ volatile ("wfe");
  }
}

#ifdef OCULUS_GO_DXE_DEBUG
VOID TrialInitializeDebugPage (VOID);
#endif

// At this call site DxeMain has installed precisely three different GUIDs.
// Validate the array bounds before calling the same lookup library as a DXE consumer.
VOID
__wrap_CoreInitializeDebugImageInfoTable (VOID)
{
  VOID *Services, *Hobs, *Types;
  EFI_GCD_MEMORY_SPACE_DESCRIPTOR Stack;
  CONST EFI_HOB_HANDOFF_INFO_TABLE *Original = (VOID *)(UINTN)GO_DXE_POOL;
  UINTN Bytes = Original->EfiFreeMemoryBottom - GO_DXE_POOL;
  if (gST != gDxeCoreST || gST->Hdr.Signature != EFI_SYSTEM_TABLE_SIGNATURE ||
      gST->NumberOfTableEntries != 3 || ((UINTN)gST->ConfigurationTable & 7) != 0 ||
      !TrialSpan ((UINTN)gST->ConfigurationTable, 3 * sizeof (EFI_CONFIGURATION_TABLE),
                  GO_DXE_POOL, GO_DXE_POOL_END) ||
      EfiGetSystemConfigurationTable (&gEfiDxeServicesTableGuid, &Services) != EFI_SUCCESS ||
      Services != gDxeCoreDS || gDxeCoreDS->Hdr.Signature != DXE_SERVICES_SIGNATURE ||
      ((EFI_DXE_SERVICES *)Services)->GetMemorySpaceDescriptor (GO_DXE_STACK_BASE, &Stack) != EFI_SUCCESS ||
      Stack.BaseAddress != GO_DXE_STACK_BASE || Stack.Length != GO_TRIAL_STACK_TOP - GO_DXE_STACK_BASE ||
      Stack.GcdMemoryType != EfiGcdMemoryTypeReserved || Stack.ImageHandle != gDxeCoreImageHandle) {
    TrialTablesRejected ();
  }
  TrialPaint (0x00ffff, 0x0000ff);
  if (EfiGetSystemConfigurationTable (&gEfiHobListGuid, &Hobs) != EFI_SUCCESS ||
      Hobs != GetHobList () || Bytes < sizeof (*Original) || Bytes > EFI_PAGE_SIZE ||
      !TrialSpan ((UINTN)Hobs, Bytes, GO_DXE_POOL + EFI_PAGE_SIZE, GO_DXE_POOL_END) ||
      CompareMem (Hobs, Original, Bytes) != 0 ||
      EfiGetSystemConfigurationTable (&gEfiMemoryTypeInformationGuid, &Types) != EFI_SUCCESS ||
      Types != gMemoryTypeInformation) {
    TrialTablesRejected ();
  }
  TrialPaint (0x00ff00, 0xff8000);
#ifdef OCULUS_GO_DXE_DEBUG
  TrialInitializeDebugPage ();
#else
  __asm__ volatile (".global TrialTablesComplete\nTrialTablesComplete: b TrialTablesComplete");
  __builtin_unreachable ();
#endif
}
