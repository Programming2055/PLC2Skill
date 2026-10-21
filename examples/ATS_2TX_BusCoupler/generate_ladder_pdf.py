#!/usr/bin/env python3
"""
generate_ladder_pdf.py
======================

Self-contained reportlab generator that draws a professional PLC ladder-logic
sheet for an ATS (Automatic Transfer Switch) controlling two transformer
incomers plus a bus-coupler (classic "main-tie-main" low-voltage switchboard).

Output: ATS_ladder_diagram.pdf  (Letter, landscape, 2 pages)

Symbols drawn:
    ] [    normally-open (NO) contact
    ]/[    normally-closed (NC) contact
    ( )    output coil
    (S)    set / latch coil
    (R)    reset / unlatch coil
    TON    on-delay timer function block with IN / PT / ET / Q pins

Regenerate with:
    python generate_ladder_pdf.py
"""

from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch  # noqa: F401  (kept for readability)

# --------------------------------------------------------------------------
# Page geometry (points; 1 pt = 1/72")
# --------------------------------------------------------------------------
PAGE_W, PAGE_H = landscape(letter)          # 792 x 612

# Outer drawing frame
FRAME_L, FRAME_R = 24, PAGE_W - 24          # 24 .. 768
FRAME_B, FRAME_T = 24, PAGE_H - 24          # 24 .. 588

# Power rails
RAIL_L = 86                                 # left rail  (L1 / +24V)
RAIL_R = 744                                # right rail (N  / 0V)

# Title strip (top of frame)
TITLE_T = FRAME_T
TITLE_B = FRAME_T - 30

# Rung number gutter (between frame and left rail)
RUNG_NUM_X = FRAME_L + 18

# Colours (muted, print friendly)
C_WIRE   = (0.10, 0.10, 0.12)
C_RAIL   = (0.15, 0.25, 0.55)
C_TAG    = (0.05, 0.05, 0.05)
C_ADDR   = (0.45, 0.10, 0.10)
C_NOTE   = (0.30, 0.30, 0.35)
C_FRAME  = (0.20, 0.20, 0.25)

# --------------------------------------------------------------------------
# Low-level drawing helpers
# --------------------------------------------------------------------------

def set_rgb(c, rgb):
    c.setStrokeColorRGB(*rgb)


def fill_rgb(c, rgb):
    c.setFillColorRGB(*rgb)


def wire(c, x1, y1, x2, y2, w=1.2):
    set_rgb(c, C_WIRE)
    c.setLineWidth(w)
    c.line(x1, y1, x2, y2)


def tag_label(c, cx, y, tag, addr, dy_tag=15, dy_addr=-23, size_tag=7, size_addr=6.2):
    """Symbolic tag above an element, PLC address below it (both centred)."""
    if tag:
        fill_rgb(c, C_TAG)
        c.setFont("Helvetica-Bold", size_tag)
        c.drawCentredString(cx, y + dy_tag, tag)
    if addr:
        fill_rgb(c, C_ADDR)
        c.setFont("Helvetica-Oblique", size_addr)
        c.drawCentredString(cx, y + dy_addr, addr)


# ---- contacts -------------------------------------------------------------
CONTACT_W = 40          # total horizontal footprint
_BAR_GAP = 7            # half-gap between the two vertical bars
_BAR_H = 9             # half-height of a bar


def contact(c, lx, y, tag, addr, nc=False):
    """Draw a NO ( ] [ ) or NC ( ]/[ ) contact whose left lead starts at lx.
    Returns the x of the right lead (lx + CONTACT_W)."""
    rx = lx + CONTACT_W
    cx = (lx + rx) / 2.0
    xb_l, xb_r = cx - _BAR_GAP, cx + _BAR_GAP
    # leads
    wire(c, lx, y, xb_l, y)
    wire(c, xb_r, y, rx, y)
    # the two vertical bars
    set_rgb(c, C_WIRE)
    c.setLineWidth(1.4)
    c.line(xb_l, y - _BAR_H, xb_l, y + _BAR_H)
    c.line(xb_r, y - _BAR_H, xb_r, y + _BAR_H)
    if nc:
        # diagonal slash across the gap
        c.setLineWidth(1.2)
        c.line(xb_l - 1.5, y - _BAR_H - 1.5, xb_r + 1.5, y + _BAR_H + 1.5)
    tag_label(c, cx, y, tag, addr)
    return rx


