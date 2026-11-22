/** Read the legacy UFS queues after their former owner releases the controller.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Library/BaseMemoryLib.h>
#include <Library/GoUfsHandoffLib.h>
#include <Library/IoLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/PacificUfsHandoff.h>

enum {
  UfsVer = 0x08, UfsHce = 0x34,
  UfsUtrlba = 0x50, UfsUtrlbau = 0x54, UfsUtrldbr = 0x58, UfsUtrlrsr = 0x60,
  UfsUtmrlba = 0x70, UfsUtmrlbau = 0x74, UfsUtmrldbr = 0x78, UfsUtmrlrsr = 0x80
};

typedef struct {
  UINT32 Enabled;
  UINT32 Running;
  UINT32 TransferBaseLow;
  UINT32 TransferBaseHigh;
  UINT32 TaskBaseLow;
  UINT32 TaskBaseHigh;
} GO_UFS_QUEUE_STATE;

STATIC BOOLEAN
ReadIdleState (UINTN Base, GO_UFS_QUEUE_STATE *State)
{
  State->Enabled = MmioRead32 (Base + UfsHce);
  if (State->Enabled > 1) {
    return FALSE;
  }

  // Accept the stopped pair and the enabled, running pair seen at SEC entry.
  // A partially stopped pair has no observed handoff contract on this board.
  State->Running = MmioRead32 (Base + UfsUtrlrsr);
  if (State->Running > State->Enabled || MmioRead32 (Base + UfsUtmrlrsr) != State->Running ||
      MmioRead32 (Base + UfsUtrldbr) != 0 || MmioRead32 (Base + UfsUtmrldbr) != 0) {
    return FALSE;
  }

  if (State->Running != 0) {
    // Watch for reprogramming during handoff. Old list addresses belong to
    // the previous owner and are never dereferenced or used for a request.
    State->TransferBaseLow = MmioRead32 (Base + UfsUtrlba);
    State->TransferBaseHigh = MmioRead32 (Base + UfsUtrlbau);
    State->TaskBaseLow = MmioRead32 (Base + UfsUtmrlba);
    State->TaskBaseHigh = MmioRead32 (Base + UfsUtmrlbau);
    if (((State->TransferBaseLow | State->TaskBaseLow) & 0x3ff) != 0 ||
        (State->TransferBaseLow | State->TransferBaseHigh) == 0 ||
        (State->TaskBaseLow | State->TaskBaseHigh) == 0 ||
        (State->TransferBaseLow == State->TaskBaseLow && State->TransferBaseHigh == State->TaskBaseHigh)) {
      return FALSE;
    }
  }
  return TRUE;
}

EFI_STATUS
GoUfsCheckHandoff (EFI_HANDLE Controller, UINTN MmioBase, UINT32 ExpectedVersion)
{
  if (Controller == NULL || MmioBase == 0 || (MmioBase & 3) != 0 ||
      MmioBase > MAX_UINTN - UfsUtmrlrsr || ExpectedVersion == 0 || ExpectedVersion == MAX_UINT32) {
    return EFI_INVALID_PARAMETER;
  }
  GO_PACIFIC_UFS_HANDOFF_PROTOCOL *Handoff;
  EFI_STATUS Status = gBS->HandleProtocol (Controller, &gGoPacificUfsHandoffProtocolGuid, (VOID **)&Handoff);
  if (Status != EFI_SUCCESS || Handoff == NULL || Handoff->ConfirmReleased == NULL) {
    return EFI_NOT_READY;
  }
  Status = Handoff->ConfirmReleased (Handoff, Controller);
  if (Status != EFI_SUCCESS) {
    return EFI_ERROR (Status) ? Status : EFI_NOT_READY;
  }
  if (MmioRead32 (MmioBase + UfsVer) != ExpectedVersion) {
    return EFI_UNSUPPORTED;
  }

  GO_UFS_QUEUE_STATE First = { 0 }, Second = { 0 };
  if (!ReadIdleState (MmioBase, &First) || !ReadIdleState (MmioBase, &Second) ||
      CompareMem (&First, &Second, sizeof (First)) != 0) {
    return EFI_NOT_READY;
  }
  return EFI_SUCCESS;
}
