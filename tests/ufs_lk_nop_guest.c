/* AArch64 QEMU-only handoff experiment. No firmware build includes this file.
 * SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <stdint.h>

#define WINDOW 0x80440000U
#define TR_LK  0x918ee400U
#define TM_LK  0x918eec00U
#define BAR    0x10000000U
#define REG(off) (*(volatile uint32_t *)(uintptr_t)(BAR + (off)))
#define BOX ((volatile uint32_t *)(uintptr_t)0x40300000U)
#define BARRIER() __asm__ volatile ("dsb sy" ::: "memory")

enum { Ok = 1, Unmapped, Handoff, Dirty, Switch, Timeout, BadResponse, Restore };
enum { Hcs = 0x30, Hce = 0x34, TrBase = 0x50, TrHigh = 0x54, Door = 0x58,
       Run = 0x60, TmBase = 0x70, TmHigh = 0x74, TmDoor = 0x78 };

static int
wait_register(unsigned offset, uint32_t expected)
{
  for (unsigned i = 0; i < 2000000; ++i) {
    if (REG(offset) == expected) return 1;
  }
  return 0;
}

static unsigned
probe(unsigned page, unsigned model_mapping)
{
  if (model_mapping != 1 || page >= 4) return Unmapped;
  /* PCI version and CAP belong to the virtual device. The model does not
     implement task-list Run/Stop. Its base and doorbell must remain intact. */
  if (REG(8) != 0x400 || REG(Hce) != 1 || (REG(Hcs) & 0x3f) != 15 ||
      REG(Run) != 1 || REG(Door) || REG(TmDoor) ||
      REG(TrBase) != TR_LK || REG(TrHigh) || REG(TmBase) != TM_LK || REG(TmHigh))
    return Handoff;
  volatile uint8_t *window = (volatile uint8_t *)(uintptr_t)WINDOW;
  for (unsigned i = 0; i < 16384; ++i)
    if (window[i] != 0xa5) return Dirty;

  uintptr_t tr = WINDOW + ((page + 1) % 4) * 4096;
  uintptr_t ucd = WINDOW + page * 4096 + 0xc00;
  volatile uint32_t *utrd = (volatile uint32_t *)tr;
  volatile uint8_t *req = (volatile uint8_t *)ucd;
  volatile uint8_t *rsp = req + 0x3e0;
  unsigned tag = 0x71 + page;
  for (unsigned i = 0; i < 32; ++i) req[i] = 0;
  req[3] = tag;                         /* NOP OUT, no data segment */
  utrd[0] = 0x11000000; utrd[1] = 0; utrd[2] = 15; utrd[3] = 0;
  utrd[4] = (uint32_t)ucd; utrd[5] = 0;
  utrd[6] = ((0x3e0 / 4) << 16) | 8;  /* 32-byte response at page end */
  utrd[7] = 0;                         /* zero PRDT entries */
  BARRIER();
  REG(Run) = 0;
  BARRIER();
  if (!wait_register(Run, 0) || REG(Door) || REG(TmDoor)) return Switch;

  REG(TrBase) = (uint32_t)tr;          /* high dword already verified zero */
  BARRIER();
  unsigned result = Switch;
  if (REG(TrBase) == tr && !REG(TrHigh)) {
    REG(Run) = 1;
    BARRIER();
    if (wait_register(Run, 1) && !REG(Door) && !REG(TmDoor)) {
      REG(Door) = 1;
      BARRIER();
      /* An outstanding DMA must keep its descriptors and base on timeout. */
      if (!wait_register(Door, 0)) return Timeout;
      BARRIER();
      result = (utrd[2] == 0 && rsp[0] == 0x20 && rsp[3] == tag &&
                rsp[6] == 0 && rsp[10] == 0 && rsp[11] == 0) ? Ok : BadResponse;
    }
  }
  if (REG(Door) || REG(TmDoor)) return Restore;
  REG(Run) = 0;
  BARRIER();
  if (!wait_register(Run, 0) || REG(Door)) return Restore;
  REG(TrBase) = TR_LK;
  BARRIER();
  if (REG(TrBase) != TR_LK || REG(TrHigh)) return Restore;
  REG(Run) = 1;
  BARRIER();
  if (!wait_register(Run, 1) || REG(Hce) != 1 || REG(TmBase) != TM_LK ||
      REG(TmHigh) || REG(TmDoor) || REG(Door)) return Restore;
  return result;
}

void run_guest(void)
{
  BOX[2] = probe(BOX[0], BOX[1]);
  BARRIER();
  BOX[3] = 0x444f4e45;
  for (;;) __asm__ volatile ("wfe");
}
