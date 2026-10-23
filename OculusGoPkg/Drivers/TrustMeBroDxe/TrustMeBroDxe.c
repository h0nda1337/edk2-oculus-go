/** @file
  Publish the original TrustMeBro diagnostic protocol from a validated HOB.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiDxe.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/TrustMeBro.h>

STATIC OCULUS_GO_ENTRY_STATE mState;

STATIC EFI_STATUS EFIAPI
GetState (
  IN CONST OCULUS_GO_TRUST_ME_BRO_PROTOCOL *This,
  IN OUT UINTN *Size,
  OUT OCULUS_GO_ENTRY_STATE *State OPTIONAL
  );

STATIC OCULUS_GO_TRUST_ME_BRO_PROTOCOL mProtocol = {
  OCULUS_GO_TRUST_ME_BRO_REVISION,
  GetState
};

STATIC EFI_STATUS EFIAPI
GetState (
  IN CONST OCULUS_GO_TRUST_ME_BRO_PROTOCOL *This,
  IN OUT UINTN *Size,
  OUT OCULUS_GO_ENTRY_STATE *State OPTIONAL
  )
{
  if ((This != &mProtocol) || (Size == NULL)) {
    return EFI_INVALID_PARAMETER;
  }
  if ((*Size < sizeof (mState)) || (State == NULL)) {
    *Size = sizeof (mState);
    return EFI_BUFFER_TOO_SMALL;
  }
  CopyMem (State, &mState, sizeof (mState));
  *Size = sizeof (mState);
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
TrustMeBroDxeEntry (IN EFI_HANDLE ImageHandle, IN EFI_SYSTEM_TABLE *SystemTable)
{
  VOID        *Hob;
  EFI_HANDLE   Handle;

  Hob = GetFirstGuidHob (&gOculusGoEntryHobGuid);
  if ((Hob == NULL) || (GET_GUID_HOB_DATA_SIZE (Hob) != sizeof (mState))) {
    return EFI_NOT_FOUND;
  }
  CopyMem (&mState, GET_GUID_HOB_DATA (Hob), sizeof (mState));
  if ((mState.Signature != OCULUS_GO_ENTRY_SIGNATURE) ||
      (mState.Version != OCULUS_GO_ENTRY_VERSION) ||
      (mState.Size != sizeof (mState)) ||
      (mState.Phase != OCULUS_GO_PHASE_PRE_DXE)) {
    return EFI_COMPROMISED_DATA;
  }
  mState.Phase = OCULUS_GO_PHASE_DXE;
  Handle = NULL;
  DEBUG ((DEBUG_INFO, "EDK2 IS RUNNING ON OCULUS GO: TrustMeBro DXE\n"));
  return gBS->InstallMultipleProtocolInterfaces (&Handle,
    &gOculusGoTrustMeBroProtocolGuid, &mProtocol, NULL);
}
