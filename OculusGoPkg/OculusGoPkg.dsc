## SPDX-License-Identifier: BSD-2-Clause-Patent
[Defines]
  DEFINE GO_BUILD_FLAVOR  = OculusGo
  PLATFORM_NAME           = OculusGo
  PLATFORM_GUID           = a7e559c7-3e6b-4254-ab21-5549719499af
  PLATFORM_VERSION        = 0.2
  DSC_SPECIFICATION       = 0x0001001B
  OUTPUT_DIRECTORY        = Build/$(GO_BUILD_FLAVOR)
  SUPPORTED_ARCHITECTURES = AARCH64
  BUILD_TARGETS           = DEBUG|RELEASE
  SKUID_IDENTIFIER        = DEFAULT
  FLASH_DEFINITION        = OculusGoPkg/OculusGoPkg.fdf

!include MdePkg/MdeLibs.dsc.inc

[BuildOptions.common]
!if $(GO_BUILD_FLAVOR) == OculusGoSecMem || $(GO_BUILD_FLAVOR) == OculusGoSecStack || $(GO_BUILD_FLAVOR) == OculusGoSecMmu || $(GO_BUILD_FLAVOR) == OculusGoSecDxe || $(GO_BUILD_FLAVOR) == OculusGoDxeMem || $(GO_BUILD_FLAVOR) == OculusGoDxeGcd || $(GO_BUILD_FLAVOR) == OculusGoDxeTables || $(GO_BUILD_FLAVOR) == OculusGoDxeDebug || $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  # Keep the PI handoff calls visible in the ELF used by the measurement.
  GCC:*_*_AARCH64_CC_FLAGS = -march=armv8-a -mgeneral-regs-only -fno-jump-tables -fno-lto -fno-stack-protector
  # GCC5's EDK2 link recipe always forwards an option to the GCC linker
  # plugin. Load it at link time; the measurement's C objects are native.
  GCC:*_*_AARCH64_DLINK2_FLAGS = -flto
!else
  GCC:*_*_AARCH64_CC_FLAGS = -march=armv8-a -fno-jump-tables
!endif

[LibraryClasses.common]
  GoUfsSplashLib|OculusGoPkg/Library/GoUfsSplashLib/GoUfsSplashLib.inf
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  FileHandleLib|MdePkg/Library/UefiFileHandleLib/UefiFileHandleLib.inf
  SortLib|MdeModulePkg/Library/UefiSortLib/UefiSortLib.inf
  UefiHiiServicesLib|MdeModulePkg/Library/UefiHiiServicesLib/UefiHiiServicesLib.inf
  HiiLib|MdeModulePkg/Library/UefiHiiLib/UefiHiiLib.inf
  ShellLib|ShellPkg/Library/UefiShellLib/UefiShellLib.inf
  ShellCommandLib|ShellPkg/Library/UefiShellCommandLib/UefiShellCommandLib.inf
  HandleParsingLib|ShellPkg/Library/UefiHandleParsingLib/UefiHandleParsingLib.inf
  UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
  OrderedCollectionLib|MdePkg/Library/BaseOrderedCollectionRedBlackTreeLib/BaseOrderedCollectionRedBlackTreeLib.inf
  RealTimeClockLib|EmbeddedPkg/Library/VirtualRealTimeClockLib/VirtualRealTimeClockLib.inf
  TimeBaseLib|EmbeddedPkg/Library/TimeBaseLib/TimeBaseLib.inf
  CapsuleLib|MdeModulePkg/Library/DxeCapsuleLibNull/DxeCapsuleLibNull.inf
  TpmMeasurementLib|MdeModulePkg/Library/TpmMeasurementLibNull/TpmMeasurementLibNull.inf
  AuthVariableLib|MdeModulePkg/Library/AuthVariableLibNull/AuthVariableLibNull.inf
  VarCheckLib|MdeModulePkg/Library/VarCheckLib/VarCheckLib.inf
  VariablePolicyHelperLib|MdeModulePkg/Library/VariablePolicyHelperLib/VariablePolicyHelperLib.inf
  VariablePolicyLib|MdeModulePkg/Library/VariablePolicyLib/VariablePolicyLibRuntimeDxe.inf
  VariableFlashInfoLib|MdeModulePkg/Library/BaseVariableFlashInfoLib/BaseVariableFlashInfoLib.inf
  SafeIntLib|MdePkg/Library/BaseSafeIntLib/BaseSafeIntLib.inf
