# RAM Intercept — PIO Architecture (Classics Rev 1)

This document describes **only the PIO portion** of
[Ram_Intercept_classics.py](Ram_Intercept_classics.py): which PIO program runs on
which physical PIO block / state machine, and the IRQ chain that fires them in
sequence.

The design uses **two PIO blocks** (PIO0 and PIO2) and **7 state machines**.
DMA moves data between the state machines and internal RP2350 RAM (shadow RAM)
and is out of scope here.

> **Note — PIO1 is not free.** The third PIO block (**PIO1**) is used by the
> board / fault-status LED driver in [BoardLED.py](../common/BoardLED.py), *not*
> by the RAM intercept. It is documented below as a reference so its state
> machines and instruction usage are accounted for when planning PIO0/PIO2
> instruction space. See [PIO1 — Board / fault LED](#pio1--board--fault-led-reference-only).

---

## Physical placement

### PIO2 — Detection / Trigger block
Watches the bus for a valid chip-select + VMA event and forwards a single clean
trigger to PIO0.

| SM  | Program        | JMP pin        | Role |
|-----|----------------|----------------|------|
| SM8 | *(reserved)*   | —              | Used by the MicroPython Wi-Fi chip interface |
| SM9 | `CatchVMA_U8`  | GPIO13 (U8 5101 RAM, 0x0200–0x02FF) | Debounce U8 VMA+ADR going low → sets IRQ5 |
| SM10| `CatchVMA_U7`  | GPIO11 (U7 6810 RAM, 0x0000–0x007F) | Debounce U7 VMA+ADR going low → sets IRQ5 |
| SM11| `Pass_VMA`     | —              | Serializes U7/U8, fires IRQ4 across to PIO0, clears IRQ5 |

### PIO0 — RAM access block (shadow RAM)
Handles the actual read/write cycle against internal RP2350 RAM.

| SM  | Program           | JMP pin      | Role |
|-----|-------------------|--------------|------|
| SM0 | `ReadAddress`     | GPIO12 (W/R) | On IRQ4: read cycle → serve data from RAM; write cycle → fire IRQ5 |
| SM1 | `GetWriteAddress` | —            | On IRQ5: latch write address → fire IRQ6 |
| SM2 | `WriteRam`        | —            | On IRQ6: latch write data → push to DMA |

### PIO1 — Board / fault LED *(reference only)*
Not part of the RAM intercept. Drives the on-board WS2812 (and legacy single-color)
status LED that indicates faults / activity. Defined in
[BoardLED.py](../common/BoardLED.py) and started from `BoardLED.startUp()`.

| SM  | Program     | Pin / clock | Role |
|-----|-------------|-------------|------|
| SM4 | `irq_clock` | 1 MHz       | Low-speed tick: raises **IRQ2** to pace the WS2812 bit timing |
| SM5 | `ws2812`    | GPIO26 (side-set), 8 MHz | Shifts 24-bit GRB pixel data out to the LED; paces off IRQ2 |
| SM6 | *(free)*    | —           | Available |
| SM7 | *(free)*    | —           | Available |

**Instruction budget:** `ws2812` (~15 instr) + `irq_clock` (3 instr) ≈ **18 of 32**
used, leaving ~14 instructions and **2 free state machines (SM6, SM7)**.

**IRQ:** uses **IRQ2 (PIO1-local)** between `irq_clock` and `ws2812`; independent of
the intercept's IRQ4/5/6.

> **Consequence for instruction space:** PIO1 cannot be treated as a blank block.
> If PIO0 runs out of room, PIO1 can host a *small* relocated state machine (2 SMs
> and ~14 instructions remain), but the LED driver's SM0/SM1, GPIO26 side-set, and
> IRQ2 must be preserved.

> **IRQ scope note:** PIO IRQ flags are **local to each PIO block** unless the
> cross-block form is used. So `IRQ5` inside PIO2 (Catch → Pass) is a *different*
> physical flag than `IRQ5` inside PIO0 (ReadAddress → GetWriteAddress). The only
> cross-block signal is **IRQ4**, sent from PIO2→PIO0 by the raw `word(0xC41C)`
> instruction in `Pass_VMA`.

---

## Trigger sequence

```
                          PIO2 (detection)                              PIO0 (RAM access)
  ┌────────────────────────────────────────────────┐   ┌──────────────────────────────────────────────┐
  │                                                 │   │                                              │
GPIO13 low ─► [SM9 CatchVMA_U8] ─┐                  │   │                                              │
                                 ├─► set IRQ5 ─► [SM11 Pass_VMA] ─ word(0xC41C) ─► IRQ4 ─► [SM0 ReadAddress]
GPIO11 low ─► [SM10 CatchVMA_U7]─┘  (PIO2-local)     │   │                                    │        │
                                                    │   │                    ┌───────────────┴──────┐ │
                                                    │   │              read cycle           write cycle│
                                                    │   │            (W/R pin low)         (W/R pin high)
                                                    │   │                    │                  │       │
                                                    │   │            serve data from      set IRQ5 ─► [SM1 GetWriteAddress]
                                                    │   │            shadow RAM via DMA        (PIO0-local)   │
                                                    │   │            back to bus                        set IRQ6 ─► [SM2 WriteRam]
                                                    │   │                                                (PIO0-local)  │
                                                    │   │                                                       read data,
                                                    │   │                                                       push to DMA
  └────────────────────────────────────────────────┘   └──────────────────────────────────────────────┘
```

### Step by step

1. **`CatchVMA_U8` (PIO2 / SM9)** and **`CatchVMA_U7` (PIO2 / SM10)** each wait
   for their VMA+ADR pin (GPIO13 / GPIO11) to go low, apply a `[15]`-cycle
   (~100 ns) debounce, re-check via `jmp(pin,...)` to reject ~50 ns false pulses,
   then **raise IRQ5** (PIO2-local). Both use the same IRQ5.

2. **`Pass_VMA` (PIO2 / SM11)** waits on IRQ5. This single point serializes U7
   vs U8 so one can't interrupt the other. On IRQ5 it:
   - issues `word(0xC41C)` → **IRQ4 to PIO0** (the cross-block trigger),
   - waits one eClock high/low cycle (GPIO1) to ride out the bus cycle and ignore
     spurious follow-on IRQs,
   - **clears IRQ5** before looping.

3. **`ReadAddress` (PIO0 / SM0)** waits on **IRQ4**. It then branches on the W/R
   pin (GPIO12, inverted):
   - **Read cycle:** captures the address (A8, then A0–A7 with `A_Select`
     side-set), `push`es it for DMA, flips the data pins to outputs, drives the
     byte fetched from shadow RAM onto the data bus, then restores the pins to
     inputs after eClock falls. Loops back to top — **no further SM involved**.
   - **Write cycle:** raises **IRQ5** (PIO0-local) to hand off, then waits out the
     eClock cycle.

4. **`GetWriteAddress` (PIO0 / SM1)** waits on **IRQ5**. Latches the write address
   (A8 then A0–A7), `push`es it for DMA, then raises **IRQ6**.

5. **`WriteRam` (PIO0 / SM2)** waits on **IRQ6**. Waits for eClock high + settle
   (`[15]`/`[15]` delays for data setup/hold), reads all 8 data pins in one go,
   and `push`es the byte out (picked up by DMA into shadow RAM).

---

## IRQ summary

| IRQ  | Block  | Raised by                          | Consumed by                | Meaning |
|------|--------|------------------------------------|----------------------------|---------|
| IRQ5 | PIO2   | `CatchVMA_U8` / `CatchVMA_U7`      | `Pass_VMA`                 | A debounced U7/U8 VMA event occurred |
| IRQ4 | PIO0*  | `Pass_VMA` (`word(0xC41C)`)        | `ReadAddress`              | Cross-block trigger: valid bus access begins |
| IRQ5 | PIO0   | `ReadAddress` (write branch)      | `GetWriteAddress`          | This cycle is a write; capture address |
| IRQ6 | PIO0   | `GetWriteAddress`                 | `WriteRam`                 | Address captured; capture data |

\* Sent from PIO2 to PIO0 via the raw-encoded cross-PIO IRQ instruction
(`word(0xC41C)` — "IRQ4 to PIO block +1"; PIO2 +1 wraps to PIO0).

---

## Startup order

From `pio_start()`:

1. **PIO2 first:** `CatchVMA_U7`, `CatchVMA_U8`, `Pass_VMA` activated;
   `Pass_VMA` clears IRQ5 for a clean start.
2. **PIO0 next:** `ReadAddress` (SM0) activated and preloaded (Y = 23-bit shadow
   RAM base, X = all-ones for pin-dir); `GetWriteAddress` (SM1) activated and
   preloaded (Y = shadow RAM base); `WriteRam` (SM2) activated and clears
   IRQ4/5/6.

All state machines run at **150 MHz** (6.6 ns/cycle).
