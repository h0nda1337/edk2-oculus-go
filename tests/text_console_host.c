/** Test text mode operations outside the visible checkpoint using a recording GOP.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <assert.h>
#include <Uefi.h>
#include "TextConsole.h"

typedef struct {
  EFI_GRAPHICS_OUTPUT_BLT_OPERATION Op;
  UINTN Sx, Sy, Dx, Dy, W, H;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Color;
} CALL;

STATIC CALL Calls[12];
STATIC UINTN Count, FailAt;
STATIC EFI_STATUS EFIAPI
Record (EFI_GRAPHICS_OUTPUT_PROTOCOL *This, EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Buffer,
        EFI_GRAPHICS_OUTPUT_BLT_OPERATION Op, UINTN Sx, UINTN Sy, UINTN Dx, UINTN Dy,
        UINTN W, UINTN H, UINTN Delta)
{
  assert (Count < 12);
  CALL *Call = &Calls[Count++];
  *Call = (CALL){ Op,Sx,Sy,Dx,Dy,W,H,{0,0,0,0} };
  if (Buffer != NULL) {
    Call->Color = *Buffer;
  }
  return Count == FailAt ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}

int main (void)
{
  EFI_GRAPHICS_OUTPUT_PROTOCOL gop = {0};
  UINTN cols, rows;
  gop.Blt = Record;
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *t = GoTextConsole (&gop);
  assert (t->QueryMode (t,0,&cols,&rows)==EFI_SUCCESS && cols==80 && rows==25);
  assert (t->QueryMode (t,1,&cols,&rows)==EFI_UNSUPPORTED);
  assert (t->SetMode (t,1)==EFI_UNSUPPORTED && Count==0);
  assert (t->SetCursorPosition (t,80,0)==EFI_UNSUPPORTED);
  assert (t->SetCursorPosition (t,79,25)==EFI_UNSUPPORTED);
  assert (t->SetAttribute (t,128)==EFI_UNSUPPORTED);
  assert (t->EnableCursor (t,FALSE)==EFI_SUCCESS && !t->Mode->CursorVisible);
  assert (t->EnableCursor (t,TRUE)==EFI_DEVICE_ERROR);
  assert (t->TestString (t,L"AZaz09 ~\b\r\n")==EFI_SUCCESS);
  assert (t->TestString (t,L"\x2603")==EFI_UNSUPPORTED);
  assert (t->OutputString (t,L"\x2603")==EFI_WARN_UNKNOWN_GLYPH && Count==2);
  assert (t->OutputString (t,L"\b")==EFI_SUCCESS && t->Mode->CursorColumn==0);
  CHAR16 required[] = {BOXDRAW_DOUBLE_HORIZONTAL, BLOCKELEMENT_FULL_BLOCK, ARROW_UP, 0};
  assert (t->TestString (t,required)==EFI_SUCCESS);
  assert (t->SetCursorPosition (t,0,1)==EFI_SUCCESS && t->OutputString (t,L"\b")==EFI_SUCCESS);
  assert (t->Mode->CursorColumn==79 && t->Mode->CursorRow==0);
  Count=0;
  assert (t->SetAttribute (t,EFI_TEXT_ATTR(EFI_WHITE,EFI_BLUE))==EFI_SUCCESS);
  assert (t->SetMode (t,0)==EFI_SUCCESS && Count==2);
  for (UINTN eye=0; eye<2; ++eye) {
    CALL *c=&Calls[eye];
    assert (c->Op==EfiBltVideoFill && c->Dx==245 && c->Dy==eye*1280 && c->W==950 && c->H==1280);
    assert (c->Color.Blue==170 && c->Color.Red==0 && c->Color.Green==0);
  }
  Count=0;
  assert (t->SetCursorPosition (t,79,24)==EFI_SUCCESS && t->OutputString (t,L"z")==EFI_SUCCESS);
  assert (Count==6 && t->Mode->CursorColumn==0 && t->Mode->CursorRow==24);
  for (UINTN eye=0; eye<2; ++eye) {
    CALL *c=&Calls[2+eye];
    assert (c->Op==EfiBltVideoToVideo && c->Sx==245 && c->Dx==283);
    assert (c->Sy==eye*1280 && c->Dy==c->Sy && c->W==912 && c->H==1280);
    c=&Calls[4+eye];
    assert (c->Op==EfiBltVideoFill && c->Dx==245 && c->Dy==eye*1280 && c->W==38 && c->H==1280);
  }
  Count=0;
  FailAt=2;
  assert (t->OutputString (t,L"x")==EFI_DEVICE_ERROR && Count==2 && t->Mode->CursorColumn==0);
  Count=FailAt=0;
  assert (t->Reset (t,FALSE)==EFI_SUCCESS && t->Mode->CursorRow==0 && t->Mode->Attribute==EFI_LIGHTGRAY);
  Count=FailAt=0;
  assert (t->QueryMode (t,2,&cols,&rows)==EFI_SUCCESS && cols==24 && rows==12);
  assert (t->SetMode (t,2)==EFI_SUCCESS && t->Mode->Mode==2 && Count==3);
  assert (Calls[0].Op==EfiBltVideoFill && Calls[0].W==1440 && Calls[0].H==2560);
  for (UINTN eye=0; eye<2; ++eye) {
    CALL *c=&Calls[1+eye];
    assert (c->Dx==492 && c->Dy==448+1280*eye && c->W==456 && c->H==384);
  }
  assert (t->SetCursorPosition (t,24,0)==EFI_UNSUPPORTED);
  assert (t->SetCursorPosition (t,0,12)==EFI_UNSUPPORTED);
  Count=0;
  assert (t->SetCursorPosition (t,23,11)==EFI_SUCCESS && t->OutputString (t,L"x")==EFI_SUCCESS);
  assert (t->Mode->CursorRow==11 && t->Mode->CursorColumn==0 && Count==6);
  for (UINTN eye=0; eye<2; ++eye) {
    CALL *c=&Calls[2+eye];
    assert (c->Op==EfiBltVideoToVideo && c->Sx==492 && c->Dx==530);
    assert (c->Sy==448+1280*eye && c->Dy==c->Sy && c->W==418 && c->H==384);
  }
  Count=0;
  assert (t->Reset (t,FALSE)==EFI_SUCCESS && t->Mode->Mode==0 && Count==3);
  Count=0;
  FailAt=2;
  assert (t->SetMode (t,2)==EFI_DEVICE_ERROR && t->Mode->Mode==0);
  return 0;
}