!endif
  ArmDisassemblerLib|ArmPkg/Library/ArmDisassemblerLib/ArmDisassemblerLib.inf
  ArmGenericTimerCounterLib|ArmPkg/Library/ArmGenericTimerPhyCounterLib/ArmGenericTimerPhyCounterLib.inf
  ArmGicArchLib|ArmPkg/Library/ArmGicArchLib/ArmGicArchLib.inf
  ArmGicLib|ArmPkg/Drivers/ArmGic/ArmGicLib.inf
  ArmHvcLib|ArmPkg/Library/ArmHvcLib/ArmHvcLib.inf
  ArmLib|ArmPkg/Library/ArmLib/ArmBaseLib.inf
  ArmMmuLib|ArmPkg/Library/ArmMmuLib/ArmMmuBaseLib.inf
  ArmSmcLib|ArmPkg/Library/ArmSmcLib/ArmSmcLib.inf
  BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
  BaseMemoryLib|MdePkg/Library/BaseMemoryLib/BaseMemoryLib.inf
  BaseSynchronizationLib|MdePkg/Library/BaseSynchronizationLib/BaseSynchronizationLib.inf
  CacheMaintenanceLib|ArmPkg/Library/ArmCacheMaintenanceLib/ArmCacheMaintenanceLib.inf
  CompilerIntrinsicsLib|ArmPkg/Library/CompilerIntrinsicsLib/CompilerIntrinsicsLib.inf
  CpuExceptionHandlerLib|ArmPkg/Library/ArmExceptionLib/ArmExceptionLib.inf
  CpuLib|MdePkg/Library/BaseCpuLib/BaseCpuLib.inf
  DebugAgentLib|MdeModulePkg/Library/DebugAgentLibNull/DebugAgentLibNull.inf
  DebugLib|MdePkg/Library/BaseDebugLibSerialPort/BaseDebugLibSerialPort.inf
  DebugPrintErrorLevelLib|MdePkg/Library/BaseDebugPrintErrorLevelLib/BaseDebugPrintErrorLevelLib.inf
  DefaultExceptionHandlerLib|ArmPkg/Library/DefaultExceptionHandlerLib/DefaultExceptionHandlerLib.inf
  DevicePathLib|MdePkg/Library/UefiDevicePathLib/UefiDevicePathLib.inf
  DxeServicesLib|MdePkg/Library/DxeServicesLib/DxeServicesLib.inf
  DxeServicesTableLib|MdePkg/Library/DxeServicesTableLib/DxeServicesTableLib.inf
  ExtractGuidedSectionLib|MdePkg/Library/DxeExtractGuidedSectionLib/DxeExtractGuidedSectionLib.inf
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
  IoLib|MdePkg/Library/BaseIoLibIntrinsic/BaseIoLibIntrinsic.inf
  LzmaDecompressLib|MdeModulePkg/Library/LzmaCustomDecompressLib/LzmaCustomDecompressLib.inf
  MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
  PcdLib|MdePkg/Library/DxePcdLib/DxePcdLib.inf
  PeCoffExtraActionLib|MdePkg/Library/BasePeCoffExtraActionLibNull/BasePeCoffExtraActionLibNull.inf
  PeCoffGetEntryPointLib|MdePkg/Library/BasePeCoffGetEntryPointLib/BasePeCoffGetEntryPointLib.inf
  PeCoffLib|MdePkg/Library/BasePeCoffLib/BasePeCoffLib.inf
  PerformanceLib|MdePkg/Library/BasePerformanceLibNull/BasePerformanceLibNull.inf
  PrePiHobListPointerLib|ArmPlatformPkg/Library/PrePiHobListPointerLib/PrePiHobListPointerLib.inf
  PrePiLib|EmbeddedPkg/Library/PrePiLib/PrePiLib.inf
  PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
  ReportStatusCodeLib|MdePkg/Library/BaseReportStatusCodeLibNull/BaseReportStatusCodeLibNull.inf
  ResetSystemLib|ArmPkg/Library/ArmSmcPsciResetSystemLib/ArmSmcPsciResetSystemLib.inf
  SecurityManagementLib|MdeModulePkg/Library/DxeSecurityManagementLib/DxeSecurityManagementLib.inf
