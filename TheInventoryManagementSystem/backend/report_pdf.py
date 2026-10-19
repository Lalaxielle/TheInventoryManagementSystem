"""Server-side PDF for the Reports page ("Save as PDF").

Lays the report out as a real PDF with reportlab, so the report preview bar can
offer an actual file the user can save and then print - the browser print dialog
alone never produced a file. The sheet is landscape A4 unless asked otherwise:
"Save as PDF" offers the paper sizes in PAPER_SIZES *and* the two orientations
(Portrait / Landscape, see ORIENTATIONS) *before* it opens the save destination
dialog, and the whole layout is scaled to the chosen sheet so the tables still
sit exactly between the margins and no column is ever dropped.

Black / white / grey only: the palette defined in static/css/style.css.
"""

import io
from xml.sax.saxutils import escape

from backend.models import civil_time, fmt_date, now_ph, warranty_state
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import (A3, A4, A5, LEGAL, LETTER, TABLOID,
                                     landscape)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle, KeepTogether)

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

# ------------------------------------------------------------- paper sizes
# The report is designed on a landscape A4 sheet: the three tables' column
# widths add up to exactly this usable width (273 mm). Every other sheet -
# another paper size, or the same paper turned portrait - is handled by scaling
# the *whole* layout by usable_width / DESIGN_USABLE, so the tables still sit
# exactly between the margins, no column is ever dropped, and type shrinks or
# grows with the sheet. "Save as PDF" asks which paper and which way round to
# lay the file out for. Keep the keys in step with PAPERS in static/js/app.js
# (that list is what the user sees).
DESIGN = landscape(A4)
MARGIN = 12 * mm
BOTTOM = 18 * mm
DESIGN_USABLE = DESIGN[0] - 2 * MARGIN      # ~273 mm of live width
# Each entry is the *portrait* page; build_report_pdf() turns it to the chosen
# orientation. (The reportlab constants are portrait - A4 is 210 x 297 mm.)
PAPER_SIZES = {
    "a4": ("A4 (210 x 297 mm)", A4),
    "letter": ("Letter (8.5 x 11 in)", LETTER),
    "legal": ("Legal (8.5 x 14 in)", LEGAL),
    "a3": ("A3 (297 x 420 mm)", A3),
    "tabloid": ("Tabloid (11 x 17 in)", TABLOID),
    "a5": ("A5 (148 x 210 mm)", A5),
}
DEFAULT_PAPER = "a4"
# The two ways round the sheet can go (the user: "add options of Portrait and
# Landscape", 2026-10-19). Landscape stays the default: it is the sheet the
# report is designed on and what every previous download produced.
ORIENTATIONS = ("portrait", "landscape")
DEFAULT_ORIENTATION = "landscape"

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
# Section headings ("INVENTORY BREAKDOWN", "WARRANTY EXPIRY REPORT (N DEVICES)",
# "FULL EQUIPMENT INVENTORY (N RECORDS)") are centred and upper-case, matching
# the Reports page, where .panel-head h2 is `text-transform: uppercase` - the
# user asked for the header text to be centre aligned and capitalised,
# 2026-10-19.
S_H2 = ParagraphStyle(
    "h2", fontName="Helvetica-Bold", fontSize=10, leading=12,
    textColor=BLACK, spaceBefore=2, spaceAfter=4, alignment=TA_CENTER)
# Every cell of the report's tables - header row included - is centre aligned
# (user, 2026-10-19: "can you make each table a center align"). The count
# columns used to be right aligned; they are centred too, and stay bold.
S_TH = ParagraphStyle(
    "th", fontName="Helvetica-Bold", fontSize=7.2, leading=8.6,
    textColor=WHITE, alignment=TA_CENTER)
S_TD = ParagraphStyle(
    "td", fontName="Helvetica", fontSize=7.2, leading=8.6,
    textColor=G900, alignment=TA_CENTER)
S_TD_B = ParagraphStyle(
    "tdb", fontName="Helvetica-Bold", fontSize=7.2, leading=8.6,
    textColor=BLACK, alignment=TA_CENTER)
S_QTY = ParagraphStyle(
    "qty", parent=S_TD_B, alignment=TA_CENTER)
S_STAT_K = ParagraphStyle(
    "statk", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=G500)
S_STAT_V = ParagraphStyle(
    "statv", fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=BLACK)
S_STAT_N = ParagraphStyle(
    "statn", fontName="Helvetica", fontSize=6.8, leading=8.5, textColor=G500)
S_NOTE = ParagraphStyle(
    "note", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=G500)


