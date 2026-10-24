# ATS Control — 2 Transformers + Bus Coupler (Main-Tie-Main)

An automatic transfer scheme for a double-ended (main-tie-main) LV switchboard
fed by two transformers. Two incomer breakers (**Q1**, **Q2**) each feed their
own bus section (**Bus A**, **Bus B**), and a bus-coupler breaker (**Q3**) ties
the two sections together. In normal running both incomers are closed and the
tie is open. If one transformer source fails, the program trips the affected
incomer, waits an **open-transition dead time**, and closes the tie so the
surviving transformer feeds both buses. When the failed source returns healthy
and stable (and retransfer is enabled) the scheme transfers back to the normal
split configuration. A software **2-of-3 interlock** guarantees the two
transformers are never paralleled through the tie, and any breaker tripped by
protection is **locked out** with no automatic reclose.

---

## 1. Scope

This package is an engineering example / control-philosophy document. It
contains the SCL program blocks, the OB1 I/O mapping, a TIA-Portal-importable
tag list and this philosophy document. It implements the open-transition
main-tie-main transfer logic, source voltage supervision, a reusable breaker
control block, the 2-of-3 bus interlock and the source-fail / retransfer state
machine. Protection, synchronising and metering functions are **not** in the
PLC — they are relay/hardware functions that feed the PLC through digital
signals.

---

## 2. Assumptions & signal conventions

| Item | Assumption |
|------|-----------|
| Platform | SIMATIC S7-1500, TIA Portal, SCL (default). The structure ports to other PLC families by swapping the tag/address style (symbolic tags + `%I/%Q` addresses) for that platform's convention. |
| Transfer type | **Open transition (break-before-make)**, dead-bus. The two sources are never paralleled. A configurable dead time allows residual bus voltage to decay before the next breaker closes. |
| Source healthy | `*_Vpresent` / `I_S*_Vok` = **TRUE** when all three phases are present and within the monitoring relay's U< / U> limits. |
| Breaker closed | CLOSED aux contact (52a) = **TRUE** when the breaker is closed; OPEN aux (52b) = **TRUE** when open. Both-true or both-false is a discrepancy (aux/wiring fault). |
| Protection trip | `*_Trip` = **TRUE** when the breaker has been tripped by its protection relay. |
| Local switch | `*_Local` = **TRUE** when the breaker's Local/Remote switch is in **LOCAL** — the PLC then hands off and does not drive the coils. |
| Ready | `*_Ready` = **TRUE** when the breaker is racked-in, spring charged and ready to close. |
| Timer values | The starting values in `DB_ATS` (UV_FailDly, V_RtnDly, DeadTime, BkrOpTO) are **proposals to tune on site**. They are **not** from any source document. |
| Compilation | This code is **NOT compiled or simulated**. Treat it as a reviewed draft to be compiled in TIA Portal. |
| Protection / sync-check | Overcurrent, earth-fault, differential and sync-check (ANSI 25) are **relay / hardware** functions, not PLC functions. |

---

## 3. One-line / topology diagram

```
      TR1                               TR2
       |                                 |
       |                                 |
     [ Q1 ]  Incomer 1            [ Q2 ]  Incomer 2
       |                                 |
   ====+========= Bus A      Bus B =========+====
                     |          |
                     +--[ Q3 ]--+
                     Bus coupler (tie)

   Normal:  Q1 closed, Q2 closed, Q3 OPEN   (buses run split)
   TR1 lost: Q1 tripped -> dead time -> Q3 closed   (TR2 feeds both)
   TR2 lost: Q2 tripped -> dead time -> Q3 closed   (TR1 feeds both)
```

---

## 4. Equipment

