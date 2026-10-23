/** @file
  Original Oculus Go boot-services diagnostic interface.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#ifndef OCULUS_GO_TRUST_ME_BRO_PROTOCOL_H_
#define OCULUS_GO_TRUST_ME_BRO_PROTOCOL_H_

#include <Uefi.h>

#define OCULUS_GO_TRUST_ME_BRO_PROTOCOL_GUID \
  { 0x4b7e5f2a, 0x196d, 0x47cc, { 0xb8, 0x1f, 0x54, 0x91, 0x4a, 0x3e, 0x9d, 0x70 } }
#define OCULUS_GO_TRUST_ME_BRO_REVISION  0x00010000ULL
#define OCULUS_GO_ENTRY_SIGNATURE       SIGNATURE_32 ('T', 'M', 'B', '1')
#define OCULUS_GO_ENTRY_VERSION         1
#define OCULUS_GO_PHASE_SEC             1
#define OCULUS_GO_PHASE_MMU             2
#define OCULUS_GO_PHASE_PRE_DXE         3
#define OCULUS_GO_PHASE_DXE             4

typedef struct {
  UINT32  Signature;
  UINT16  Version;
  UINT16  Size;
  UINT64  Fdt;
  UINT64  X1;
  UINT64  X2;
  UINT64  X3;
  UINT64  CurrentEl;
  UINT64  Mpidr;
  UINT64  ActiveSctlr;
  UINT64  Daif;
  UINT64  IncomingSp;
  UINT64  IncomingLr;
  UINT32  Phase;
  UINT32  Reserved;
} OCULUS_GO_ENTRY_STATE;

STATIC_ASSERT (sizeof (OCULUS_GO_ENTRY_STATE) == 96, "SEC state ABI size");
STATIC_ASSERT (OFFSET_OF (OCULUS_GO_ENTRY_STATE, Fdt) == 8, "SEC FDT offset");
STATIC_ASSERT (OFFSET_OF (OCULUS_GO_ENTRY_STATE, Phase) == 88, "SEC phase offset");

typedef struct _OCULUS_GO_TRUST_ME_BRO_PROTOCOL OCULUS_GO_TRUST_ME_BRO_PROTOCOL;

/**
  Copy the latest diagnostic state. The interface is valid only until
  ExitBootServices. Size is in/out; a NULL State is a valid size query.
  EFI_BUFFER_TOO_SMALL sets Size to sizeof (OCULUS_GO_ENTRY_STATE).
  The entry fields describe the initial SEC entry before any C/library call.
**/
typedef
EFI_STATUS
(EFIAPI *OCULUS_GO_TRUST_ME_BRO_GET_STATE)(
  IN CONST OCULUS_GO_TRUST_ME_BRO_PROTOCOL  *This,
  IN OUT UINTN                           *Size,
  OUT OCULUS_GO_ENTRY_STATE               *State OPTIONAL
  );

struct _OCULUS_GO_TRUST_ME_BRO_PROTOCOL {
  UINT64                              Revision;
  OCULUS_GO_TRUST_ME_BRO_GET_STATE     GetState;
};

extern EFI_GUID gOculusGoTrustMeBroProtocolGuid;
extern EFI_GUID gOculusGoEntryHobGuid;

#endif
