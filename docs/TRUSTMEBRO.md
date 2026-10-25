# TrustMeBro protocol v1

| Field | Value |
| --- | --- |
| Public header | `OculusGoPkg/Include/Protocol/TrustMeBro.h` |
| C type | `OCULUS_GO_TRUST_ME_BRO_PROTOCOL` |
| GUID symbol | `gOculusGoTrustMeBroProtocolGuid` |
| GUID | `4b7e5f2a-196d-47cc-b81f-54914a3e9d70` |
| Revision | `0x00010000` |
| Lifetime | Boot services, before ExitBootServices |
| Method | `GetState(This, Size, State)` using EFIAPI |

Locate the interface with standard UEFI LocateProtocol. GetState copies a
96-byte versioned `OCULUS_GO_ENTRY_STATE`. A NULL output or short buffer returns
EFI_BUFFER_TOO_SMALL and supplies the required size. A NULL size pointer or
wrong interface pointer returns EFI_INVALID_PARAMETER. A valid copy returns
EFI_SUCCESS. The interface performs no device or storage access.

The state includes signature/version/size, original x0-x3, CurrentEL, MPIDR,
active SCTLR, incoming DAIF, SP/LR, phase and reserved field. SEC records the
arguments before calling an EDK2 library. After constructing the HOB list it
copies that private stack record into a GUID HOB. The driver validates HOB
length, signature, version, state size and pre-DXE phase before installation.
It reports phase 4 only after entering DXE. No PEI core is claimed by this
direct-to-DXE flow; phase 3 denotes the pre-DXE handoff.

Validation: 19 checks of the real C driver with mocked boot services; the
actual FD also reaches real DXE in QEMU EL1/EL2, installs the protocol, finds
it through real LocateProtocol and executes size-query/GetState calls. The
returned phase is 4 and original sentinel arguments survive. This is
emulator evidence; a corresponding headset observation is still pending.