def _scaled(style, scale):
    """A copy of *style* with every length multiplied by *scale*.

    Paper other than the landscape-A4 design is handled by scaling the layout,
    so type, leading and the space around it move with the sheet instead of the
    ten-column tables running past the margins. Legacy `spaceBefore`/`spaceAfter`
    are scaled too (they are the heading's breathing room).
    """
    if scale == 1:
        return style
    return ParagraphStyle(
        "%s@%.3f" % (style.name, scale), parent=style,
        fontSize=(style.fontSize or 0) * scale,
        leading=(style.leading or 0) * scale,
        spaceBefore=(style.spaceBefore or 0) * scale,
        spaceAfter=(style.spaceAfter or 0) * scale)


def _styles(scale=1.0):
    """The report's paragraph styles, sized for the chosen paper."""
    return {
        "title": _scaled(S_TITLE, scale),
        "kicker": _scaled(S_KICKER, scale),
        "sub": _scaled(S_SUB, scale),
        "title_c": _scaled(S_TITLE_C, scale),
        "kicker_c": _scaled(S_KICKER_C, scale),
        "meta_c": _scaled(S_META_C, scale),
        "h2": _scaled(S_H2, scale),
        "th": _scaled(S_TH, scale),
        "td": _scaled(S_TD, scale),
        "td_b": _scaled(S_TD_B, scale),
        "qty": _scaled(S_QTY, scale),
        "stat_k": _scaled(S_STAT_K, scale),
        "stat_v": _scaled(S_STAT_V, scale),
        "stat_n": _scaled(S_STAT_N, scale),
        "note": _scaled(S_NOTE, scale),
    }


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


def _table(headers, rows, widths, *, bold=(), empty="No records.",
           styles=None, scale=1.0):
    """Build a striped, black-headed table.

    Every cell is centre aligned (see the S_TH/S_TD note above). *bold* lists
    column indexes whose cells are drawn bold (the counts). *styles* is a
    `_styles()` set and *scale* the paper's layout scale, so cell type and
    padding shrink with the sheet.
    """
    st = styles or _styles(1.0)
    data = [[_p(h, st["th"]) for h in headers]]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append(_p(cell, st["qty"] if i in bold else st["td"]))
        data.append(cells)

    hpad = 4 * scale
    vpad = 3.5 * scale
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, G200),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, G50]),
        ("LEFTPADDING", (0, 0), (-1, -1), hpad),
        ("RIGHTPADDING", (0, 0), (-1, -1), hpad),
        ("TOPPADDING", (0, 0), (-1, -1), vpad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), vpad),
    ]
    if not rows:
        data.append([_p(empty, st["td"])] + [""] * (len(headers) - 1))
        style.append(("SPAN", (0, 1), (-1, 1)))

    return Table(data, colWidths=widths, repeatRows=1,
                 style=TableStyle(style))


def _footer(canvas, doc):
    """Thin rule plus copyright / page number at the foot of every page."""
    # doc.pagesize, not a module constant: the paper is chosen per request.
    width = doc.pagesize[0]
    canvas.saveState()
    canvas.setStrokeColor(G200)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 13 * mm, width - MARGIN, 13 * mm)
    canvas.setFillColor(G500)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 9 * mm,
                      "\u00a9 2026 The ITEQ Company. All rights reserved.")
    canvas.drawRightString(width - MARGIN, 9 * mm,
                           "Page %d" % canvas.getPageNumber())
    canvas.restoreState()


def _pairs(mapping):
    """(label, count) rows from a dict or from location_summary()."""
    if isinstance(mapping, dict):
        return list(mapping.items())
    return [(g.get("location"), g.get("total")) for g in (mapping or [])]