!if $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  SerialPortLib|ArmPlatformPkg/Library/PL011SerialPortLib/PL011SerialPortLib.inf
  PL011UartLib|ArmPlatformPkg/Library/PL011UartLib/PL011UartLib.inf
  PL011UartClockLib|ArmPlatformPkg/Library/PL011UartClockLib/PL011UartClockLib.inf
!else
  SerialPortLib|MdePkg/Library/BaseSerialPortLibNull/BaseSerialPortLibNull.inf
!endif
  SynchronizationLib|MdePkg/Library/BaseSynchronizationLib/BaseSynchronizationLib.inf
  TimerLib|ArmPkg/Library/ArmArchTimerLib/ArmArchTimerLib.inf
  UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
  UefiDecompressLib|MdePkg/Library/BaseUefiDecompressLib/BaseUefiDecompressLib.inf
  UefiDriverEntryPoint|MdePkg/Library/UefiDriverEntryPoint/UefiDriverEntryPoint.inf
  UefiLib|MdePkg/Library/UefiLib/UefiLib.inf
  UefiRuntimeLib|MdePkg/Library/UefiRuntimeLib/UefiRuntimeLib.inf
  UefiRuntimeServicesTableLib|MdePkg/Library/UefiRuntimeServicesTableLib/UefiRuntimeServicesTableLib.inf
  NULL|ArmPkg/Library/CompilerIntrinsicsLib/CompilerIntrinsicsLib.inf
  NULL|MdePkg/Library/BaseStackCheckLib/BaseStackCheckLib.inf

[LibraryClasses.common.SEC]
  ArmGicArchLib|ArmPkg/Library/ArmGicArchSecLib/ArmGicArchSecLib.inf
  ExtractGuidedSectionLib|EmbeddedPkg/Library/PrePiExtractGuidedSectionLib/PrePiExtractGuidedSectionLib.inf
  HobLib|EmbeddedPkg/Library/PrePiHobLib/PrePiHobLib.inf
  MemoryAllocationLib|EmbeddedPkg/Library/PrePiMemoryAllocationLib/PrePiMemoryAllocationLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf

[LibraryClasses.common.DXE_CORE]
  DxeCoreEntryPoint|MdePkg/Library/DxeCoreEntryPoint/DxeCoreEntryPoint.inf
  HobLib|MdePkg/Library/DxeCoreHobLib/DxeCoreHobLib.inf
  MemoryAllocationLib|MdeModulePkg/Library/DxeCoreMemoryAllocationLib/DxeCoreMemoryAllocationLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf

[PcdsFeatureFlag.common]
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  gEfiMdeModulePkgTokenSpaceGuid.PcdHiiOsRuntimeSupport|FALSE
  gEfiShellPkgTokenSpaceGuid.PcdShellForceConsole|TRUE
!endif
!if $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  gEfiMdeModulePkgTokenSpaceGuid.PcdDevicePathSupportDevicePathToText|FALSE
  gEfiMdeModulePkgTokenSpaceGuid.PcdDevicePathSupportDevicePathFromText|FALSE
