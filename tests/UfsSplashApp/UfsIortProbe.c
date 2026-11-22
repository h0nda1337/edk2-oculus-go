/** Identify the same PCI handle used by the QEMU test and report its firmware's IORT.
    All table pointers originate in the test VM's system configuration table.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsIortProbe.h"
#include <Guid/Acpi.h>
#include <IndustryStandard/IoRemappingTable.h>
#include <Library/BaseLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/PciIo.h>

#define MAX_TABLE_BYTES  (16 * 1024)
#define ROW_BYTES        16

STATIC EFI_STATUS
FindIort (CONST EFI_ACPI_DESCRIPTION_HEADER **Result)
{
  EFI_ACPI_2_0_ROOT_SYSTEM_DESCRIPTION_POINTER *Root;
  EFI_STATUS Status = EfiGetSystemConfigurationTable (&gEfiAcpi20TableGuid, (VOID **)&Root);
  if (EFI_ERROR (Status)) {
    Print (L"UFS-ROUTE ACPI20 UNAVAILABLE %r\r\n", Status);
    return Status;
  }
  if (Root == NULL || Root->Signature != EFI_ACPI_2_0_ROOT_SYSTEM_DESCRIPTION_POINTER_SIGNATURE ||
      Root->Revision < 2 || Root->Length < sizeof (*Root) || Root->Length > SIZE_4KB ||
      CalculateSum8 ((UINT8 *)Root, 20) != 0 || CalculateSum8 ((UINT8 *)Root, Root->Length) != 0 ||
      Root->XsdtAddress == 0) {
    Print (L"UFS-ROUTE INVALID RSDP\r\n");
    return EFI_COMPROMISED_DATA;
  }

  CONST EFI_ACPI_DESCRIPTION_HEADER *Xsdt = (VOID *)(UINTN)Root->XsdtAddress;
  if (Xsdt->Signature != EFI_ACPI_2_0_EXTENDED_SYSTEM_DESCRIPTION_TABLE_SIGNATURE ||
      Xsdt->Length < sizeof (*Xsdt) || Xsdt->Length > MAX_TABLE_BYTES ||
      (Xsdt->Length - sizeof (*Xsdt)) % sizeof (UINT64) != 0 ||
      CalculateSum8 ((UINT8 *)Xsdt, Xsdt->Length) != 0) {
    Print (L"UFS-ROUTE INVALID XSDT\r\n");
    return EFI_COMPROMISED_DATA;
  }

  *Result = NULL;
  CONST UINT8 *Entries = (CONST UINT8 *)(Xsdt + 1);
  UINTN Count = (Xsdt->Length - sizeof (*Xsdt)) / sizeof (UINT64);
  for (UINTN Index = 0; Index < Count; ++Index) {
    UINT64 Address = ReadUnaligned64 ((CONST UINT64 *)(Entries + Index * sizeof (UINT64)));
    if (Address == 0) {
      Print (L"UFS-ROUTE INVALID XSDT ENTRY\r\n");
      return EFI_COMPROMISED_DATA;
    }
    CONST EFI_ACPI_DESCRIPTION_HEADER *Table = (VOID *)(UINTN)Address;
    if (Table->Signature != EFI_ACPI_6_0_IO_REMAPPING_TABLE_SIGNATURE) {
      continue;
    }
    if (*Result != NULL) {
      Print (L"UFS-ROUTE DUPLICATE IORT\r\n");
      return EFI_COMPROMISED_DATA;
    }
    if (Table->Length < sizeof (EFI_ACPI_6_0_IO_REMAPPING_TABLE) ||
        Table->Length > MAX_TABLE_BYTES || CalculateSum8 ((UINT8 *)Table, Table->Length) != 0) {
      Print (L"UFS-ROUTE INVALID IORT\r\n");
      return EFI_COMPROMISED_DATA;
    }
    *Result = Table;
  }
  return EFI_SUCCESS;
}

EFI_STATUS
PrintUfsIort (EFI_HANDLE Controller)
{
  EFI_PCI_IO_PROTOCOL *Pci;
  UINTN Segment, Bus, Device, Function;
  EFI_STATUS Status = gBS->HandleProtocol (Controller, &gEfiPciIoProtocolGuid, (VOID **)&Pci);
  if (!EFI_ERROR (Status)) {
    Status = Pci->GetLocation (Pci, &Segment, &Bus, &Device, &Function);
  }
  if (EFI_ERROR (Status)) {
    Print (L"UFS-ROUTE PCI UNAVAILABLE %r\r\n", Status);
    return Status;
  }
  Print (L"UFS-ROUTE PCI %u %u %u %u\r\n", Segment, Bus, Device, Function);

  CONST EFI_ACPI_DESCRIPTION_HEADER *Iort;
  Status = FindIort (&Iort);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (Iort == NULL) {
    Print (L"UFS-ROUTE NO IORT\r\n");
    return EFI_SUCCESS;
  }
  CONST UINT8 *TableBytes = (CONST UINT8 *)Iort;
  for (UINTN Offset = 0; Offset < Iort->Length; Offset += ROW_BYTES) {
    CHAR16 Text[2 * ROW_BYTES + 1];
    UINTN Length = MIN (ROW_BYTES, Iort->Length - Offset);
    for (UINTN I = 0; I < Length; ++I) {
      UINT8 Byte = TableBytes[Offset + I];
      Text[I * 2] = L"0123456789ABCDEF"[Byte >> 4];
      Text[I * 2 + 1] = L"0123456789ABCDEF"[Byte & 15];
    }
    Text[2 * Length] = 0;
    Print (L"UFS-ROUTE IORT %04x %s\r\n", Offset, Text);
  }
  Print (L"UFS-ROUTE END\r\n");
  return EFI_SUCCESS;
}
