/** Exercise live, overlapping call frames and the PI handoff constructor.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Base.h>

BOOLEAN SecMemConstructHob (VOID);

// Each caller must retain its own 1 KiB of volatile data while the next
// frame (or the real PI HOB constructor) is active.
__attribute__ ((noinline))
BOOLEAN
SecStackFrames (IN UINTN Depth)
{
  volatile UINT64 Words[128];
  UINTN Index;
  BOOLEAN Ok;

  for (Index = 0; Index < 128; ++Index) {
    Words[Index] = (Depth << 16) | Index;
  }
  if (Depth == 0) {
    Ok = SecMemConstructHob ();
  } else {
    Ok = SecStackFrames (Depth - 1);
  }
  for (Index = 0; Index < 128; ++Index) {
    if (Words[Index] != ((Depth << 16) | Index)) {
      return FALSE;
    }
  }
  return Ok;
}
