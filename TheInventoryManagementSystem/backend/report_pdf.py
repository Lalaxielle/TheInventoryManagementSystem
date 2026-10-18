"""Server-side PDF for the Reports page ("Save as PDF").

Lays the report out as a real landscape-A4 document with reportlab, so the
report preview bar can offer an actual PDF file the user can save and then
print - the browser print dialog alone never produced a file.

Black / white / grey only: the palette defined in static/css/style.css.
"""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle, KeepTogether)

from backend.models import civil_time, fmt_date, warranty_state

# --------------------------------------------------------------- palette
BLACK = colors.HexColor("#000000")
INK = colors.HexColor("#0a0a0b")
G900 = colors.HexColor("#18181b")
G700 = colors.HexColor("#3f3f46")
G500 = colors.HexColor("#71717a")
G300 = colors.HexColor("#d4d4d8")
G200 = colors.HexColor("#e4e4e7")
G100 = colors.HexColor("#f1f1f2")
G50 = colors.HexColor("#f7f7f8")
WHITE = colors.white

PAGE = landscape(A4)
MARGIN = 12 * mm
BOTTOM = 18 * mm
USABLE = PAGE[0] - 2 * MARGIN          # ~273 mm of live width

# ----------------------------------------------------------------- styles
S_TITLE = ParagraphStyle(
    "title", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=WHITE)
S_KICKER = ParagraphStyle(
    "kicker", fontName="Helvetica-Bold", fontSize=8, leading=10,
    textColor=G300)
S_SUB = ParagraphStyle(
    "sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=WHITE)
S_META_R = ParagraphStyle(
    "metar", fontName="Helvetica", fontSize=8, leading=10.5,
    textColor=G300, alignment=TA_RIGHT)
# the title band is centred, like the report header on the Reports page
S_TITLE_C = ParagraphStyle("titlec", parent=S_TITLE, alignment=TA_CENTER)
S_KICKER_C = ParagraphStyle("kickerc", parent=S_KICKER, alignment=TA_CENTER)
S_META_C = ParagraphStyle("metac", parent=S_META_R, alignment=TA_CENTER)
S_H2 = ParagraphStyle(
    "h2", fontName="Helvetica-Bold", fontSize=10, leading=12,
    textColor=BLACK, spaceBefore=2, spaceAfter=4)
S_TH = ParagraphStyle(
    "th", fontName="Helvetica-Bold", fontSize=7.2, leading=8.6, textColor=WHITE)
S_TD = ParagraphStyle(
    "td", fontName="Helvetica", fontSize=7.2, leading=8.6, textColor=G900)
S_TD_B = ParagraphStyle(
    "tdb", fontName="Helvetica-Bold", fontSize=7.2, leading=8.6, textColor=BLACK)
S_QTY = ParagraphStyle(
    "qty", parent=S_TD_B, alignment=TA_RIGHT)
S_STAT_K = ParagraphStyle(
    "statk", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=G500)
S_STAT_V = ParagraphStyle(
    "statv", fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=BLACK)
S_STAT_N = ParagraphStyle(
    "statn", fontName="Helvetica", fontSize=6.8, leading=8.5, textColor=G500)
S_NOTE = ParagraphStyle(
    "note", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=G500)


def _text(value) -> str:
    """Coerce *value* to a string the built-in Helvetica can actually draw.

    WinAnsi (cp1252) is the encoding reportlab uses for the standard Type1
    fonts, so anything outside it would raise or print a black box. Common
    typographic characters are folded to their ASCII form first.
    """
    if value is None:
        return "-"
    text = str(value)
    for src, dst in (("\u2013", "-"), ("\u2014", "-"), ("\u2018", "'"),
                     ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                     ("\u2022", "-"), ("\u00a0", " "), ("\u2264", "<="),
                     ("\u2265", ">=")):
        text = text.replace(src, dst)
    return text.encode("cp1252", "replace").decode("cp1252")


def _p(value, style=S_TD) -> Paragraph:
    """Paragraph for a table cell - *value* is escaped because Paragraph
    parses the string as markup."""
    text = _text(value).strip() or "-"
    return Paragraph(escape(text), style)


def _table(headers, rows, widths, *, right=(), empty="No records."):
    """Build a striped, black-headed table.

    *right* lists column indexes whose cells are right-aligned (counts).
    """
    data = [[_p(h, S_TH) for h in headers]]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append(_p(cell, S_QTY if i in right else S_TD))
        data.append(cells)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, G200),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, G50]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    if not rows:
        data.append([_p(empty, S_TD)] + [""] * (len(headers) - 1))
        style.append(("SPAN", (0, 1), (-1, 1)))

    return Table(data, colWidths=widths, repeatRows=1,
                 style=TableStyle(style))


