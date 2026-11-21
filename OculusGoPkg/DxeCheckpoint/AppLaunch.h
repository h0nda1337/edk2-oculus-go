/** SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef OCULUS_GO_APP_LAUNCH_H_
#define OCULUS_GO_APP_LAUNCH_H_
#include <Protocol/LoadedImage.h>
extern EFI_HANDLE mTrialFvHandle;
extern EFI_HANDLE mTrialAppHandle;
BOOLEAN TrialSealApplication (EFI_LOADED_IMAGE_PROTOCOL *Image);
VOID TrialLaunchApplication (VOID);
#endif
