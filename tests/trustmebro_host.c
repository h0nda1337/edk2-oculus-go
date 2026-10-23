/* Exercise the actual driver against EDK2 headers and mocked boot services.
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef NULL
#include "../OculusGoPkg/Drivers/TrustMeBroDxe/TrustMeBroDxe.c"

EFI_GUID gOculusGoTrustMeBroProtocolGuid = OCULUS_GO_TRUST_ME_BRO_PROTOCOL_GUID;
EFI_GUID gOculusGoEntryHobGuid = { 0 };
STATIC EFI_BOOT_SERVICES Services;
EFI_BOOT_SERVICES *gBS = &Services;
STATIC struct {
  EFI_HOB_GUID_TYPE Header;
  OCULUS_GO_ENTRY_STATE State;
} TestHob;
STATIC BOOLEAN HaveHob;
STATIC UINTN Installs;
STATIC UINTN Checks;

VOID *EFIAPI CopyMem (OUT VOID *Destination, IN CONST VOID *Source, IN UINTN Length)
{
  return memcpy (Destination, Source, Length);
}

VOID *EFIAPI GetFirstGuidHob (IN CONST EFI_GUID *Guid)
{
  return HaveHob ? &TestHob : NULL;
}

STATIC EFI_STATUS EFIAPI Install (IN OUT EFI_HANDLE *Handle, ...)
{
  Installs++;
  *Handle = (EFI_HANDLE)(UINTN)1;
  return EFI_SUCCESS;
}

STATIC VOID Check (BOOLEAN Condition, CONST char *Name)
{
  Checks++;
  if (!Condition) {
    fprintf (stderr, "FAIL: %s\n", Name);
    exit (1);
  }
}

int main (void)
{
  UINTN Size;
  OCULUS_GO_ENTRY_STATE Out;
  Services.InstallMultipleProtocolInterfaces = Install;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_NOT_FOUND, "missing HOB");
  Check (Installs == 0, "missing state must not install");
  HaveHob = TRUE;
  TestHob.Header.Header.HobLength = sizeof (TestHob);
  TestHob.State.Signature = OCULUS_GO_ENTRY_SIGNATURE;
  TestHob.State.Version = OCULUS_GO_ENTRY_VERSION;
  TestHob.State.Size = sizeof (TestHob.State);
  TestHob.State.Phase = OCULUS_GO_PHASE_PRE_DXE;
  TestHob.State.Fdt = 0x82000000;
  TestHob.State.X1 = 0x12345678;
  TestHob.State.CurrentEl = 8;

  TestHob.Header.Header.HobLength--;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_NOT_FOUND, "truncated HOB");
  TestHob.Header.Header.HobLength++;
  TestHob.State.Signature = 0;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_COMPROMISED_DATA, "bad signature");
  TestHob.State.Signature = OCULUS_GO_ENTRY_SIGNATURE;
  TestHob.State.Version++;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_COMPROMISED_DATA, "future version");
  TestHob.State.Version--;
  TestHob.State.Size--;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_COMPROMISED_DATA, "bad ABI size");
  TestHob.State.Size++;
  TestHob.State.Phase = OCULUS_GO_PHASE_SEC;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_COMPROMISED_DATA, "incomplete SEC state");
  TestHob.State.Phase = OCULUS_GO_PHASE_PRE_DXE;
  Check (TrustMeBroDxeEntry (NULL, NULL) == EFI_SUCCESS, "valid DXE install");
  Check (Installs == 1, "only valid state installs");
  Check (GetState (&mProtocol, NULL, &Out) == EFI_INVALID_PARAMETER, "null size");
  Size = sizeof (Out);
  Check (GetState (NULL, &Size, &Out) == EFI_INVALID_PARAMETER, "invalid protocol pointer");
  Size = 0;
  Check (GetState (&mProtocol, &Size, NULL) == EFI_BUFFER_TOO_SMALL, "size query");
  Check (Size == sizeof (Out), "required size");
  memset (&Out, 0xA5, sizeof (Out));
  Size--;
  Check (GetState (&mProtocol, &Size, &Out) == EFI_BUFFER_TOO_SMALL, "short output");
  Check (Out.Signature == 0xA5A5A5A5, "short output untouched");
  Check (GetState (&mProtocol, &Size, &Out) == EFI_SUCCESS, "state copy");
  Check (Out.Phase == OCULUS_GO_PHASE_DXE, "DXE checkpoint");
  Check (Out.Fdt == 0x82000000 && Out.X1 == 0x12345678 && Out.CurrentEl == 8,
    "original entry fields preserved");
  Check (TestHob.State.Phase == OCULUS_GO_PHASE_PRE_DXE, "source HOB unmodified");
  printf ("PASS: %lu TrustMeBro driver checks\n", (unsigned long)Checks);
  return 0;
}
