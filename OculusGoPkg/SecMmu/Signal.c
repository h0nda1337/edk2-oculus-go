/** Two stage-specific patterns in the previously observed packed BGR bands.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Base.h>
#include "Layout.h"

BOOLEAN
MmuSignal (UINTN Stage, BOOLEAN VerifyOnly)
{
  UINTN Band, Row, Block, X;
  UINT8 B, G, R;
  volatile UINT8 *Pixel;
  for (Band = 0; Band < 2; ++Band) {
    Pixel = (volatile UINT8 *)(UINTN)((Band == 0) ? GO_BAND_ONE : GO_BAND_TWO);
    for (Row = 0; Row < 32; ++Row) {
      for (Block = 0; Block < 5; ++Block) {
        if (Stage == 2 && Block != 2) {
          Pixel += 288 * 3;
          continue;
        }
        if (Stage != 0) {
          B = ((Block == 0) || (Block == 4)) ? 255 : 0;
          G = ((Block & 1) != 0) ? 255 : 0;
          R = (G != 0 || Stage == 2) ? 255 : 0;
        } else {
          B = G = R = ((Block & 1) == 0) ? 255 : 0;
        }
        for (X = 0; X < 288; ++X, Pixel += 3) {
          if (VerifyOnly) {
            if ((Pixel[0] != B) || (Pixel[1] != G) || (Pixel[2] != R)) {
              return FALSE;
            }
          } else {
            Pixel[0] = B;
            Pixel[1] = G;
            Pixel[2] = R;
          }
        }
      }
    }
  }
  return TRUE;
}