| Tag | Description | Notes |
|-----|-------------|-------|
| TR1 | Transformer 1 — source for Bus A | Rating / vector group: to confirm (project-specific) |
| TR2 | Transformer 2 — source for Bus B | Rating / vector group: to confirm (project-specific) |
| Q1 | Incomer 1 ACB (TR1 → Bus A) | Breaker type / frame: to confirm (project-specific) |
| Q2 | Incomer 2 ACB (TR2 → Bus B) | Breaker type / frame: to confirm (project-specific) |
| Q3 | Bus-coupler (tie) ACB between Bus A and Bus B | Breaker type / frame: to confirm (project-specific) |
| S1 | TR1 source voltage monitoring relay (3-phase) | Digital "volts healthy" output to PLC |
| S2 | TR2 source voltage monitoring relay (3-phase) | Digital "volts healthy" output to PLC |

---

## 5. Program structure

| Block | Type | Role |
|-------|------|------|
| `FB_VMon` | FB | Source voltage monitor: debounces the monitoring-relay signal with a fail delay (U< confirmation) and a return delay, producing `Healthy` / `Failed`. |
| `FB_Breaker` | FB | Generic breaker control: position decode, protection-trip lockout, fail-to-operate supervision, close interlock, manual/auto command resolution, open-dominates-close. |
| `FB_ATS_2TX_BusCoupler` | FB | Main-tie-main sequencer. Owns two `FB_VMon` and three `FB_Breaker` multi-instances; runs the 2-of-3 interlock and the open-transition state machine. |
| `IDB_ATS` | Instance DB | Instance data block of `FB_ATS_2TX_BusCoupler`. |
| `DB_ATS` | Global DB | HMI mode/commands and ATS setpoints (timers); holds the live `State`. |
| `OB_Main` | OB1 | Cyclic call of `IDB_ATS`, mapping physical I/O (via `PLC_Tags.csv`) and `DB_ATS` to the FB ports. |

---

## 6. Sequence of operation

All automatic transitions require `AutoMode = TRUE`. In manual mode the
operator drives each breaker through the HMI, but the 2-of-3 close interlock and
the protection lockout are still enforced by `FB_Breaker`.

**Normal (state 1).** Both sources healthy. Q1 and Q2 closed, Q3 (tie) open.
Buses A and B run split, each on its own transformer.

**Loss of TR1 (states 2 → 9 → 3).** `FB_VMon` for S1 confirms undervoltage for
`UV_FailDly` and sets `S1.Failed`. With S2 still healthy, the sequencer trips
incomer **Q1** (tie held open). When Q1's OPEN aux confirms, the scheme arms
`DeadTime` and enters the dead-time state (9). After the dead time it goes to
state 3, closing the tie **Q3** so **TR2 feeds both buses** (Q2 + Q3 closed,
Q1 open).

**Loss of TR2 (states 4 → 9 → 5).** Mirror image: S2 confirmed failed with S1
healthy, trip incomer **Q2**, dead time, then close the tie **Q3** so **TR1
feeds both buses** (Q1 + Q3 closed, Q2 open).

**Both sources lost (state 8).** If both monitors report failed (either from
state 1, or a second source lost while running on the tie), the scheme opens all
breakers (Q1, Q2, Q3 all commanded open) and waits. When the **first** source
returns healthy it auto-restores to that source feeding both buses (to state 5
if S1 returns first, state 3 if S2 returns first); if both are healthy it
returns to INIT (state 0) which re-establishes normal split running.

**Retransfer (states 6 / 7 → 9 → 1).** When the previously failed source returns
and `FB_VMon` holds `Healthy` for `V_RtnDly`, and `RetransEnable = TRUE`, the
scheme transfers back to normal: it opens the tie **Q3**, waits `DeadTime`, then
recloses the restored incomer (state 1). This is an **open-transition**
retransfer, so the restored bus sees a **momentary interruption** during the
dead time — there is no synchronised (closed-transition) make.

**Protection trip (any state).** A breaker tripped by its protection relay
(`*_Trip`) latches `FB_Breaker.Locked`. While locked the block holds an open/
trip command and refuses any close — **no automatic reclose onto a fault**.
Clearing requires the fault to be gone and a manual `Reset` (HMI `ATSReset`).

---

## 7. State table

