/** @file
  Original Go memory handoff. Address provenance: docs/MEMORY_MAP.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiPei.h>
#include <Library/ArmMmuLib.h>
#include <Library/HobLib.h>
#include <Library/PcdLib.h>
#if defined (OCULUS_GO_GOP_MODEL)
#include <Display/Framebuffer.h>
#define GO_MODEL_EXTRA_REGIONS  1
STATIC_ASSERT ((GO_FB_BASE & EFI_PAGE_MASK) == 0, "Unaligned model surface base");
STATIC_ASSERT ((GO_FB_SIZE & EFI_PAGE_MASK) == 0, "Unaligned model surface size");
#else
#define GO_MODEL_EXTRA_REGIONS  0
#endif

#define RAM_ATTRIBUTES (EFI_RESOURCE_ATTRIBUTE_PRESENT | \
  EFI_RESOURCE_ATTRIBUTE_INITIALIZED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_COMBINEABLE | EFI_RESOURCE_ATTRIBUTE_WRITE_THROUGH_CACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_BACK_CACHEABLE | EFI_RESOURCE_ATTRIBUTE_TESTED)

EFI_STATUS
OculusGoInitializeMemory (VOID)
{
  ARM_MEMORY_REGION_DESCRIPTOR  Map[5 + GO_MODEL_EXTRA_REGIONS];
  VOID                         *Tables;
  UINTN                         TableSize;
  RETURN_STATUS                 Result;

  // Only the FD and the selected high RAM window are EFI system memory.
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
#if defined (OCULUS_GO_GOP_MODEL)
  // Only the QEMU graphics profile maps the surface. Keep it out of DXE's
  // general-purpose page allocator even though QEMU backs it with RAM.
  BuildResourceDescriptorHob (EFI_RESOURCE_MEMORY_RESERVED,
    EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED |
    EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE, GO_FB_BASE, GO_FB_SIZE);
  Map[4] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    GO_FB_BASE, GO_FB_BASE, GO_FB_SIZE,
    ARM_MEMORY_REGION_ATTRIBUTE_UNCACHED_UNBUFFERED
  };
#endif
  Map[4 + GO_MODEL_EXTRA_REGIONS] = (ARM_MEMORY_REGION_DESCRIPTOR) { 0, 0, 0, 0 };
  Result = ArmConfigureMmu (Map, &Tables, &TableSize);
  return RETURN_ERROR (Result) ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