!endif
  gArmTokenSpaceGuid.PcdCpuDxeProduceDebugSupport|TRUE
  gArmTokenSpaceGuid.PcdDebuggerExceptionSupport|FALSE
  gArmTokenSpaceGuid.PcdArmGicV3WithV2Legacy|FALSE
  gEmbeddedTokenSpaceGuid.PcdPrePiProduceMemoryTypeInformationHob|FALSE

[PcdsFixedAtBuild.common]
  # Device evidence and staging limitations: docs/MEMORY_MAP.md.
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80480000
  gArmTokenSpaceGuid.PcdSystemMemorySize|0x01000000
  gOculusGoPkgTokenSpaceGuid.PcdMemoryPoolBase|0x80480000
  gOculusGoPkgTokenSpaceGuid.PcdMemoryPoolSize|0x01000000
!else
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x91700000
  gArmTokenSpaceGuid.PcdSystemMemorySize|0x0E800000
  gOculusGoPkgTokenSpaceGuid.PcdMemoryPoolBase|0x94000000
  gOculusGoPkgTokenSpaceGuid.PcdMemoryPoolSize|0x04000000
!endif
  gOculusGoPkgTokenSpaceGuid.PcdStackSize|0x00040000
  gOculusGoPkgTokenSpaceGuid.PcdSecVisualDiagnostic|FALSE
  gEmbeddedTokenSpaceGuid.PcdPrePiCpuIoSize|0
!if $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  gEfiMdeModulePkgTokenSpaceGuid.PcdSerialRegisterBase|0x09000000
  gArmTokenSpaceGuid.PcdGicDistributorBase|0x08000000
  gArmTokenSpaceGuid.PcdGicRedistributorsBase|0x080A0000
  gArmTokenSpaceGuid.PcdArmArchTimerFreqInHz|0
!else
  gEfiMdeModulePkgTokenSpaceGuid.PcdSerialRegisterBase|0
  gArmTokenSpaceGuid.PcdGicDistributorBase|0x09BC0000
  gArmTokenSpaceGuid.PcdGicRedistributorsBase|0x09C00000
  gArmTokenSpaceGuid.PcdGicInterruptInterfaceBase|0
  gArmTokenSpaceGuid.PcdArmArchTimerFreqInHz|19200000
!endif
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  gEfiMdeModulePkgTokenSpaceGuid.PcdEmuVariableNvModeEnable|TRUE
  gEfiMdeModulePkgTokenSpaceGuid.PcdFirmwareRevision|0x00000002
  gEfiShellPkgTokenSpaceGuid.PcdShellDefaultDelay|0
  gEfiShellPkgTokenSpaceGuid.PcdShellSupportLevel|2
  gEfiShellPkgTokenSpaceGuid.PcdShellLibAutoInitialize|FALSE
!endif
  gArmTokenSpaceGuid.PcdArmArchTimerSecIntrNum|29
  gArmTokenSpaceGuid.PcdArmArchTimerIntrNum|30
  gArmTokenSpaceGuid.PcdArmArchTimerVirtIntrNum|27
  gArmTokenSpaceGuid.PcdArmArchTimerHypIntrNum|26
  gArmTokenSpaceGuid.PcdVFPEnabled|1
  gEfiMdeModulePkgTokenSpaceGuid.PcdFirmwareVendor|L"OculusGo UEFI"
  gEfiMdeModulePkgTokenSpaceGuid.PcdFirmwareVersionString|L"DIRECT-ENTRY-OFFLINE-ONLY"
  gEfiMdeModulePkgTokenSpaceGuid.PcdResetOnMemoryTypeInformationChange|FALSE