`step` (output `State`) drives the Q1/Q2/Q3 close/open requests (`r1c/r1o`,
`r2c/r2o`, `r3c/r3o`). `C` = close requested, `O` = open/trip requested,
`-` = request unchanged / not driven in that state.

| State | Name | Q1 | Q2 | Q3 | Entry condition | Exit / next |
|------:|------|----|----|----|-----------------|-------------|
| 0 | INIT | - | - | - | Power-up; or both sources healthy from state 8 | S1&S2 healthy → 1; S1 only → 5; S2 only → 3; neither → 8 |
| 1 | NORMAL | C | C | O | From INIT with both healthy; from retransfer | S1 failed & S2 healthy → 2; S2 failed & S1 healthy → 4; both failed → 8 (auto mode) |
| 2 | TRIP Q1 | O | C | hold | S1 failed in NORMAL | Q1 OPEN confirmed → arm dead time, next = 3 → 9 |
| 3 | RUN on TR2 | O | C | C | After dead time from state 2; S2 returns first from 8 | S2 failed → 8; S1 healthy & retrans → 6 |
| 4 | TRIP Q2 | C | O | hold | S2 failed in NORMAL | Q2 OPEN confirmed → arm dead time, next = 5 → 9 |
| 5 | RUN on TR1 | C | O | C | After dead time from state 4; S1 returns first from 8 | S1 failed → 8; S2 healthy & retrans → 7 |
| 6 | RETRANSFER → normal (from TR2) | - | - | O | S1 healthy & stable & retrans, from state 3 | Q3 OPEN confirmed → arm dead time, next = 1 → 9 |
| 7 | RETRANSFER → normal (from TR1) | - | - | O | S2 healthy & stable & retrans, from state 5 | Q3 OPEN confirmed → arm dead time, next = 1 → 9 |
| 8 | BOTH DEAD | O | O | O | Both sources failed | S1 only → 5; S2 only → 3; both → 0 |
| 9 | DEAD-TIME | - | - | - | Entered from 2/4/6/7 (break-before-make) | `DeadTime` elapsed → go to `nextAfterDead` |

Note: in states 2 and 4 the tie close request is explicitly held off (`r3c := FALSE`)
so the incomer trip and the dead time complete before the tie is allowed to close.

---

## 8. Interlock matrix

| # | Rule (intent) | Signal(s) | Implemented by |
|---|---------------|-----------|----------------|
| 1 | **2-of-3**: Q1, Q2 and Q3 are never all closed together (no parallel of the two transformers through the tie). | `inh1 = Q2_Closed AND Q3_Closed`; `inh2 = Q1_Closed AND Q3_Closed`; `inh3 = Q1_Closed AND Q2_Closed` | `FB_ATS_2TX_BusCoupler` computes `inh1/inh2/inh3` and passes each to `FB_Breaker.Inhibit`, which blocks that breaker's close. **Must also be hardwired** between the three breakers as a backup. |
| 2 | **No auto-reclose onto a protection trip.** | `*_Trip` → `Locked` | `FB_Breaker` latches `Locked` on `TripAlarm`; while locked it asserts open and refuses close. Reset needs fault clear + `Reset`. |
| 3 | **Fail-to-operate lockout.** | close/open command vs confirmed position + `OpTime` | `FB_Breaker` sets `Fault` if the breaker doesn't reach the commanded position within `OpTime`; `Fault` blocks further close until `Reset`. |
| 4 | **Local hands-off.** | `*_Local` | `FB_Breaker`: when `LocalHW` is TRUE the PLC drives neither coil (operator uses local control). |
| 5 | **Open/trip dominates close.** | internal | `FB_Breaker`: after command resolution, if `OpenCmd` then `CloseCmd := FALSE` — both are never asserted together. |
| 6 | **Interlock alarm.** | `r*c AND inh*` | `FB_ATS_2TX_BusCoupler` sets `Alm_Interlock` when a close is requested while that breaker is inhibited. |

---

## 9. Truth tables

### T1 — `FB_Breaker` command resolution

