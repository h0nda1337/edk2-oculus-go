/** @file
  Synchronous capacity observation on an EDK2 UFS pass-through controller.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#ifndef GO_UFS_CAPACITY_PROTOCOL_H_
#define GO_UFS_CAPACITY_PROTOCOL_H_

#include <Protocol/ScsiPassThruExt.h>

typedef struct _GO_UFS_CAPACITY_PROTOCOL GO_UFS_CAPACITY_PROTOCOL;

/**
  Submit READ CAPACITY(10) for LUN 4. The CDB must request the complete
  capacity, with an aligned eight-byte inbound buffer and no outbound data.
  Packet receives the usual SCSI target status, length and sense information.
  On EFI_SUCCESS, DmaAddress is the bus address supplied to the PRDT for
  this completed transfer. Zero is a valid success value. The address is
  diagnostic only: the transport has already released its mapping.
  On failure DmaAddress is cleared.
**/
typedef
EFI_STATUS
(EFIAPI *GO_UFS_READ_CAPACITY)(
  IN     GO_UFS_CAPACITY_PROTOCOL                    *This,
  IN     UINT8                                       *Target,
  IN OUT EFI_EXT_SCSI_PASS_THRU_SCSI_REQUEST_PACKET  *Packet,
  OUT    EFI_PHYSICAL_ADDRESS                        *DmaAddress
  );

struct _GO_UFS_CAPACITY_PROTOCOL {
  GO_UFS_READ_CAPACITY  ReadCapacity;
};

extern EFI_GUID  gGoUfsCapacityProtocolGuid;

#endif
