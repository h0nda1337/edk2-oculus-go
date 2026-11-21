/** Procedural stereo glass pyramid for the Pacific BDS. Integer model coordinates,
    two off-axis cameras and native GOP BLTs; the scene owns only pool memory.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Display/Framebuffer.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/TimerLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <third-party/edk2/ConsoleFont.h>
#include "Welcome.h"

#define WIDTH        352
#define HEIGHT       400
#define FOCAL        340
#define RISE_MS      1600
#define TURN_MS      4200
#define REVEAL_MS    2100
#define HOLD_MS      1000
#define END_MS       (RISE_MS + TURN_MS + REVEAL_MS + HOLD_MS)
#define FRAME_MS     33
#define TILE_BYTES   (WIDTH * HEIGHT * sizeof (PIXEL))

typedef EFI_GRAPHICS_OUTPUT_BLT_PIXEL PIXEL;
typedef struct { INT32 X, Y, Z; } POINT;
typedef struct { INT32 X, Y; } SCREEN_POINT;
typedef struct { UINT8 Count, Vertex[4]; } FACE;

// A square base and a single apex. Each triangular side has its own normal;
// the lower quadrilateral is also rendered so it can refract through the sides.
STATIC CONST POINT mMesh[] = {
  {0, -101, 0},
  {-84, 52, -84}, {84, 52, -84}, {84, 52, 84}, {-84, 52, 84}
};
STATIC CONST FACE mFaces[] = {
  {3, {0, 1, 2}}, {3, {0, 2, 3}}, {3, {0, 3, 4}}, {3, {0, 4, 1}},
  {4, {1, 4, 3, 2}}
};
STATIC CONST CHAR8 mWelcome[] = "Welcome to EDK2 Go!";

STATIC INT32
Abs32 (INT32 V)
{
  return V < 0 ? -V : V;
}

STATIC INT32
Clamp (INT32 Value, INT32 Low, INT32 High)
{
  return MIN (MAX (Value, Low), High);
}

// 1024 angular units per revolution. Rational half-wave approximation, Q10 result.
STATIC INT32
SinTurn (INT32 Angle)
{
  UINT32 T = (UINT32)Angle & 511;
  INT32 P = (INT32)(T * (512 - T));
  INT32 Sine = 16384 * P / (5 * 512 * 512 - 4 * P);
  return (Angle & 512) ? -Sine : Sine;
}

STATIC INT32
Ease (INT32 Time, INT32 Duration)
{
  INT32 T = Clamp (Time, 0, Duration) * 1024 / Duration;
  return T * T * (3072 - 2 * T) / (1024 * 1024);
}

STATIC VOID
Pose (POINT *World, INT32 Ms)
{
  INT32 Angle = 148 + Ease (Ms - RISE_MS, TURN_MS);
  INT32 Cos = SinTurn (Angle + 256);
  INT32 Sin = SinTurn (Angle);
  INT32 Lift = 360 * (1024 - Ease (Ms, RISE_MS)) / 1024;
  for (UINTN I = 0; I < ARRAY_SIZE (mMesh); ++I) {
    CONST POINT *P = &mMesh[I];
    INT32 Z = (P->Z * Cos - P->X * Sin) / 1024;
    INT32 X = (P->X * Cos + P->Z * Sin) / 1024;
    // Keep the apex upright. Fourteen degrees of pitch reveal the square base,
    // with a near corner offset from the apex in the final three-quarter view.
    World[I].Z = (P->Y * 248 + Z * 994) / 1024;
    World[I].X = X;
    World[I].Y = (P->Y * 994 - Z * 248) / 1024 + Lift - 10;
  }
}

STATIC POINT
FaceNormal (POINT A, POINT B, POINT C)
{
  POINT U = {B.X - A.X, B.Y - A.Y, B.Z - A.Z};
  POINT V = {C.X - A.X, C.Y - A.Y, C.Z - A.Z};
  POINT N = {U.Y*V.Z - U.Z*V.Y, U.Z*V.X - U.X*V.Z, U.X*V.Y - U.Y*V.X};
  INT32 Scale = MAX (Abs32 (N.X), MAX (Abs32 (N.Y), Abs32 (N.Z)));
  N.X = N.X * 256 / Scale;
  N.Y = N.Y * 256 / Scale;
  N.Z = N.Z * 256 / Scale;
  INT32 Square = N.X*N.X + N.Y*N.Y + N.Z*N.Z;
  INT32 Length = 256;
  for (UINTN I = 0; I < 4; ++I) {
    Length = (Length + Square / Length) / 2;
  }
  N.X = N.X * 256 / Length;
  N.Y = N.Y * 256 / Length;
  N.Z = N.Z * 256 / Length;
  return N;
}

// Both the scratch tile and its backdrop use GOP scanout order. Logical (0,0)
// is the top-left pixel when worn. Each eye is centered on its own half-panel.
STATIC UINTN
PixelIndex (INT32 X, INT32 Y)
{
  return (UINTN)X * HEIGHT + HEIGHT - 1 - (UINTN)Y;
}

STATIC VOID
Backdrop (PIXEL *Background)
{
  for (INT32 X = 0; X < WIDTH; ++X) {
    for (INT32 Y = 0; Y < HEIGHT; ++Y) {
      INT32 Dx = X - WIDTH / 2, Dy = Y - HEIGHT / 2;
      INT32 Light = MAX (0, 27000 - Dx*Dx - Dy*Dy);
      PIXEL Color = {(UINT8)(Light / 1270), (UINT8)(Light / 3400), (UINT8)(Light / 9400), 0};
      Background[PixelIndex (X, Y)] = Color;
    }
  }
}

// A soft pool of light under the suspended crystal makes its height visible.
// The transmitted highlight follows the rotating base corner on this plane.
STATIC VOID
GroundLight (PIXEL *Tile, CONST POINT *World, INT32 Ms, INT32 EyeOffset)
{
  INT32 Gain = Ease (Ms, RISE_MS);
  INT32 Center = WIDTH/2 + EyeOffset/6;
  INT32 Focus = Center + World[3].X/4;
  INT32 Spread = 48 + Abs32 (World[1].X - World[2].X)/5;
  for (INT32 Y = HEIGHT/2 + 88; Y < HEIGHT/2 + 122; ++Y) {
    INT32 Dy = Y - HEIGHT/2 - 106;
    for (INT32 X = 12; X < WIDTH-12; ++X) {
      INT32 Dx = X - Center;
      INT32 Pool = MAX (0, 19000 - Dx*Dx - 70*Dy*Dy) / 610;
      INT32 ShadeX = Dx - 11, ShadeY = Dy + 2;
      INT32 Shadow = MAX (0, 5300 - ShadeX*ShadeX - 120*ShadeY*ShadeY) / 255;
      INT32 U = X - Focus;
      INT32 Ridge = Abs32 (3*Dy - 10 + U*U/450 + World[0].Z/22);
      INT32 Caustic = MAX (0, Spread - Abs32 (U)) * MAX (0, 18 - Ridge) / 32;
      INT32 Blue = MAX (0, Pool - Shadow + Caustic) * Gain / 1024;
      PIXEL *Dest = &Tile[PixelIndex (X,Y)];
      Dest->Blue += (UINT8)Blue;
      Dest->Green += (UINT8)(Blue/2);
      Dest->Red += (UINT8)(Blue/7);
    }
  }
}

typedef struct { INT32 Dx, Dy, Offset, InvLength; } EDGE;

STATIC VOID
GlassFace (PIXEL *Tile, CONST PIXEL *Transmitted, CONST SCREEN_POINT *Points,
          CONST FACE *Face, POINT Normal, INT32 Winding)
{
  EDGE Edges[4];
  INT32 MinX = WIDTH, MinY = HEIGHT, MaxX = -1, MaxY = -1;
  for (UINTN I = 0; I < Face->Count; ++I) {
    SCREEN_POINT A = Points[Face->Vertex[I]];
    SCREEN_POINT B = Points[Face->Vertex[(I + 1) % Face->Count]];
    INT32 Dx = (A.Y - B.Y) * Winding;
    INT32 Dy = (B.X - A.X) * Winding;
    INT32 Length = MAX (Abs32 (Dx), Abs32 (Dy));
    if (Length == 0) {
      return;
    }
    Edges[I] = (EDGE){Dx, Dy, -Dx*A.X - Dy*A.Y, 1024 / Length};
    MinX = MIN (MinX, A.X); MinY = MIN (MinY, A.Y);
    MaxX = MAX (MaxX, A.X); MaxY = MAX (MaxY, A.Y);
  }

  INT32 Grazing = 256 - Abs32 (Normal.Z);
  for (INT32 X = MAX (0, MinX); X <= MIN (WIDTH - 1, MaxX); ++X) {
    for (INT32 Y = MAX (0, MinY); Y <= MIN (HEIGHT - 1, MaxY); ++Y) {
      INT32 Nearest = MAX_INT32;
      for (UINTN I = 0; I < Face->Count; ++I) {
        CONST EDGE *E = &Edges[I];
        INT32 Side = E->Offset + E->Dx * X + E->Dy * Y;
        if (Side < 0) {
          Nearest = -1;
          break;
        }
        Nearest = MIN (Nearest, Side * E->InvLength);
      }
      if (Nearest < 0) {
        continue;
      }
      // Reflect the incident camera ray about this facet's camera-space normal.
      // Two rectangular studio lights and a narrow strip are sampled analytically.
      INT32 Vx = (X - WIDTH/2) * 256 / FOCAL;
      INT32 Vy = (Y - HEIGHT/2) * 256 / FOCAL;
      INT32 Dot = (Normal.X*Vx + Normal.Y*Vy)/256 + Normal.Z;
      INT32 Rx = Vx - 2*Dot*Normal.X/256;
      INT32 Ry = Vy - 2*Dot*Normal.Y/256;
      INT32 Rz = 256 - 2*Dot*Normal.Z/256;
      INT32 U = Rx + Ry/2;
      INT32 Sky = Clamp (157 - Abs32 (U + 161) - Abs32 (Ry - 123)/2, 0, 157);
      INT32 Strip = MAX (0, 57 - Abs32 (2*Rx - Ry + 160));
      INT32 Gleam = MAX (0, 88 - Abs32 (U - 86) - Abs32 (Rz + 36)/2);
      INT32 Fill = MAX (0, 119 - Abs32 (Rx - 145)/2 - Abs32 (Ry + 90)/2);
      INT32 Rim = MAX (0, 255 - Nearest/6);
      INT32 Fresnel = Grazing * Grazing / 256;
      INT32 Reflection = Sky*Sky/154 + 2*Strip + Gleam + Fresnel/4;
      INT32 Edge = Rim * (50 + Fresnel/3) / 255;

      // Refract the already composited rear surfaces into the front faces.
      // The small wavelength-dependent shift splits narrow internal highlights.
      INT32 Bend = (Winding < 0) ? 25 : 8;
      INT32 OffsetX = (Normal.X + Vx) * Bend / 256;
      INT32 OffsetY = (Normal.Y + Vy) * Bend / 256;
      INT32 SampleX = Clamp (X + OffsetX, 1, WIDTH-2);
      INT32 SampleY = Clamp (Y + OffsetY, 0, HEIGHT-1);
      PIXEL Behind = Transmitted[PixelIndex (SampleX, SampleY)];
      INT32 Red = Transmitted[PixelIndex (SampleX - 1, SampleY)].Red;
      INT32 Blue = Transmitted[PixelIndex (SampleX + 1, SampleY)].Blue;
      UINTN Pos = PixelIndex (X,Y);
      PIXEL Straight = Transmitted[Pos];
      Red = (3*Red + Straight.Red)/4;
      INT32 Green = (3*Behind.Green + Straight.Green)/4;
      Blue = (3*Blue + Straight.Blue)/4;
      // The glass tint transmits 217/255 (~85%) per interface. Surface light
      // adds a grazing reflection and a fine highlight along the polished cut.
      Tile[Pos] = (PIXEL){
        (UINT8)Clamp ((217*Blue + 38*192)/255 + Reflection + Edge + Fill*3/4, 0, 255),
        (UINT8)Clamp ((217*Green + 38*65)/255 + Reflection*3/4 + Edge + Fill/3, 0, 255),
        (UINT8)Clamp ((217*Red + 38*7)/255 + Reflection*2/5 + Edge*4/5, 0, 255), 0
      };
    }
  }
}

STATIC VOID
DrawPyramid (PIXEL *Tile, PIXEL *Rear, CONST PIXEL *Background, CONST POINT *World, INT32 EyeOffset)
{
  SCREEN_POINT Points[ARRAY_SIZE (mMesh)];
  for (UINTN I = 0; I < ARRAY_SIZE (mMesh); ++I) {
    INT32 Depth = FOCAL + World[I].Z;
    Points[I].X = WIDTH/2 + (FOCAL*World[I].X + EyeOffset*World[I].Z) / Depth;
    Points[I].Y = HEIGHT/2 + FOCAL*World[I].Y / Depth;
  }
  // A ray intersects at most two surfaces of this convex solid. Blend the
  // exit faces before the entry faces, using projected winding for this eye.
  for (INT32 Winding = 1; Winding >= -1; Winding -= 2) {
    if (Winding < 0) {
      CopyMem (Rear, Tile, TILE_BYTES);
    }
    for (UINTN I = 0; I < ARRAY_SIZE (mFaces); ++I) {
      CONST FACE *Face = &mFaces[I];
      UINT8 A = Face->Vertex[0], B = Face->Vertex[1], C = Face->Vertex[2];
      INT32 Area = (Points[B].X - Points[A].X)*(Points[C].Y - Points[A].Y)
                 - (Points[B].Y - Points[A].Y)*(Points[C].X - Points[A].X);
      if (Area * Winding > 0) {
        GlassFace (Tile, Winding > 0 ? Background : Rear, Points, Face, FaceNormal (World[A], World[B], World[C]), Winding);
      }
    }
  }
}

STATIC VOID
DrawWelcome (PIXEL *Tile, INT32 Time)
{
  CONST INT32 Count = sizeof (mWelcome) - 1;
  if (Time <= 0) {
    return;
  }
  for (INT32 I = 0; I < Count; ++I) {
    INT32 Light = Ease (Time - I * 65, 850);
    CONST UINT8 *Glyph = mAsciiFont[mWelcome[I] - ' '];
    for (INT32 V = 0; V < 38; ++V) {
      UINT8 Row = Glyph[V/2];
      UINT8 Halo = (UINT8)((Row << 1) | (Row >> 1));
      if (V >= 2) { Halo |= Glyph[V/2 - 1]; }
      if (V < 36) { Halo |= Glyph[V/2 + 1]; }
      for (INT32 U = 0; U < 16; ++U) {
        INT32 X = (WIDTH - Count * 16)/2 + 16*I + U;
        INT32 Y = HEIGHT/2 + 115 + V;
        UINTN Pos = PixelIndex (X,Y);
        UINT8 Bit = (UINT8)(0x80 >> (U/2));
        if ((Row & Bit) != 0) {
          Tile[Pos].Blue  = MAX (Tile[Pos].Blue, 255*Light/1024);
          Tile[Pos].Green = MAX (Tile[Pos].Green, 156*Light/1024);
          Tile[Pos].Red   = MAX (Tile[Pos].Red, 58*Light/1024);
        } else if ((Halo & Bit) != 0) {
          Tile[Pos].Blue  = MAX (Tile[Pos].Blue, 24*Light/1024);
          Tile[Pos].Green = MAX (Tile[Pos].Green, 8*Light/1024);
        }
      }
    }
  }
}

EFI_STATUS
GoPlayWelcome (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop)
{
  if (Gop == NULL || Gop->Mode == NULL || Gop->Mode->Info == NULL ||
      Gop->Mode->Info->HorizontalResolution != GO_FB_WIDTH ||
      Gop->Mode->Info->VerticalResolution != GO_FB_HEIGHT) {
    return EFI_UNSUPPORTED;
  }
  if (GetPerformanceCounterProperties (NULL, NULL) == 0) {
    return EFI_NOT_READY;
  }
  PIXEL *Background = AllocatePool (3 * TILE_BYTES);
  if (Background == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  PIXEL *Tile = Background + WIDTH * HEIGHT;
  PIXEL *Rear = Tile + WIDTH * HEIGHT;
  Backdrop (Background);
  EFI_STATUS Status = EFI_SUCCESS;
  UINT64 Start = GetPerformanceCounter ();
  INT32 Ms = 0;
  while (Ms < END_MS && !EFI_ERROR (Status)) {
    POINT World[ARRAY_SIZE (mMesh)];
    Pose (World, Ms);
    for (UINTN Eye = 0; Eye < 2; ++Eye) {
      CopyMem (Tile, Background, TILE_BYTES);
      INT32 EyeOffset = Eye == 0 ? -14 : 14;
      GroundLight (Tile, World, Ms, EyeOffset);
      DrawPyramid (Tile, Rear, Background, World, EyeOffset);
      DrawWelcome (Tile, Ms - RISE_MS - TURN_MS);
      Status = Gop->Blt (Gop, Tile, EfiBltBufferToVideo, 0, 0,
                         (GO_FB_WIDTH - HEIGHT)/2, Eye*(GO_FB_HEIGHT/2) + (GO_FB_HEIGHT/2 - WIDTH)/2,
                         HEIGHT, WIDTH, 0);
      if (EFI_ERROR (Status)) {
        break;
      }
    }
    UINT64 Elapsed = GetTimeInNanoSecond (GetPerformanceCounter () - Start) / 1000000;
    INT32 Next = MIN (END_MS, Ms + FRAME_MS);
    if (!EFI_ERROR (Status) && Elapsed < (UINT64)Next) {
      Status = gBS->Stall ((UINTN)(Next - Elapsed) * 1000);
    }
    Ms = MAX (Next, (INT32)MIN (Elapsed, (UINT64)END_MS));
  }
  FreePool (Background);
  return Status;
}