Inputs: operating mode (Local / Manual / Auto), the close request for that mode
(`AutoClose` in auto, `ManClose` in manual), the open request (`AutoOpen` /
`ManOpen`), and the blocks `Inhibit`, `Locked`, `Fault`. `Ready` assumed TRUE
where a close is evaluated. Outputs: `CloseCmd`, `OpenCmd`.

| LocalHW | ManMode | Close req | Open req | Inhibit | Locked | Fault | CloseCmd | OpenCmd |
|:------:|:------:|:--------:|:-------:|:------:|:-----:|:----:|:-------:|:------:|
| TRUE | x | x | x | x | x | x | FALSE | FALSE |
| FALSE | TRUE | TRUE | FALSE | FALSE | FALSE | FALSE | **TRUE** | FALSE |
| FALSE | TRUE | TRUE | FALSE | TRUE | x | x | FALSE | FALSE |
| FALSE | TRUE | x | TRUE | x | x | x | FALSE | **TRUE** |
| FALSE | FALSE | TRUE (auto) | FALSE | FALSE | FALSE | FALSE | **TRUE** | FALSE |
| FALSE | FALSE | TRUE (auto) | FALSE | TRUE | x | x | FALSE | FALSE |
| FALSE | FALSE | TRUE (auto) | FALSE | FALSE | FALSE | TRUE | FALSE | FALSE |
| FALSE | FALSE | x | TRUE (auto) | x | x | x | FALSE | **TRUE** |
| FALSE | FALSE | x | x | x | TRUE | x | FALSE | **TRUE** |

Rules shown: Local → both coils off; a close needs Ready, no Inhibit, no Locked,
no Fault; open/trip is always permitted and dominates close; `Locked` forces an
open command (hold open) in auto.

### T2 — `FB_VMon` (debounced source monitor)

| Enable | VpresentHW | Condition held | Healthy | Failed |
|:------:|:----------:|----------------|:------:|:-----:|
| FALSE | x | — | FALSE | FALSE |
| TRUE | FALSE | < `FailDly` | FALSE | FALSE |
| TRUE | FALSE | ≥ `FailDly` | FALSE | **TRUE** |
| TRUE | TRUE | < `RtnDly` | FALSE | FALSE (prev holds until a timer elapses) |
| TRUE | TRUE | ≥ `RtnDly` | **TRUE** | FALSE |

When `Enable` (VT/monitor supply) is FALSE the monitor declares neither Healthy
nor Failed — it avoids a nuisance transfer on a monitor supply loss.

### T3 — 2-of-3 bus interlock (which close is inhibited)

| Q1 closed | Q2 closed | Q3 closed | inh1 (Q1 close) | inh2 (Q2 close) | inh3 (Q3 close) | Note |
|:--------:|:--------:|:--------:|:--------------:|:--------------:|:--------------:|------|
| F | F | F | F | F | F | all open |
| T | F | F | F | F | F | only Q1 closed |
| F | T | F | F | F | F | only Q2 closed |
| F | F | T | F | F | F | only tie closed |
| T | T | F | F | F | **T** | normal split — tie close inhibited |
| T | F | T | F | **T** | F | TR1 feeds both — Q2 close inhibited |
| F | T | T | **T** | F | F | TR2 feeds both — Q1 close inhibited |
| T | T | T | **T** | **T** | **T** | **PROHIBITED** — must never occur (software + hardwired interlock) |

---

## 10. IO list

### Digital inputs (19)