def _footer(canvas, doc):
    """Thin rule plus copyright / page number at the foot of every page."""
    canvas.saveState()
    canvas.setStrokeColor(G200)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 13 * mm, PAGE[0] - MARGIN, 13 * mm)
    canvas.setFillColor(G500)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 9 * mm,
                      "\u00a9 2026 The ITEQ Company. All rights reserved.")
    canvas.drawRightString(PAGE[0] - MARGIN, 9 * mm,
                           "Page %d" % canvas.getPageNumber())
    canvas.restoreState()


def _pairs(mapping):
    """(label, count) rows from a dict or from location_summary()."""
    if isinstance(mapping, dict):
        return list(mapping.items())
    return [(g.get("location"), g.get("total")) for g in (mapping or [])]


def build_report_pdf(stats, equipment, warranty_rows, locations,
                     generated_by="", generated_at=None) -> bytes:
    """Return the report as PDF bytes (landscape A4)."""
    if not generated_at:
        now = datetime.now()
        generated_at = f"{now:%b %d, %Y} {civil_time(now)}"

    st = {"title": S_TITLE, "kicker": S_KICKER, "sub": S_SUB}
    widths_mm = {
        "stats": [68, 68, 68, 69],
        "break": [42, 26, 42, 26, 42, 26, 43, 26],
        "warranty": [24, 64, 34, 52, 41, 30, 28],
        "equipment": [19, 43, 25, 27, 38, 32, 30, 25, 18, 16],
    }
    W = {k: [v * mm for v in vals] for k, vals in widths_mm.items()}

    story = []

    # ---------------------------------------------------------- title band
    band = [
        Paragraph(escape("IT INVENTORY MANAGEMENT SYSTEM"), S_KICKER_C),
        Spacer(1, 3),
        Paragraph(escape("Inventory Report"), S_TITLE_C),
        Spacer(1, 6),
        Paragraph(escape("Date issued: %s" % generated_at), S_META_C),
        Paragraph(escape("Prepared by %s" % (generated_by or "-")), S_META_C),
    ]
    story.append(Table(
        [[band]],
        colWidths=[USABLE],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BLACK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ])))
    story.append(Spacer(1, 7 * mm))

    # ------------------------------------------------------------ headline
    warranty = stats.get("warranty") or {}
    expiring = (warranty.get("exp30") or 0) + (warranty.get("exp90") or 0)
    stat_cells = [
        (["TOTAL EQUIPMENT"], [str(stats.get("total", 0))],
         ["%s location(s) tracked" % stats.get("locations", 0)]),
        (["WARRANTY EXPIRED"], [str(warranty.get("expired", 0))],
         ["renewal candidates"]),
        (["EXPIRING WITHIN 90 DAYS"], [str(expiring)],
         ["%s within 30 days" % warranty.get("exp30", 0)]),
        (["ACTIVE LOANS / JOBS"],
         ["%s / %s" % (stats.get("active_loans", 0), stats.get("maint_open", 0))],
         ["%s overdue loans \u00b7 %s overdue jobs"
          % (stats.get("overdue_loans", 0), stats.get("maint_overdue", 0))]),
    ]
    stat_row = []
    for keys, values, notes in stat_cells:
        stat_row.append([
            Paragraph(escape(keys[0]), S_STAT_K),
            Spacer(1, 3),
            Paragraph(escape(values[0]), S_STAT_V),
            Spacer(1, 2),
            Paragraph(escape(notes[0]), S_STAT_N),
        ])
    story.append(Table(
        [stat_row],
        colWidths=[v * mm for v in widths_mm["stats"]],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
            ("BOX", (0, 0), (-1, -1), 0.5, G200),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, G200),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])))
    story.append(Spacer(1, 6 * mm))

    # ----------------------------------------------------------- breakdown
    story.append(Paragraph(escape("Inventory breakdown"), S_H2))
    blocks = [
        _pairs(stats.get("by_status")),
        _pairs(stats.get("by_category")),
        _pairs(stats.get("by_brand")),
        _pairs(locations),
    ]
    depth = max([len(b) for b in blocks] or [0])
    break_rows = []
    for i in range(depth):
        row = []
        for block in blocks:
            if i < len(block):
                row.extend([block[i][0], block[i][1]])
            else:
                row.extend(["", ""])
        break_rows.append(row)
    story.append(KeepTogether([
        Paragraph(escape("Inventory breakdown"), S_H2),
        _table(
            ["Status", "Qty", "Category", "Qty", "Brand", "Qty", "Location", "Qty"],
            break_rows, W["break"], right=(1, 3, 5, 7),
            empty="No inventory recorded yet."),
    ]))
    story.append(Spacer(1, 6 * mm))

    # ----------------------------------------------------------- warranty
    story.append(Paragraph(escape("Warranty expiry report (%d device%s)"
                                  % (len(warranty_rows),
                                     "" if len(warranty_rows) == 1 else "s")),
                           S_H2))
    warranty_rows_out = []
    for r in warranty_rows:
        state = warranty_state(r.get("warranty_expiry"))[0]
        warranty_rows_out.append([
            r.get("asset_tag"), r.get("model"), r.get("brand"),
            r.get("assigned_to"), fmt_date(r.get("warranty_expiry")),
            state, r.get("status"),
        ])
    story.append(KeepTogether([
        Paragraph(escape("Warranty expiry report (%d device%s)"
                          % (len(warranty_rows),
                             "" if len(warranty_rows) == 1 else "s")),
                  S_H2),
        _table(
            ["Asset Tag", "Model", "Brand", "Assigned", "Warranty Expiry",
             "State", "Status"],
            warranty_rows_out, W["warranty"],
            empty="No warranty dates recorded."),
    ]))
    story.append(Spacer(1, 6 * mm))

    # --------------------------------------------------------- equipment
    story.append(Paragraph(escape("Full equipment inventory (%d record%s)"
                                  % (len(equipment),
                                     "" if len(equipment) == 1 else "s")),
                           S_H2))
    equipment_out = []
    for r in equipment:
        equipment_out.append([
            r.get("asset_tag"), r.get("model"), r.get("brand"),
            r.get("category"), r.get("serial_no"), r.get("assigned_to"),
            r.get("location"), r.get("status"), r.get("condition"),
            fmt_date(r.get("purchase_date")),
        ])
    story.append(KeepTogether([
        Paragraph(escape("Full equipment inventory (%d record%s)"
                          % (len(equipment),
                             "" if len(equipment) == 1 else "s")),
                  S_H2),
        _table(
            ["Asset Tag", "Model", "Brand", "Category", "Serial No.", "Assigned",
             "Location", "Status", "Condition", "Available Date"],
            equipment_out, W["equipment"],
            empty="No equipment recorded yet."),
    ]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=BOTTOM,
        title="Inventory Report", author="IT Equipment Management System",
        subject="Inventory report")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