# ---- coils ---------------------------------------------------------------
COIL_W = 40
_COIL_R = 12            # how far the parens bulge horizontally
_COIL_H = 9


def _coil_body(c, cx, y, letter=None):
    set_rgb(c, C_WIRE)
    c.setLineWidth(1.4)
    # left paren "(" bulging left
    c.bezier(cx - 4, y + _COIL_H,
             cx - _COIL_R, y + 4,
             cx - _COIL_R, y - 4,
             cx - 4, y - _COIL_H)
    # right paren ")" bulging right
    c.bezier(cx + 4, y + _COIL_H,
             cx + _COIL_R, y + 4,
             cx + _COIL_R, y - 4,
             cx + 4, y - _COIL_H)
    if letter:
        fill_rgb(c, C_WIRE)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, y - 3, letter)


def coil(c, lx, y, tag, addr, kind=None):
    """kind: None -> ( ) ; 'S' -> (S) ; 'R' -> (R). Left lead starts at lx.
    Returns right lead x."""
    rx = lx + COIL_W
    cx = (lx + rx) / 2.0
    wire(c, lx, y, cx - _COIL_R, y)
    wire(c, cx + _COIL_R, y, rx, y)
    _coil_body(c, cx, y, letter=kind)
    tag_label(c, cx, y, tag, addr)
    return rx


# ---- TON timer block ------------------------------------------------------
TMR_W = 96
TMR_H = 56


def ton_block(c, lx, y, name, addr, pt_text):
    """On-delay timer. The rung wire enters the IN pin (upper-left) and leaves
    the Q pin (upper-right) at height y. Returns the Q-pin x (right lead end).
    PT is annotated on the lower-left pin, ET on the lower-right pin."""
    box_l = lx + 10
    box_r = box_l + TMR_W
    # box vertically centred so the upper pins sit on the wire line y
    pin_up = y
    pin_dn = y - (TMR_H - 20)
    box_t = pin_up + 14
    box_b = pin_dn - 14
    # body
    set_rgb(c, C_FRAME)
    c.setLineWidth(1.3)
    c.setFillColorRGB(0.97, 0.97, 0.99)
    c.rect(box_l, box_b, box_r - box_l, box_t - box_b, stroke=1, fill=1)
    # title inside
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString((box_l + box_r) / 2.0, box_t - 13, "TON")
    c.setFont("Helvetica", 6.5)
    c.drawCentredString((box_l + box_r) / 2.0, box_t - 22, "on-delay")
    # pin labels
    c.setFont("Helvetica-Bold", 6.5)
    fill_rgb(c, C_WIRE)
    c.drawString(box_l + 3, pin_up - 2.5, "IN")
    c.drawString(box_l + 3, pin_dn - 2.5, "PT")
    c.drawRightString(box_r - 3, pin_up - 2.5, "Q")
    c.drawRightString(box_r - 3, pin_dn - 2.5, "ET")
    # leads IN (left) and Q (right) on the wire line
    wire(c, lx, pin_up, box_l, pin_up)
    wire(c, box_r, pin_up, box_r + 10, pin_up)
    # PT constant feeding lower-left pin
    fill_rgb(c, C_ADDR)
    c.setFont("Helvetica-Oblique", 6.2)
    c.drawRightString(box_l - 3, pin_dn - 2.5, pt_text)
    set_rgb(c, C_WIRE)
    c.setLineWidth(1.0)
    c.line(box_l - 2, pin_dn, box_l, pin_dn)
    # timer name + address above the block
    fill_rgb(c, C_TAG)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString((box_l + box_r) / 2.0, box_t + 4, name)
    fill_rgb(c, C_ADDR)
    c.setFont("Helvetica-Oblique", 6.2)
    c.drawCentredString((box_l + box_r) / 2.0, box_b - 9, addr)
    return box_r + 10


