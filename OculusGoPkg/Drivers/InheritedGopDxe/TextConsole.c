/** Headset text output over the inherited GOP. All coordinates passed to GOP
    are in scanout orientation. Both eye views use the same logical 80x25 grid.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Display/Framebuffer.h>
#include "TextConsole.h"
#include <third-party/edk2/ConsoleFont.h>

#define COLUMNS 80
#define ROWS    25
#define SCALE   2
#define CELL_W  (8 * SCALE)
#define CELL_H  (19 * SCALE)
#define EYE_W   (GO_FB_HEIGHT / 2)
#define LEFT    ((EYE_W - COLUMNS * CELL_W) / 2)
#define TOP     ((GO_FB_WIDTH - ROWS * CELL_H) / 2)
STATIC_ASSERT (COLUMNS * CELL_W <= EYE_W && ROWS * CELL_H <= GO_FB_WIDTH, "text viewport");

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL *mGop;
STATIC EFI_SIMPLE_TEXT_OUTPUT_MODE mMode = {1, 0, EFI_LIGHTGRAY, 0, 0, FALSE};
STATIC CONST EFI_GRAPHICS_OUTPUT_BLT_PIXEL mPalette[16] = {
  {0,0,0,0},       {170,0,0,0},     {0,170,0,0},     {170,170,0,0},
  {0,0,170,0},     {170,0,170,0},   {0,85,170,0},    {170,170,170,0},
  {85,85,85,0},    {255,85,85,0},   {85,255,85,0},   {255,255,85,0},
  {85,85,255,0},   {255,85,255,0},  {85,255,255,0},  {255,255,255,0}
};

// Topmost native X of a run of logical rows. Pacific's display is portrait
// and text row zero is at the high-X side when the headset is worn.
STATIC UINTN
ScanoutX (UINTN FirstRow, UINTN RowCount)
{
  return TOP + (ROWS - FirstRow - RowCount) * CELL_H;
}

STATIC EFI_STATUS
FillRows (UINTN First, UINTN Count)
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Color = mPalette[mMode.Attribute >> 4];
  for (UINTN Eye = 0; Eye < 2; ++Eye) {
    EFI_STATUS Status = mGop->Blt (mGop, &Color, EfiBltVideoFill, 0, 0,
      ScanoutX (First, Count), Eye * EYE_W + LEFT, Count * CELL_H, COLUMNS * CELL_W, 0);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  return EFI_SUCCESS;
}

STATIC EFI_STATUS
LineFeed (VOID)
{
  if (mMode.CursorRow < ROWS - 1) {
    ++mMode.CursorRow;
    return EFI_SUCCESS;
  }
  for (UINTN Eye = 0; Eye < 2; ++Eye) {
    UINTN Y = Eye * EYE_W + LEFT;
    EFI_STATUS Status = mGop->Blt (mGop, NULL, EfiBltVideoToVideo,
      ScanoutX (1, ROWS - 1), Y, ScanoutX (0, ROWS - 1), Y, (ROWS - 1) * CELL_H, COLUMNS * CELL_W, 0);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  return FillRows (ROWS - 1, 1);
}

STATIC CONST UINT8 *
Glyph (CHAR16 Ch)
{
  if (Ch >= L' ' && Ch <= L'~') {
    return mAsciiFont[Ch - L' '];
  }
  for (UINTN I = 0; I < ARRAY_SIZE (mDrawingFont); ++I) {
    if (mDrawingFont[I].Code == Ch) {
      return mDrawingFont[I].Rows;
    }
  }
  return NULL;
}

STATIC EFI_STATUS
DrawGlyph (CONST UINT8 *GlyphRows)
{
  // Rotate the 8x19 raster into the panel's native column/row order.
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Tile[CELL_W][CELL_H];
  for (UINTN V = 0; V < CELL_H; ++V) {
    UINT8 Bits = GlyphRows[V / SCALE];
    for (UINTN U = 0; U < CELL_W; ++U) {
      Tile[U][CELL_H - 1 - V] = mPalette[(Bits & (0x80 >> (U / SCALE))) ?
                                           (mMode.Attribute & 15) : (mMode.Attribute >> 4)];
    }
  }
  for (UINTN Eye = 0; Eye < 2; ++Eye) {
    UINTN Y = Eye * EYE_W + LEFT + mMode.CursorColumn * CELL_W;
    EFI_STATUS Status = mGop->Blt (mGop, &Tile[0][0], EfiBltBufferToVideo, 0, 0,
      ScanoutX (mMode.CursorRow, 1), Y, CELL_H, CELL_W, 0);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  return EFI_SUCCESS;
}

STATIC BOOLEAN
Supported (CHAR16 Ch)
{
  return Glyph (Ch) != NULL || Ch == L'\b' || Ch == L'\r' || Ch == L'\n';
}

STATIC EFI_STATUS EFIAPI
TextTestString (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, CHAR16 *String)
{
  if (String == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  for (; *String != 0; ++String) {
    if (!Supported (*String)) {
      return EFI_UNSUPPORTED;
    }
  }
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
TextOutputString (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, CHAR16 *String)
{
  EFI_STATUS Result = EFI_SUCCESS;
  if (String == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  for (; *String != 0; ++String) {
    EFI_STATUS Status = EFI_SUCCESS;
    CHAR16 Ch = *String;
    CONST UINT8 *GlyphRows;
    switch (Ch) {
      case L'\b':
        if (mMode.CursorColumn > 0) {
          --mMode.CursorColumn;
        } else if (mMode.CursorRow > 0) {
          --mMode.CursorRow;
          mMode.CursorColumn = COLUMNS - 1;
        } else {
          break;
        }
        Status = DrawGlyph (Glyph (L' '));
        break;
      case L'\r':
        mMode.CursorColumn = 0;
        break;
      case L'\n':
        Status = LineFeed ();
        break;
      default:
        GlyphRows = Glyph (Ch);
        if (GlyphRows == NULL) {
          GlyphRows = Glyph (L'?');
          Result = EFI_WARN_UNKNOWN_GLYPH;
        }
        Status = DrawGlyph (GlyphRows);
        if (Status == EFI_SUCCESS && ++mMode.CursorColumn == COLUMNS) {
          mMode.CursorColumn = 0;
          Status = LineFeed ();
        }
    }
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  return Result;
}

STATIC EFI_STATUS EFIAPI
TextQuery (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Mode, UINTN *Cols, UINTN *Rows)
{
  if (Mode != 0) {
    return EFI_UNSUPPORTED;
  }
  if (Cols == NULL || Rows == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  *Cols = COLUMNS;
  *Rows = ROWS;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
TextClear (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This)
{
  EFI_STATUS Status = FillRows (0, ROWS);
  if (!EFI_ERROR (Status)) {
    mMode.CursorRow = mMode.CursorColumn = 0;
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
TextMode (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Mode)
{
  return Mode == 0 ? TextClear (This) : EFI_UNSUPPORTED;
}

STATIC EFI_STATUS EFIAPI
TextReset (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, BOOLEAN Extended)
{
  mMode.Attribute = EFI_LIGHTGRAY;
  return TextClear (This);
}

STATIC EFI_STATUS EFIAPI
TextAttribute (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Attribute)
{
  if (Attribute > 0x7f) {
    return EFI_UNSUPPORTED;
  }
  mMode.Attribute = (INT32)Attribute;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
TextPosition (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Col, UINTN Row)
{
  if (Col >= COLUMNS || Row >= ROWS) {
    return EFI_UNSUPPORTED;
  }
  mMode.CursorColumn = (INT32)Col;
  mMode.CursorRow = (INT32)Row;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
TextCursor (EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, BOOLEAN Visible)
{
  // This early console supports a logical, invisible cursor.
  return Visible ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}

STATIC EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL mText = {
  TextReset, TextOutputString, TextTestString, TextQuery, TextMode,
  TextAttribute, TextClear, TextPosition, TextCursor, &mMode
};

EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *
GoTextConsole (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop)
{
  mGop = Gop;
  return &mText;
}
