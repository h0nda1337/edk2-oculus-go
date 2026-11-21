## AAVMF ESP modules, kept out of the Pacific platform build and its FV.
## SPDX-License-Identifier: BSD-2-Clause-Patent
[Defines]
  PLATFORM_NAME = PacificUfsTest
  PLATFORM_GUID = fa477e92-83d9-4518-9616-b0793914e6e8
  PLATFORM_VERSION = 0.1
  DSC_SPECIFICATION = 0x0001001B
  OUTPUT_DIRECTORY = Build/PacificUfsTest
  SUPPORTED_ARCHITECTURES = AARCH64
  BUILD_TARGETS = DEBUG
  SKUID_IDENTIFIER = DEFAULT

!include MdePkg/MdeLibs.dsc.inc
[LibraryClasses]
  ArmLib|ArmPkg/Library/ArmLib/ArmBaseLib.inf
  ArmGenericTimerCounterLib|ArmPkg/Library/ArmGenericTimerPhyCounterLib/ArmGenericTimerPhyCounterLib.inf
  BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
  BaseMemoryLib|MdePkg/Library/BaseMemoryLib/BaseMemoryLib.inf
  CpuLib|MdePkg/Library/BaseCpuLib/BaseCpuLib.inf
  DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf
  DevicePathLib|MdePkg/Library/UefiDevicePathLib/UefiDevicePathLib.inf
  MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
  TimerLib|ArmPkg/Library/ArmArchTimerLib/ArmArchTimerLib.inf
  UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
  UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
  UefiDriverEntryPoint|MdePkg/Library/UefiDriverEntryPoint/UefiDriverEntryPoint.inf
  UefiLib|MdePkg/Library/UefiLib/UefiLib.inf
  UefiRuntimeServicesTableLib|MdePkg/Library/UefiRuntimeServicesTableLib/UefiRuntimeServicesTableLib.inf
  GoUfsSplashLib|OculusGoPkg/Library/GoUfsSplashLib/GoUfsSplashLib.inf
  NULL|ArmPkg/Library/CompilerIntrinsicsLib/CompilerIntrinsicsLib.inf
  NULL|MdePkg/Library/BaseStackCheckLib/BaseStackCheckLib.inf

[Components]
  MdeModulePkg/Bus/Pci/UfsPciHcDxe/UfsPciHcDxe.inf
  build/ufs-test-sources/UfsPassThruDxe/UfsPassThruDxe.inf
  tests/UfsSplashApp/UfsSplashApp.inf
  tests/UfsSplashApp/UfsCapacityMap.inf