!if $(GO_BUILD_FLAVOR) == OculusGoDxeTables || $(GO_BUILD_FLAVOR) == OculusGoDxeDebug || $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x2F
!else
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x0F
!endif
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x800000c6
!else
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0xFFFFFFFF
!endif
  gEfiMdePkgTokenSpaceGuid.PcdDebugClearMemoryValue|0xAF
  gEfiMdePkgTokenSpaceGuid.PcdMaximumAsciiStringLength|1000000
  gEfiMdePkgTokenSpaceGuid.PcdMaximumUnicodeStringLength|1000000
  gEfiMdePkgTokenSpaceGuid.PcdMaximumLinkedListLength|1000000
  gEfiMdePkgTokenSpaceGuid.PcdPerformanceLibraryPropertyMask|0
  gEfiMdePkgTokenSpaceGuid.PcdReportStatusCodePropertyMask|0

[Components.common]
!if $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  OculusGoPkg/Applications/ConsoleProbe/ConsoleProbe.inf {
    <LibraryClasses>
      UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
      PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  }
!endif
!if $(GO_BUILD_FLAVOR) == OculusGoSecDxe || $(GO_BUILD_FLAVOR) == OculusGoDxeMem || $(GO_BUILD_FLAVOR) == OculusGoDxeGcd || $(GO_BUILD_FLAVOR) == OculusGoDxeTables || $(GO_BUILD_FLAVOR) == OculusGoDxeDebug || $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
!if $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf {
    <LibraryClasses>
      PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  }
!endif
!if $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
  OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopText.inf {
    <LibraryClasses>
      PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  }
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeGop
  OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopDisplay.inf {
    <LibraryClasses>
      PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  }
!endif
  OculusGoPkg/SecMmu/SecDxe.inf {
    <BuildOptions>
!if $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_MEMORY=1 -DOCULUS_GO_DXE_GCD=1 -DOCULUS_GO_DXE_DEBUG=1 -DOCULUS_GO_DXE_DISPATCH=1 -DOCULUS_GO_DXE_GOP=1
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_MEMORY=1 -DOCULUS_GO_DXE_GCD=1 -DOCULUS_GO_DXE_DEBUG=1 -DOCULUS_GO_DXE_DISPATCH=1
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDebug
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_MEMORY=1 -DOCULUS_GO_DXE_GCD=1 -DOCULUS_GO_DXE_DEBUG=1
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeGcd || $(GO_BUILD_FLAVOR) == OculusGoDxeTables
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_MEMORY=1 -DOCULUS_GO_DXE_GCD=1
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeMem
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_MEMORY=1
!else
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_DXE=1
!endif
!if $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText || $(GO_BUILD_FLAVOR) == OculusGoDxeApp
      GCC:*_*_AARCH64_PP_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_DEBUG=1 -DOCULUS_GO_DXE_GOP=1
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDebug || $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch
      GCC:*_*_AARCH64_PP_FLAGS = -DOCULUS_GO_SEC_DXE=1 -DOCULUS_GO_DXE_DEBUG=1
!else
      GCC:*_*_AARCH64_PP_FLAGS = -DOCULUS_GO_SEC_DXE=1
!endif
  }
  MdeModulePkg/Core/Dxe/DxeMain.inf {
    <LibraryClasses>
!if $(GO_BUILD_FLAVOR) == OculusGoDxeApp
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/AppCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeText
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/TextCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeGop
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/GopCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/DispatchCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDebug
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/DebugCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeTables
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/TablesCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeGcd
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/GcdCheckpoint.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeMem
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/MemoryCheckpoint.inf
!else
      DebugAgentLib|OculusGoPkg/DxeCheckpoint/DxeCheckpoint.inf
!endif
    <BuildOptions>
!if $(GO_BUILD_FLAVOR) == OculusGoDxeApp
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices,--wrap=CoreInitializeGcdServices,--wrap=ProcessLibraryConstructorList,--wrap=CoreInitializeDebugImageInfoTable,--wrap=CoreNewDebugImageInfoEntry,--wrap=CoreStartImage,--wrap=CoreDispatcher,--wrap=UnprotectUefiImage
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDispatch || $(GO_BUILD_FLAVOR) == OculusGoDxeGop || $(GO_BUILD_FLAVOR) == OculusGoDxeText
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices,--wrap=CoreInitializeGcdServices,--wrap=ProcessLibraryConstructorList,--wrap=CoreInitializeDebugImageInfoTable,--wrap=CoreNewDebugImageInfoEntry,--wrap=CoreStartImage,--wrap=CoreDispatcher
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeDebug
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices,--wrap=CoreInitializeGcdServices,--wrap=ProcessLibraryConstructorList,--wrap=CoreInitializeDebugImageInfoTable,--wrap=CoreNewDebugImageInfoEntry
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeTables
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices,--wrap=CoreInitializeGcdServices,--wrap=ProcessLibraryConstructorList,--wrap=CoreInitializeDebugImageInfoTable
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeGcd
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices,--wrap=CoreInitializeGcdServices
!elseif $(GO_BUILD_FLAVOR) == OculusGoDxeMem
      GCC:*_*_AARCH64_DLINK_FLAGS = -Wl,--wrap=CoreInitializeImageServices
!endif
      # GCC 14 diagnoses Prot in upstream CoreOpenProtocol. Retain its warning.
      GCC:*_*_AARCH64_CC_FLAGS = -Wno-error=maybe-uninitialized
  }