# ---- parallel (OR) group --------------------------------------------------

def parallel_group(c, gx_l, gx_r, y, upper, lower, spread=22):
    """Draw two contacts as parallel branches between nodes gx_l and gx_r.
    `upper`/`lower` are dicts: {tag, addr, nc}. The main rung line sits at y;
    branches sit at y+spread and y-spread. Returns gx_r."""
    yu, yd = y + spread, y - spread
    # vertical connectors (the OR nodes)
    set_rgb(c, C_WIRE)
    c.setLineWidth(1.2)
    c.line(gx_l, yd, gx_l, yu)
    c.line(gx_r, yd, gx_r, yu)
    # centre contact span inside the branch
    inner = CONTACT_W
    bl = (gx_l + gx_r) / 2.0 - inner / 2.0
    for yy, el in ((yu, upper), (yd, lower)):
        wire(c, gx_l, yy, bl, yy)
        rx = contact(c, bl, yy, el["tag"], el["addr"], nc=el.get("nc", False))
        wire(c, rx, yy, gx_r, yy)
    return gx_r


# --------------------------------------------------------------------------
# Rung scaffold (rails + number + comment)
# --------------------------------------------------------------------------

RAIL_TOP = 544


def rung_scaffold(c, num, y, comment, comment_dy=30):
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(RUNG_NUM_X, y - 3, num)
    if comment:
        fill_rgb(c, C_NOTE)
        c.setFont("Helvetica-Oblique", 6.8)
        c.drawString(RAIL_L + 4, y + comment_dy, comment)


def rails(c, bottom):
    set_rgb(c, C_RAIL)
    c.setLineWidth(2.2)
    c.line(RAIL_L, bottom, RAIL_L, RAIL_TOP)
    c.line(RAIL_R, bottom, RAIL_R, RAIL_TOP)
    fill_rgb(c, C_RAIL)
    c.setFont("Helvetica-Bold", 7.5)
    c.saveState()
    c.translate(RAIL_L - 6, RAIL_TOP - 54)
    c.rotate(90)
    c.drawString(0, 0, "L1 / +24V")
    c.restoreState()
    c.saveState()
    c.translate(RAIL_R + 11, RAIL_TOP - 54)
    c.rotate(90)
    c.drawString(0, 0, "N / 0V")
    c.restoreState()


# --------------------------------------------------------------------------
# Title block + legend
# --------------------------------------------------------------------------

