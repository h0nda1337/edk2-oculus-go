/** @file
  Original Go memory handoff. Address provenance: docs/MEMORY_MAP.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiPei.h>
#include <Library/ArmMmuLib.h>
#include <Library/HobLib.h>
#include <Library/PcdLib.h>

#define RAM_ATTRIBUTES (EFI_RESOURCE_ATTRIBUTE_PRESENT | \
  EFI_RESOURCE_ATTRIBUTE_INITIALIZED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_COMBINEABLE | EFI_RESOURCE_ATTRIBUTE_WRITE_THROUGH_CACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_BACK_CACHEABLE | EFI_RESOURCE_ATTRIBUTE_TESTED)

EFI_STATUS
OculusGoInitializeMemory (VOID)
{
  ARM_MEMORY_REGION_DESCRIPTOR  Map[5];
  VOID                         *Tables;
  UINTN                         TableSize;
  RETURN_STATUS                 Result;

  // Deliberately do not expose the low splash area, FDT or secure carve-outs.
  BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, RAM_ATTRIBUTES,
    FixedPcdGet64 (PcdSystemMemoryBase), FixedPcdGet64 (PcdSystemMemorySize));
  BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, RAM_ATTRIBUTES,
    FixedPcdGet64 (PcdFdBaseAddress), FixedPcdGet32 (PcdFdSize));
  BuildMemoryAllocationHob (FixedPcdGet64 (PcdFdBaseAddress),
    FixedPcdGet32 (PcdFdSize), EfiBootServicesCode);

  Map[0] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdFdBaseAddress), FixedPcdGet64 (PcdFdBaseAddress),
    FixedPcdGet32 (PcdFdSize), ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK
  };
  Map[1] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdSystemMemoryBase), FixedPcdGet64 (PcdSystemMemoryBase),
    FixedPcdGet64 (PcdSystemMemorySize), ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK
  };
  Map[2] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    0x09BC0000, 0x09BC0000, 0x10000, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
  };
  Map[3] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    0x09C00000, 0x09C00000, 0x100000, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
  };
  Map[4] = (ARM_MEMORY_REGION_DESCRIPTOR) { 0, 0, 0, 0 };
  Result = ArmConfigureMmu (Map, &Tables, &TableSize);
  return RETURN_ERROR (Result) ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
