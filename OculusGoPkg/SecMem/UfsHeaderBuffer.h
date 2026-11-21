/** Fixed boot-header workspace identified in the stock Pacific LK ELF.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_HEADER_BUFFER_H_
#define GO_UFS_HEADER_BUFFER_H_
#include "UfsPanel.h"

#define GO_LK_HEADER       0x918d7e80U
#define GO_LK_PAGE_WORD    0x918e18d4U
#define GO_LK_HEADER_SIZE  4096U
#ifdef GO_UFS_GPT_MODEL
VOID GoUfsModelReadPrimary (CONST UINT32 *Original);
#endif
#endif