def title_block(c, sheet_no, sheet_of):
    set_rgb(c, C_FRAME)
    c.setLineWidth(1.0)
    c.rect(FRAME_L, TITLE_B, FRAME_R - FRAME_L, TITLE_T - TITLE_B, stroke=1, fill=0)
    # vertical dividers for the right-hand cells
    x_cells = FRAME_R - 300
    c.line(x_cells, TITLE_B, x_cells, TITLE_T)
    # title text
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(FRAME_L + 10, TITLE_B + 16, "ATS — 2 Transformers + Bus Coupler (Main-Tie-Main)")
    c.setFont("Helvetica", 7.5)
    fill_rgb(c, C_NOTE)
    c.drawString(FRAME_L + 10, TITLE_B + 5,
                 "Automatic Transfer Switch – dual-incomer LV switchboard, open-transition bus-tie")
    # cells: drawing no / rev / date / sheet
    cells = [
        ("DWG No.", "ATS-LAD-001"),
        ("REV", "A"),
        ("DATE", "2026-10-21"),
        ("SHEET", "%d of %d" % (sheet_no, sheet_of)),
    ]
    cw = (FRAME_R - x_cells) / len(cells)
    for i, (k, v) in enumerate(cells):
        cxl = x_cells + i * cw
        if i:
            set_rgb(c, C_FRAME)
            c.line(cxl, TITLE_B, cxl, TITLE_T)
        fill_rgb(c, C_NOTE)
        c.setFont("Helvetica", 6)
        c.drawString(cxl + 4, TITLE_T - 9, k)
        fill_rgb(c, C_WIRE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(cxl + 4, TITLE_B + 7, v)


def legend(c):
    """A boxed symbol + I/O legend strip along the bottom of the frame."""
    ly_b = FRAME_B
    ly_t = FRAME_B + 44
    set_rgb(c, C_FRAME)
    c.setLineWidth(1.0)
    c.rect(FRAME_L, ly_b, FRAME_R - FRAME_L, ly_t - ly_b, stroke=1, fill=0)
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(FRAME_L + 6, ly_t - 9, "LEGEND / SYMBOLS")
    ymid = ly_b + 16
    x = FRAME_L + 14
    step = 118

    def item(label, drawer):
        nonlocal x
        drawer(x)
        fill_rgb(c, C_NOTE)
        c.setFont("Helvetica", 6.3)
        c.drawString(x + 46, ymid - 2, label)
        x += step

    # NO
    item("NO contact  ] [", lambda xx: contact(c, xx, ymid, "", "", nc=False))
    # NC
    item("NC contact  ]/[", lambda xx: contact(c, xx, ymid, "", "", nc=True))
    # coil
    item("Output coil  ( )", lambda xx: coil(c, xx, ymid, "", "", kind=None))
    # set
    item("Set/latch  (S)", lambda xx: coil(c, xx, ymid, "", "", kind="S"))
    # reset
    item("Reset  (R)", lambda xx: coil(c, xx, ymid, "", "", kind="R"))

    # second line: text notes about addressing + timer
    fill_rgb(c, C_NOTE)
    c.setFont("Helvetica", 6.3)
    c.drawString(FRAME_L + 14, ly_b + 4,
                 "Addresses:  %I = digital input (DI)   %Q = digital output (DO)   "
                 "%M = internal memory bit   T# = TON on-delay timer   "
                 "Tag shown above element, PLC address below.")


def frame(c):
    set_rgb(c, C_FRAME)
    c.setLineWidth(1.4)
    c.rect(FRAME_L, FRAME_B, FRAME_R - FRAME_L, FRAME_T - FRAME_B, stroke=1, fill=0)


# --------------------------------------------------------------------------
# SHEET 1
# --------------------------------------------------------------------------

def sheet1(c):
    frame(c)
    title_block(c, 1, 2)
    rails(c, FRAME_B + 50)
    legend(c)

    # ---- R1 : SYS_OK = AUTO_MODE AND (NOT LOCKOUT) ----
    y = 518
    rung_scaffold(c, "R1", y, "System-ready permissive: AUTO selected and no active lockout")
    x = RAIL_L
    x = contact(c, x, y, "AUTO_MODE", "%I0.0", nc=False)
    wire(c, x, y, x + 24, y); x += 24
    x = contact(c, x, y, "LOCKOUT", "%M20.0", nc=True)
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "SYS_OK", "%M10.0")

    # ---- R2 : Bus A undervoltage -> TON T_TRANS_A -> BUS_A_FAIL ----
    y = 424
    rung_scaffold(c, "R2", y, "Transformer-A incomer undervoltage, delayed 2 s, latches bus-A fail")
    x = RAIL_L
    x = contact(c, x, y, "UV_A", "%I0.1", nc=False)
    wire(c, x, y, x + 22, y); x += 22
    x = contact(c, x, y, "SYS_OK", "%M10.0", nc=False)
    wire(c, x, y, x + 22, y); x += 22
    x = ton_block(c, x, y, "T_TRANS_A", "T1  PT=2s", "PT=T#2s")
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "BUS_A_FAIL", "%M11.0")

    # ---- R3 : Bus B undervoltage -> TON T_TRANS_B -> BUS_B_FAIL ----
    y = 313
    rung_scaffold(c, "R3", y, "Transformer-B incomer undervoltage, delayed 2 s, latches bus-B fail")
    x = RAIL_L
    x = contact(c, x, y, "UV_B", "%I0.2", nc=False)
    wire(c, x, y, x + 22, y); x += 22
    x = contact(c, x, y, "SYS_OK", "%M10.0", nc=False)
    wire(c, x, y, x + 22, y); x += 22
    x = ton_block(c, x, y, "T_TRANS_B", "T2  PT=2s", "PT=T#2s")
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "BUS_B_FAIL", "%M11.1")

    # ---- R4 : BUS_A_FAIL -> Q1_TRIP ----
    y = 220
    rung_scaffold(c, "R4", y, "Open failed incomer 1 (transformer-A main breaker)")
    x = RAIL_L
    x = contact(c, x, y, "BUS_A_FAIL", "%M11.0", nc=False)
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "Q1_TRIP", "%Q0.0")

    # ---- R5 : BUS_B_FAIL -> Q2_TRIP ----
    y = 144
    rung_scaffold(c, "R5", y, "Open failed incomer 2 (transformer-B main breaker)")
    x = RAIL_L
    x = contact(c, x, y, "BUS_B_FAIL", "%M11.1", nc=False)
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "Q2_TRIP", "%Q0.1")

    c.showPage()