!elseif $(GO_BUILD_FLAVOR) == OculusGoSecMmu
  OculusGoPkg/SecMmu/SecMmu.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoSecStack
  OculusGoPkg/SecMem/SecStack.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoSecMem
  OculusGoPkg/SecMem/SecMem.inf
!else
!if $(GO_BUILD_FLAVOR) == OculusGoGopModel
  OculusGoPkg/PrePi/PrePi.inf {
    <BuildOptions>
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_GOP_MODEL=1
  }
  OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopDxe.inf
!elseif $(GO_BUILD_FLAVOR) == OculusGoSecC
  OculusGoPkg/PrePi/PrePi.inf {
    <BuildOptions>
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_SEC_C=1
      GCC:*_*_AARCH64_PP_FLAGS = -DOCULUS_GO_SEC_C=1
  }
!else
!if $(GO_BUILD_FLAVOR) == OculusGo || $(GO_BUILD_FLAVOR) == OculusGoShellQemu
  OculusGoPkg/PrePi/PrePi.inf {
    <BuildOptions>
      GCC:*_*_AARCH64_CC_FLAGS = -DOCULUS_GO_BOOT_CONSOLE=1
      GCC:*_*_AARCH64_PP_FLAGS = -DOCULUS_GO_BOOT_CONSOLE=1
  }
  MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopText.inf
  MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
  MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
  MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  OculusGoPkg/Drivers/GoBdsDxe/GoBdsDxe.inf
  ShellPkg/Application/Shell/Shell.inf {
    <LibraryClasses>
      NULL|ShellPkg/Library/UefiShellLevel1CommandsLib/UefiShellLevel1CommandsLib.inf
      NULL|ShellPkg/Library/UefiShellLevel2CommandsLib/UefiShellLevel2CommandsLib.inf
  }
!else
  OculusGoPkg/PrePi/PrePi.inf
!endif
!endif
  MdeModulePkg/Core/Dxe/DxeMain.inf {
    <LibraryClasses>
      NULL|MdeModulePkg/Library/DxeCrc32GuidedSectionExtractLib/DxeCrc32GuidedSectionExtractLib.inf
      NULL|MdeModulePkg/Library/LzmaCustomDecompressLib/LzmaCustomDecompressLib.inf
  }
  MdeModulePkg/Universal/PCD/Dxe/Pcd.inf {
    <LibraryClasses>
      PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  }
  ArmPkg/Drivers/ArmGic/ArmGicDxe.inf
  ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  ArmPkg/Drivers/TimerDxe/TimerDxe.inf
  EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf
  MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf
  OculusGoPkg/Drivers/TrustMeBroDxe/TrustMeBroDxe.inf
!endif