def build_report_pdf(stats, equipment, warranty_rows, locations,
                     generated_by="", generated_at=None,
                     paper=DEFAULT_PAPER,
                     orientation=DEFAULT_ORIENTATION) -> bytes:
    """Return the report as PDF bytes, laid out for *paper* (see PAPER_SIZES),
    turned *orientation* (see ORIENTATIONS: "portrait" or "landscape")."""
    if not generated_at:
        now = now_ph()
        generated_at = f"{now:%b %d, %Y} {civil_time(now)}"

    # Paper handling: the design is a landscape A4 sheet, so every length below
    # is multiplied by this one factor. At scale 1 each table's column widths
    # add up to exactly DESIGN_USABLE (273 mm); because the factor is
    # usable_width / DESIGN_USABLE they still add up to exactly the usable width
    # of whatever sheet was picked, so nothing is clipped and no column is lost.
    label, base = PAPER_SIZES.get(str(paper or "").lower(),
                                  PAPER_SIZES[DEFAULT_PAPER])
    orient = str(orientation or "").lower()
    if orient not in ORIENTATIONS:
        orient = DEFAULT_ORIENTATION
    page = base if orient == "portrait" else landscape(base)
    usable = page[0] - 2 * MARGIN
    scale = usable / DESIGN_USABLE

    st = _styles(scale)
    widths_mm = {
        "stats": [68, 68, 68, 69],
        "break": [42, 26, 42, 26, 42, 26, 43, 26],
        "warranty": [24, 64, 34, 52, 41, 30, 28],
        "equipment": [19, 43, 25, 27, 38, 32, 30, 25, 18, 16],
    }
    W = {k: [v * mm * scale for v in vals] for k, vals in widths_mm.items()}

    story = []

    # ---------------------------------------------------------- title band
    band = [
        Paragraph(escape("IT INVENTORY MANAGEMENT SYSTEM"), st["kicker_c"]),
        Spacer(1, 3 * scale),
        Paragraph(escape("Inventory Report"), st["title_c"]),
        Spacer(1, 6 * scale),
        Paragraph(escape("Date issued: %s" % generated_at), st["meta_c"]),
        Paragraph(escape("Prepared by %s" % (generated_by or "-")), st["meta_c"]),
    ]
    story.append(Table(
        [[band]],
        colWidths=[usable],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BLACK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14 * scale),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14 * scale),
            ("TOPPADDING", (0, 0), (-1, -1), 12 * scale),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12 * scale),
        ])))
    story.append(Spacer(1, 7 * mm * scale))

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
            Paragraph(escape(keys[0]), st["stat_k"]),
            Spacer(1, 3 * scale),
            Paragraph(escape(values[0]), st["stat_v"]),
            Spacer(1, 2 * scale),
            Paragraph(escape(notes[0]), st["stat_n"]),
        ])
    story.append(Table(
        [stat_row],
        colWidths=W["stats"],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
            ("BOX", (0, 0), (-1, -1), 0.5, G200),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, G200),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9 * scale),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9 * scale),
            ("TOPPADDING", (0, 0), (-1, -1), 8 * scale),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * scale),
        ])))
    story.append(Spacer(1, 6 * mm * scale))

    # ----------------------------------------------------------- breakdown
    # (The heading is emitted only inside the KeepTogether below: a standalone
    # copy up here printed the section title twice in the PDF - the user's
    # "duplicate text in landscape" report, 2026-10-19.)
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
        Paragraph(escape("INVENTORY BREAKDOWN"), st["h2"]),
        _table(
            ["Status", "Qty", "Category", "Qty", "Brand", "Qty", "Location", "Qty"],
            break_rows, W["break"], bold=(1, 3, 5, 7),
            empty="No inventory recorded yet.", styles=st, scale=scale),
    ]))
    story.append(Spacer(1, 6 * mm * scale))

    # ----------------------------------------------------------- warranty
    # (Heading only in the KeepTogether below - see the breakdown note.)
    warranty_rows_out = []
    for r in warranty_rows:
        state = warranty_state(r.get("warranty_expiry"))[0]
        warranty_rows_out.append([
            r.get("asset_tag"), r.get("model"), r.get("brand"),
            r.get("assigned_to"), fmt_date(r.get("warranty_expiry")),
            state, r.get("status"),
        ])
    story.append(KeepTogether([
        Paragraph(escape("WARRANTY EXPIRY REPORT (%d DEVICE%s)"
                          % (len(warranty_rows),
                             "" if len(warranty_rows) == 1 else "S")),
                  st["h2"]),
        _table(
            ["Asset Tag", "Model", "Brand", "Assigned", "Warranty Expiry",
             "State", "Status"],
            warranty_rows_out, W["warranty"],
            empty="No warranty dates recorded.",
            styles=st, scale=scale),
    ]))
    story.append(Spacer(1, 6 * mm * scale))

    # --------------------------------------------------------- equipment
    # (Heading only in the KeepTogether below - see the breakdown note.)
    equipment_out = []
    for r in equipment:
        equipment_out.append([
            r.get("asset_tag"), r.get("model"), r.get("brand"),
            r.get("category"), r.get("serial_no"), r.get("assigned_to"),
            r.get("location"), r.get("status"), r.get("condition"),
            fmt_date(r.get("purchase_date")),
        ])
    story.append(KeepTogether([
        Paragraph(escape("FULL EQUIPMENT INVENTORY (%d RECORD%s)"
                          % (len(equipment),
                             "" if len(equipment) == 1 else "S")),
                  st["h2"]),
        _table(
            ["Asset Tag", "Model", "Brand", "Category", "Serial No.", "Assigned",
             "Location", "Status", "Condition", "Available Date"],
            equipment_out, W["equipment"],
            empty="No equipment recorded yet.",
            styles=st, scale=scale),
    ]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=page,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=BOTTOM,
        title="Inventory Report", author="IT Equipment Management System",
        subject="Inventory report - %s, %s" % (label, orient))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
