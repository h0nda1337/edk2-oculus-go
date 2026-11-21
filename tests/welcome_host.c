/** Exercise the boot animation through its GOP, pool and clock contracts.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#undef NULL
#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/TimerLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include "Welcome.h"

STATIC EFI_BOOT_SERVICES Services;
EFI_BOOT_SERVICES *gBS = &Services;
STATIC UINT64 Now;
STATIC UINTN Calls, FailBlt, Pools;
STATIC BOOLEAN FailPool;

UINT64 EFIAPI GetPerformanceCounter (VOID) { return Now; }
UINT64 EFIAPI GetPerformanceCounterProperties (UINT64 *A, UINT64 *B) { return 1000000; }
UINT64 EFIAPI GetTimeInNanoSecond (UINT64 Ticks) { return Ticks * 1000; }
STATIC EFI_STATUS EFIAPI Stall (UINTN Us) { Now += Us; return EFI_SUCCESS; }
VOID *EFIAPI CopyMem (VOID *D, CONST VOID *S, UINTN N) { return memcpy (D, S, N); }
VOID *EFIAPI AllocatePool (UINTN N) {
  if (FailPool) { return NULL; }
  ++Pools;
  return malloc (N);
}
VOID *EFIAPI AllocateZeroPool (UINTN N) {
  VOID *P = AllocatePool (N);
  if (P != NULL) { memset (P, 0, N); }
  return P;
}
VOID EFIAPI FreePool (VOID *P) { assert (Pools == 1); --Pools; free (P); }

STATIC EFI_STATUS EFIAPI
Present (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop, EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Data,
         EFI_GRAPHICS_OUTPUT_BLT_OPERATION Op, UINTN Sx, UINTN Sy, UINTN X, UINTN Y,
         UINTN Width, UINTN Height, UINTN Stride)
{
  assert (Data != NULL && Op == EfiBltBufferToVideo && Sx == 0 && Sy == 0 && Stride == 0);
  assert (Width == 400 && Height == 352 && X == 520 && Y == 464 + 1280 * (Calls % 2));
  ++Calls;
  return Calls == FailBlt ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}

int main (void)
{
  EFI_GRAPHICS_OUTPUT_MODE_INFORMATION Info = {0};
  EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE Mode = {0};
  EFI_GRAPHICS_OUTPUT_PROTOCOL Gop = {0};
  Services.Stall = Stall;
  Gop.Mode = &Mode;
  Gop.Blt = Present;
  Mode.Info = &Info;
  assert (GoPlayWelcome (&Gop, NULL) == EFI_UNSUPPORTED && Calls == 0);
  Info.HorizontalResolution = 1440;
  Info.VerticalResolution = 2560;
  FailPool = TRUE;
  assert (GoPlayWelcome (&Gop, NULL) == EFI_OUT_OF_RESOURCES && Pools == 0 && Calls == 0);
  FailPool = FALSE;
  FailBlt = 2;
  assert (GoPlayWelcome (&Gop, NULL) == EFI_DEVICE_ERROR && Pools == 0 && Calls == 2);
  FailBlt = Calls = 0;
  assert (GoPlayWelcome (&Gop, NULL) == EFI_SUCCESS && Pools == 0 && Now == 8900000);
  assert (Calls == 2 * ((8900 + 32) / 33));
  return 0;
}
