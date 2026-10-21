# ATS — 2 Transformers + Bus Coupler (Main-Tie-Main)

PLC ladder-logic deliverable for an **Automatic Transfer Switch (ATS)** on a
dual-incomer low-voltage switchboard with a bus-coupler — the classic
**main-tie-main** arrangement.

- `generate_ladder_pdf.py` — self-contained [reportlab](https://www.reportlab.com/)
  script that draws the ladder sheet.
- `ATS_ladder_diagram.pdf` — the rendered drawing (Letter, landscape, **2 pages**).
- `README.md` — this document.

## The switchboard

```
   Transformer A                         Transformer B
        |                                     |
      [ Q1 ]  main breaker              [ Q2 ]  main breaker
        |                                     |
   ===== BUS A =====[ Q3  bus-tie ]===== BUS B =====
        |                                     |
     loads A                               loads B
```

Two transformers each feed their own bus section through a main incomer breaker
(**Q1**, **Q2**). A normally-open **bus-tie / bus-coupler** breaker (**Q3**) can
link the two bus sections so that a single healthy transformer can carry both
loads when the other source is lost.

## Control sequence

### Normal operation
Both transformers are healthy, **Q1** and **Q2** are closed, **Q3** (tie) is
**open**. Each bus is fed from its own source. `AUTO_MODE` is selected and no
`LOCKOUT` is active, so `SYS_OK` is true and the automatic logic is armed.

### Transfer (loss of a source)
1. Undervoltage on an incomer (`UV_A` / `UV_B`) while `SYS_OK` is true starts an
   on-delay timer (`T_TRANS_A` / `T_TRANS_B`, **PT = 2 s**) to ride through
   transient dips.
2. If the undervoltage persists past the delay, the corresponding bus-fail flag
   latches (`BUS_A_FAIL` / `BUS_B_FAIL`).
3. The bus-fail flag **trips the failed incomer** (`Q1_TRIP` / `Q2_TRIP`) so the
   dead source is isolated first.
4. With at least one incomer now open, the **bus-tie closes** (`Q3_CLOSE`) and the
   surviving transformer picks up both bus sections.

### Retransfer (source recovery)
1. When the lost source returns, the recovery signal (`RECOV_A` / `RECOV_B`) and
   `RETRANS_PERMIT` enable the reclose permissives (`Q1_CLOSE` / `Q2_CLOSE`),
   gated by the tie still being closed (`Q3_CL`).
2. A retransfer timer (`T_RETRANS`, **PT = 5 s**) confirms the source has been
   stable (`NOT UV_A`) before acting.
3. The retransfer is **open-transition (break-before-make)**: the tie is tripped
   (`Q3_TRIP`) *before* the recovered incomer recloses, so the two transformers
   are never paralleled through the tie.

### Lockout
A `FAULT` **sets** the `LOCKOUT` latch, which drops `SYS_OK` and blocks all
automatic action. The latch is sealed in until an operator `RESET` **resets**
it (seal-in broken by reset).

## 2-of-3 interlock (safety rule)

The three breakers **Q1 (incomer 1)**, **Q2 (incomer 2)** and **Q3 (bus-tie)**
must **never all be closed at the same time**. Closing all three would parallel
transformer A and transformer B through the tie — an uncontrolled parallel that
can cause large circulating / fault currents.

The rule is enforced on the tie-close rung (R6): `Q3_CLOSE` is permitted only
through the interlock branch `((NOT Q1_CL) OR (NOT Q2_CL))`, i.e. the tie may
close **only when at least one incomer is already open**. Combined with the
open-transition retransfer (tie trips before an incomer recloses), at most two
of the three breakers are ever closed together.

## Rung summary

| Rung | Function |
|------|----------|
| R1   | `SYS_OK = AUTO_MODE · (NOT LOCKOUT)` — system-ready permissive |
| R2   | Bus-A undervoltage → TON `T_TRANS_A` (2 s) → latch `BUS_A_FAIL` |
| R3   | Bus-B undervoltage → TON `T_TRANS_B` (2 s) → latch `BUS_B_FAIL` |
| R4   | `BUS_A_FAIL` → `Q1_TRIP` (open failed incomer 1) |
| R5   | `BUS_B_FAIL` → `Q2_TRIP` (open failed incomer 2) |
| R6   | `(BUS_A_FAIL OR BUS_B_FAIL) · ((NOT Q1_CL) OR (NOT Q2_CL))` → `Q3_CLOSE` (2-of-3 interlock) |
| R7   | `RETRANS_PERMIT · (NOT Q3_CL) · RECOV_A` → `Q1_CLOSE` |
| R8   | `RETRANS_PERMIT · (NOT Q3_CL) · RECOV_B` → `Q2_CLOSE` |
| R9   | `(NOT UV_A) · RETRANS_PERMIT` → TON `T_RETRANS` (5 s); `T_RETRANS.Q · RECOV_A` → `Q3_TRIP` |
| R10  | `FAULT` → (S) `LOCKOUT` ; `RESET` → (R) `LOCKOUT` |

## PLC tag / I-O list

| Tag | Address | I/O type | Description |
|-----|---------|----------|-------------|
| AUTO_MODE      | %I0.0 | DI       | Auto mode selected (vs. manual/off) |
| UV_A           | %I0.1 | DI       | Undervoltage detected on transformer-A incomer |
| UV_B           | %I0.2 | DI       | Undervoltage detected on transformer-B incomer |
| RECOV_A        | %I0.3 | DI       | Transformer-A source recovered / healthy |
| RECOV_B        | %I0.4 | DI       | Transformer-B source recovered / healthy |
| Q1_CL          | %I1.0 | DI       | Incomer-1 breaker closed (aux contact) |
| Q2_CL          | %I1.1 | DI       | Incomer-2 breaker closed (aux contact) |
| Q3_CL          | %I1.2 | DI       | Bus-tie breaker closed (aux contact) |
| FAULT          | %I2.0 | DI       | External/protection fault → lockout |
| RESET          | %I2.1 | DI       | Operator lockout reset pushbutton |
| Q1_TRIP        | %Q0.0 | DO       | Trip incomer-1 breaker |
| Q2_TRIP        | %Q0.1 | DO       | Trip incomer-2 breaker |
| Q3_CLOSE       | %Q0.2 | DO       | Close bus-tie breaker |
| Q1_CLOSE       | %Q0.3 | DO       | Close incomer-1 breaker |
| Q2_CLOSE       | %Q0.4 | DO       | Close incomer-2 breaker |
| Q3_TRIP        | %Q0.5 | DO       | Trip bus-tie breaker (open-transition) |
| SYS_OK         | %M10.0 | internal | System-ready permissive |
| BUS_A_FAIL     | %M11.0 | internal | Bus-A fail latch |
| BUS_B_FAIL     | %M11.1 | internal | Bus-B fail latch |
| RETRANS_PERMIT | %M12.0 | internal | Retransfer permitted (auto return enabled) |
| LOCKOUT        | %M20.0 | internal | Lockout latch (set/reset) |
| T_TRANS_A      | T1 (PT = T#2s) | timer | Bus-A transfer on-delay (TON) |
| T_TRANS_B      | T2 (PT = T#2s) | timer | Bus-B transfer on-delay (TON) |
| T_RETRANS      | T3 (PT = T#5s) | timer | Retransfer confirm on-delay (TON); `T3.Q` used on R9 |

*DI = digital input (%I), DO = digital output (%Q), internal = memory bit (%M),
timer = TON on-delay function block.*

## How to regenerate

```
python generate_ladder_pdf.py
```

Requires `reportlab`. Produces `ATS_ladder_diagram.pdf` in this directory.