| Tag | Description | Breaker / Source |
|-----|-------------|------------------|
| `I_S1_Vok` | TR1 source volts healthy (monitoring relay) | S1 |
| `I_S2_Vok` | TR2 source volts healthy (monitoring relay) | S2 |
| `I_VT1_On` | TR1 voltage-monitor supply healthy (enable) | S1 |
| `I_VT2_On` | TR2 voltage-monitor supply healthy (enable) | S2 |
| `I_Q1_Closed` | Q1 incomer-1 CLOSED aux (52a) | Q1 |
| `I_Q1_Open` | Q1 incomer-1 OPEN aux (52b) | Q1 |
| `I_Q1_Ready` | Q1 racked-in + spring charged + ready | Q1 |
| `I_Q1_Trip` | Q1 tripped by protection | Q1 |
| `I_Q1_Local` | Q1 Local/Remote switch in LOCAL | Q1 |
| `I_Q2_Closed` | Q2 incomer-2 CLOSED aux (52a) | Q2 |
| `I_Q2_Open` | Q2 incomer-2 OPEN aux (52b) | Q2 |
| `I_Q2_Ready` | Q2 racked-in + spring charged + ready | Q2 |
| `I_Q2_Trip` | Q2 tripped by protection | Q2 |
| `I_Q2_Local` | Q2 Local/Remote switch in LOCAL | Q2 |
| `I_Q3_Closed` | Q3 bus-coupler CLOSED aux (52a) | Q3 |
| `I_Q3_Open` | Q3 bus-coupler OPEN aux (52b) | Q3 |
| `I_Q3_Ready` | Q3 racked-in + spring charged + ready | Q3 |
| `I_Q3_Trip` | Q3 tripped by protection | Q3 |
| `I_Q3_Local` | Q3 Local/Remote switch in LOCAL | Q3 |

### Digital outputs (6)

| Tag | Description | Breaker |
|-----|-------------|---------|
| `Q_Q1_Close` | Q1 close coil | Q1 |
| `Q_Q1_Trip` | Q1 shunt-trip coil | Q1 |
| `Q_Q2_Close` | Q2 close coil | Q2 |
| `Q_Q2_Trip` | Q2 shunt-trip coil | Q2 |
| `Q_Q3_Close` | Q3 close coil | Q3 |
| `Q_Q3_Trip` | Q3 shunt-trip coil | Q3 |

### Not wired — HMI only

These live in `DB_ATS` and are set from the HMI / engineering, not from field I/O:

- `AutoMode`, `RetransEnable`, `ClosedTrans`
- `ATSReset`, `AlarmReset`
- `Q1_ManClose`, `Q1_ManOpen`, `Q2_ManClose`, `Q2_ManOpen`, `Q3_ManClose`, `Q3_ManOpen`
- Setpoint timers: `UV_FailDly`, `V_RtnDly`, `DeadTime`, `BkrOpTO`

### Totals

- **19 DI, 6 DO, 0 AI, 0 AQ.**
- Voltage sensing is via digital monitoring relays, so there are no analog
  channels in this design.
- Recommend **~20% spare** per I/O card for future additions.

---

## 11. PLC variables

The 25 physical I/O tags are defined in **`scl/PLC_Tags.csv`** (TIA-Portal
importable; columns `Name, Path, Data Type, Logical Address, Comment`). The
`%I` / `%Q` logical addresses in that file are **sequential placeholders** until
the hardware configuration exists — import the CSV via the TIA Portal tag-table
CSV import and then re-address to match the real rack/module layout.

Non-I/O variables live in the global data block **`DB_ATS`**:

| Name | Type | Starting value | Comment |
|------|------|---------------|---------|
| `AutoMode` | Bool | `TRUE` | TRUE = ATS auto; FALSE = ATS manual |
| `RetransEnable` | Bool | `TRUE` | Auto retransfer to normal on source return |
| `ClosedTrans` | Bool | `FALSE` | FALSE = open transition (this program); closed transition not implemented |
| `ATSReset` | Bool | — | Reset breaker faults / lockouts |
| `AlarmReset` | Bool | — | Reset / acknowledge alarms (HMI) |
| `Q1_ManClose` | Bool | — | Manual close Q1 (when AutoMode = FALSE) |
| `Q1_ManOpen` | Bool | — | Manual open Q1 |
| `Q2_ManClose` | Bool | — | Manual close Q2 |
| `Q2_ManOpen` | Bool | — | Manual open Q2 |
| `Q3_ManClose` | Bool | — | Manual close Q3 |
| `Q3_ManOpen` | Bool | — | Manual open Q3 |
| `UV_FailDly` | Time | `T#3s` | Source-fail confirmation (ride-through dips) |
| `V_RtnDly` | Time | `T#10s` | Healthy-return stabilisation before retransfer |
| `DeadTime` | Time | `T#1s` | Open-transition dead time (residual-volts decay) |
| `BkrOpTO` | Time | `T#2s` | Breaker operation timeout |
| `State` | Int | — | Live sequencer state (written by the ATS FB) |

