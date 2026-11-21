/** SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_TEXT_CONSOLE_H_
#define GO_TEXT_CONSOLE_H_
#include <Protocol/GraphicsOutput.h>
#include <Protocol/SimpleTextOut.h>
EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *GoTextConsole (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop);
#endif