# --------------------------------------------------------------------------
# SHEET 2
# --------------------------------------------------------------------------

def sheet2(c):
    frame(c)
    title_block(c, 2, 2)
    rails(c, FRAME_B + 34)

    # ---- R6 : bus-tie close with 2-of-3 interlock ----
    y = 478
    rung_scaffold(c, "R6", y,
                  "Close bus-tie (Q3) on either bus fail, only if an incomer is already open",
                  comment_dy=56)
    # group 1 : (BUS_A_FAIL OR BUS_B_FAIL)
    g1_l = RAIL_L
    g1_r = g1_l + 150
    parallel_group(c, g1_l, g1_r, y, spread=34,
                   upper={"tag": "BUS_A_FAIL", "addr": "%M11.0", "nc": False},
                   lower={"tag": "BUS_B_FAIL", "addr": "%M11.1", "nc": False})
    # series link
    link = 40
    wire(c, g1_r, y, g1_r + link, y)
    # group 2 : ((NOT Q1_CL) OR (NOT Q2_CL))  -- the 2-of-3 interlock branch
    g2_l = g1_r + link
    g2_r = g2_l + 150
    parallel_group(c, g2_l, g2_r, y, spread=34,
                   upper={"tag": "Q1_CL", "addr": "%I1.0", "nc": True},
                   lower={"tag": "Q2_CL", "addr": "%I1.1", "nc": True})
    # to coil
    wire(c, g2_r, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "Q3_CLOSE", "%Q0.2")
    # explanatory note
    fill_rgb(c, C_NOTE)
    c.setFont("Helvetica-Oblique", 6.6)
    c.drawString(RAIL_L + 4, y - 72,
                 "NOTE (2-of-3 interlock): the bus-tie may close only when at least one incomer breaker is open "
                 "— never with all three breakers (Q1, Q2, Q3) closed, which would parallel the transformers.")

    # ---- R7 : Q1 reclose permit ----
    y = 368
    rung_scaffold(c, "R7", y, "Permit to reclose incomer 1 after transformer-A recovers")
    x = RAIL_L
    x = contact(c, x, y, "RETRANS_PERMIT", "%M12.0", nc=False)
    wire(c, x, y, x + 20, y); x += 20
    x = contact(c, x, y, "Q3_CL", "%I1.2", nc=True)
    wire(c, x, y, x + 20, y); x += 20
    x = contact(c, x, y, "RECOV_A", "%I0.3", nc=False)
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "Q1_CLOSE", "%Q0.3")

    # ---- R8 : Q2 reclose permit ----
    y = 300
    rung_scaffold(c, "R8", y, "Permit to reclose incomer 2 after transformer-B recovers")
    x = RAIL_L
    x = contact(c, x, y, "RETRANS_PERMIT", "%M12.0", nc=False)
    wire(c, x, y, x + 20, y); x += 20
    x = contact(c, x, y, "Q3_CL", "%I1.2", nc=True)
    wire(c, x, y, x + 20, y); x += 20
    x = contact(c, x, y, "RECOV_B", "%I0.4", nc=False)
    wire(c, x, y, RAIL_R - COIL_W, y)
    coil(c, RAIL_R - COIL_W, y, "Q2_CLOSE", "%Q0.4")

    # ---- R9 : retransfer timing (two lines) ----
    ya = 250          # line A (timer)
    yb = 196          # line B (trip coil)
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(RUNG_NUM_X, (ya + yb) / 2.0 - 3, "R9")
    fill_rgb(c, C_NOTE)
    c.setFont("Helvetica-Oblique", 6.8)
    c.drawString(RAIL_L + 4, ya + 34,
                 "Retransfer timing: confirm source A healthy for 5 s, then open-transition trip of tie")
    # line A: (NOT UV_A) AND RETRANS_PERMIT -> TON T_RETRANS
    x = RAIL_L
    x = contact(c, x, ya, "UV_A", "%I0.1", nc=True)
    wire(c, x, ya, x + 22, ya); x += 22
    x = contact(c, x, ya, "RETRANS_PERMIT", "%M12.0", nc=False)
    wire(c, x, ya, x + 22, ya); x += 22
    x = ton_block(c, x, ya, "T_RETRANS", "T3  PT=5s", "PT=T#5s")
    wire(c, x, ya, RAIL_R, ya)
    # line B: T_RETRANS.Q AND RECOV_A -> Q3_TRIP  (break-before-make)
    x = RAIL_L
    x = contact(c, x, yb, "T_RETRANS.Q", "T3.Q", nc=False)
    wire(c, x, yb, x + 24, yb); x += 24
    x = contact(c, x, yb, "RECOV_A", "%I0.3", nc=False)
    wire(c, x, yb, RAIL_R - COIL_W, yb)
    coil(c, RAIL_R - COIL_W, yb, "Q3_TRIP", "%Q0.5")
    fill_rgb(c, C_NOTE)
    c.setFont("Helvetica-Oblique", 6.4)
    c.drawString(RAIL_L + 4, yb - 32,
                 "Open-transition (break-before-make): the tie (Q3) opens before the recovered incomer recloses.")

    # ---- R10 : lockout latch (set / reset) ----
    ya = 120          # set line
    yb = 72           # reset line
    fill_rgb(c, C_WIRE)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(RUNG_NUM_X, (ya + yb) / 2.0 - 3, "R10")
    fill_rgb(c, C_NOTE)
    c.setFont("Helvetica-Oblique", 6.8)
    c.drawString(RAIL_L + 4, ya + 30, "Lockout latch — FAULT sets, RESET clears (seal-in broken by reset)")
    x = RAIL_L
    x = contact(c, x, ya, "FAULT", "%I2.0", nc=False)
    wire(c, x, ya, RAIL_R - COIL_W, ya)
    coil(c, RAIL_R - COIL_W, ya, "LOCKOUT", "%M20.0", kind="S")
    x = RAIL_L
    x = contact(c, x, yb, "RESET", "%I2.1", nc=False)
    wire(c, x, yb, RAIL_R - COIL_W, yb)
    coil(c, RAIL_R - COIL_W, yb, "LOCKOUT", "%M20.0", kind="R")

    c.showPage()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(path="ATS_ladder_diagram.pdf"):
    c = canvas.Canvas(path, pagesize=(PAGE_W, PAGE_H))
    c.setTitle("ATS Ladder Diagram - 2 Transformers + Bus Coupler")
    c.setAuthor("PLC2Skill")
    c.setSubject("Automatic Transfer Switch ladder logic (main-tie-main)")
    sheet1(c)
    sheet2(c)
    c.save()
    print("Wrote", path)


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    main(os.path.join(here, "ATS_ladder_diagram.pdf"))