---

## 12. Open points / to confirm

1. **Open vs closed transition.** This design is **open transition** (break-
   before-make) — the sources are never paralleled and the restored bus sees a
   momentary interruption. A closed-transition (make-before-break) retransfer
   would need a **25 sync-check relay** and an explicit paralleling permission;
   it is **not implemented** here (`DB_ATS.ClosedTrans` is a placeholder flag).
2. **Timer values.** `DeadTime`, `UV_FailDly`, `V_RtnDly` and `BkrOpTO` are
   proposed starting values to **tune on site** against residual-voltage decay,
   supply dip ride-through and breaker operating times.
3. **Preferred source.** This design is **symmetric** — neither transformer is a
   preferred source. A preferred-source option (e.g. always retransfer to TR1)
   can be added if required.
4. **Single-transformer capacity.** When one transformer carries **both** buses,
   its rating may be exceeded. **Load-shedding / non-essential-load tripping**
   may be required before or on tie close — to confirm against the load schedule.
5. **Hardwired interlock.** A **hardwired 2-of-3 interlock** between the three
   breakers is **mandatory** as a backup to the software interlock in
   `FB_ATS`/`FB_Breaker`.
6. **Protection signals.** Overcurrent / earth-fault / differential are **relay**
   functions that feed the `*_Trip` inputs; they are not computed in the PLC.
7. **Output pulsing.** The close/trip outputs are shown **maintained** in the
   logic; convert them to **pulses** to the close and shunt-trip coils at the
   output module (per coil ratings / breaker requirements).
8. **Voltage sensing.** Voltage is sensed via **digital monitoring relays**. Add
   **analog VT metering** if continuous voltage measurement / display is required.

---

## 13. FAT checklist

- [ ] Compile the program in TIA Portal (all blocks, no errors).
- [ ] Simulate **Normal** running: Q1 & Q2 closed, Q3 open.
- [ ] Simulate **Loss of TR1**: confirm U< for `UV_FailDly`, Q1 trips, dead time, Q3 closes, TR2 feeds both buses (state 3).
- [ ] Simulate **Loss of TR2**: confirm U< for `UV_FailDly`, Q2 trips, dead time, Q3 closes, TR1 feeds both buses (state 5).
- [ ] Simulate **both sources dead**: all breakers open; confirm lockout and auto-restore to the first source that returns.
- [ ] Simulate **retransfer each way** (TR1→normal and TR2→normal): source healthy & stable for `V_RtnDly`, tie opens, dead time, incomer recloses; verify the momentary open-transition interruption.
- [ ] Simulate **protection-trip lockout**: assert `*_Trip`, confirm `Locked`, confirm **no auto-reclose** and that reset needs fault clear + `ATSReset`.
- [ ] Simulate **breaker fail-to-operate**: command close/open without feedback, confirm `Fault` after `BkrOpTO` and the close block.
- [ ] Verify **Local hands-off**: with `*_Local` TRUE the PLC drives neither coil.
- [ ] Verify the **2-of-3 interlock** blocks the all-three-closed case in **software** AND confirm it is **hardwired**.
- [ ] Verify the **open-transition dead time** between breaker operations.
- [ ] Verify **HMI manual mode**: manual close/open per breaker, with interlocks and lockout still enforced.
- [ ] Verify **alarms**: `Alm_S1_Fail`, `Alm_S2_Fail`, `Alm_BothDead`, `Alm_Q1/2/3_Fault`, `Alm_Interlock`.
