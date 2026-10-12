"""
Creates templates/sonar_template.docx - the Sonar-branded Word template.

Run once:  python -m sonar_report.build_template
After that you can open the .docx in Word and restyle it freely (colours, fonts,
spacing, extra static text). Just keep the {{ ... }} and {% ... %} tags intact -
those are the slots the report generator fills in.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

HERE = Path(__file__).parent
LOGO = HERE / "assets" / "sonar-logo.png"
OUT = HERE.parent / "templates" / "sonar_template.docx"

RED = "C8161D"
SLATE = "4A4959"
ORANGE = "C98633"
INK = "1F1F29"
TEXT = "3D3D4A"
MUTED = "73737F"
LIGHT = "F5F5F7"
PINK = "FBEAEA"
FONT = "Arial"
CONTENT_W = Cm(17)


# ---------------------------------------------------------------- low-level helpers

def rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_)


def shade(cell, hex_: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_)
    tc_pr.append(shd)


def cell_margins(cell, top=120, bottom=120, left=160, right=160) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tc_pr.append(mar)


def table_borders(table, colour: str | None = "E4E4EA", inside: bool = True) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        if colour is None or (not inside and side.startswith("inside")):
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), colour)
        borders.append(el)
    tbl_pr.append(borders)


def col_widths(table, widths) -> None:
    """Set column widths in both places Word and LibreOffice read them from."""
    table.autofit = False
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(int(Emu(w).twips)))
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = w
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def keep_rows_together(table) -> None:
    """Never split a row across pages, and keep each row with the next one (chart cards stay whole)."""
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        tr_pr.append(cant)
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.keep_with_next = True


def para_border_bottom(p, colour=ORANGE, size=12) -> None:
    p_pr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), colour)
    bdr.append(bottom)
    p_pr.append(bdr)


def keep_with_next(p) -> None:
    p.paragraph_format.keep_with_next = True


def write(container, text: str = "", size: float = 10, bold: bool = False, colour: str = TEXT,
          align=None, before: float = 0, after: float = 6, italic: bool = False, first=False):
    """Add a paragraph with ONE run, so {{ tags }} are never split by Word."""
    p = container.paragraphs[0] if first and container.paragraphs else container.add_paragraph()
    if text:
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.name = FONT
        run.font.color.rgb = rgb(colour)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.2
    if align is not None:
        p.alignment = align
    return p


def tag(container, text: str):
    """A paragraph holding only a {%p ... %} / {%tr ... %} control tag."""
    return write(container, text, size=2, after=0)


def heading(doc, text: str, page_break: bool = False):
    p = write(doc, text.upper(), size=15, bold=True, colour=RED, before=6, after=10)
    p.paragraph_format.page_break_before = page_break
    para_border_bottom(p)
    keep_with_next(p)
    return p


def subheading(doc, text: str, colour: str = INK):
    p = write(doc, text, size=11.5, bold=True, colour=colour, before=10, after=4)
    keep_with_next(p)
    return p


def add_field(paragraph, instr: str, size=8, colour=MUTED) -> None:
    """Insert a Word field such as PAGE or NUMPAGES."""
    run = paragraph.add_run()
    run.font.size = Pt(size)
    run.font.name = FONT
    run.font.color.rgb = rgb(colour)
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "1"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        elif text == instr:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = f" {instr} "
        else:
            el = OxmlElement("w:t")
            el.text = text
        run._r.append(el)


def label_value_table(doc, rows, label_w=Cm(4.5)):
    t = doc.add_table(rows=len(rows), cols=2)
    table_borders(t, "E4E4EA")
    col_widths(t, [label_w, CONTENT_W - label_w])
    for row, (label, value) in zip(t.rows, rows):
        shade(row.cells[0], LIGHT)
        for c in row.cells:
            cell_margins(c, 90, 90)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        write(row.cells[0], label, size=9, bold=True, colour=INK, after=0, first=True)
        write(row.cells[1], value, size=9.5, colour=TEXT, after=0, first=True)
    return t


# ---------------------------------------------------------------- the template

def build() -> Path:
    doc = Document()

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10)
    normal.font.color.rgb = rgb(TEXT)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(1.8)
    sec.different_first_page_header_footer = True

    # header (pages 2+): logo left, report name right
    ht = sec.header.add_table(rows=1, cols=2, width=CONTENT_W)
    table_borders(ht, None)
    col_widths(ht, [Cm(8.5), Cm(8.5)])
    if LOGO.exists():
        ht.cell(0, 0).paragraphs[0].add_run().add_picture(str(LOGO), height=Cm(1.1))
    write(ht.cell(0, 1), "PERFORMANCE TEST REPORT", size=8, bold=True, colour=RED,
          align=WD_ALIGN_PARAGRAPH.RIGHT, after=0, first=True)
    write(ht.cell(0, 1), "{{ project_name }}", size=8, colour=MUTED, align=WD_ALIGN_PARAGRAPH.RIGHT, after=0)
    hp = sec.header.paragraphs[0]
    para_border_bottom(hp, RED, 8)

    # footer: confidential left, page x of y right
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = fp.add_run("{{ client_name }} · Confidential        Page ")
    r.font.size, r.font.name, r.font.color.rgb = Pt(8), FONT, rgb(MUTED)
    add_field(fp, "PAGE")
    r = fp.add_run(" of ")
    r.font.size, r.font.name, r.font.color.rgb = Pt(8), FONT, rgb(MUTED)
    add_field(fp, "NUMPAGES")

    # ======================= COVER =======================
    if LOGO.exists():
        p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
        p.add_run().add_picture(str(LOGO), width=Cm(6.5))
        p.paragraph_format.space_after = Pt(70)
    else:
        write(doc, "SONAR", size=36, bold=True, colour=INK, after=70)

    cover = doc.add_table(rows=2, cols=1)
    table_borders(cover, None)
    col_widths(cover, [CONTENT_W])
    c = cover.cell(0, 0)
    shade(c, RED)
    cell_margins(c, 500, 500, 500, 500)
    write(c, "PERFORMANCE TEST REPORT", size=11, bold=True, colour="FFFFFF", after=10, first=True)
    write(c, "{{ test_type_name }}", size=30, bold=True, colour="FFFFFF", after=4)
    write(c, "{{ project_name }}", size=15, colour="FFFFFF", after=0)
    c = cover.cell(1, 0)
    shade(c, SLATE)
    cell_margins(c, 320, 320, 500, 500)
    for i, (lab, val) in enumerate([("Client", "{{ client_name }}"), ("Environment", "{{ environment }}"),
                                    ("Test period", "{{ period }}"), ("Tool", "{{ tool_name }}")]):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        r1 = p.add_run(f"{lab}:  ")
        r1.font.size, r1.font.bold, r1.font.name, r1.font.color.rgb = Pt(10.5), True, FONT, rgb(ORANGE)
        r2 = p.add_run(val)
        r2.font.size, r2.font.name, r2.font.color.rgb = Pt(10.5), FONT, rgb("FFFFFF")
        p.paragraph_format.space_after = Pt(3)

    write(doc, "", after=150)
    write(doc, "Prepared by {{ tester_name }}  ·  {{ report_date }}  ·  Version 1.0", size=9, colour=MUTED, after=2)
    write(doc, "This document is confidential and intended only for {{ client_name }}.", size=8, colour=MUTED, italic=True)

    # ======================= EXECUTIVE SUMMARY =======================
    heading(doc, "Executive Summary", page_break=True)
    label_value_table(doc, [
        ("System under test", "{{ project_name }}"),
        ("Objective", "{{ objective }}"),
        ("Test type", "{{ test_type_name }} - {{ test_type_purpose }}"),
        ("Scope", "{{ scope }}"),
    ])
    write(doc, "", after=4)
    tag(doc, "{%p for para in summary %}")
    write(doc, "{{ para }}", size=10, after=8)
    tag(doc, "{%p endfor %}")

    subheading(doc, "FINDINGS", RED)
    tiles = doc.add_table(rows=2, cols=4)
    table_borders(tiles, "FFFFFF")
    col_widths(tiles, [CONTENT_W / 4] * 4)
    for i, (name, colour) in enumerate([("HIGH", RED), ("MEDIUM", "E07A1F"), ("LOW", ORANGE), ("INFO", SLATE)]):
        top, bottom = tiles.cell(0, i), tiles.cell(1, i)
        shade(top, colour)
        shade(bottom, colour)
        cell_margins(top, 100, 0)
        cell_margins(bottom, 0, 140)
        write(top, name, size=9, bold=True, colour="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)
        write(bottom, "{{ counts.%s }}" % name, size=30, bold=True, colour="FFFFFF",
              align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)

    write(doc, "", after=4)
    verdict = doc.add_table(rows=1, cols=1)
    table_borders(verdict, None)
    vc = verdict.cell(0, 0)
    cell_margins(vc, 160, 160, 200, 200)
    p = write(vc, "{% cellbg verdict_colour %}OVERALL RESULT:  {{ verdict }}", size=12, bold=True, colour="FFFFFF",
              align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)

    # ======================= KEY RESULTS =======================
    heading(doc, "Key Results", page_break=True)
    write(doc, "The headline numbers from the test. Status is shown where a target was set.", size=9.5, colour=MUTED)
    kr = doc.add_table(rows=3, cols=3)
    table_borders(kr, "E4E4EA")
    col_widths(kr, [Cm(7.5), Cm(6), Cm(3.5)])
    for i, h in enumerate(["METRIC", "RESULT", "STATUS"]):
        shade(kr.cell(0, i), SLATE)
        cell_margins(kr.cell(0, i), 90, 90)
        write(kr.cell(0, i), h, size=8.5, bold=True, colour="FFFFFF", after=0, first=True)
    write(kr.cell(1, 0), "{%tr for r in key_results %}", size=2, after=0, first=True)
    for i, txt in enumerate(["{{ r.name }}", "{{ r.value }}", "{{r r.status_rt }}"]):
        cell_margins(kr.cell(2, i), 80, 80)
        write(kr.cell(2, i), txt, size=9.5, colour=INK, after=0, first=True)
    kr.add_row()
    write(kr.cell(3, 0), "{%tr endfor %}", size=2, after=0, first=True)

    subheading(doc, "TOP IDENTIFIED ISSUES", RED)
    tag(doc, "{%p if not top_findings %}")
    write(doc, "No performance issues were identified during this test.", size=10)
    tag(doc, "{%p endif %}")
    tag(doc, "{%p for f in top_findings %}")
    write(doc, "{{ f.id }} - {{ f.title }}  ({{ f.severity }})", size=10.5, bold=True, colour=INK, before=4, after=2)
    write(doc, "{{ f.description }}", size=10, after=8)
    tag(doc, "{%p endfor %}")

    # ======================= RECOMMENDATIONS + WHAT WENT WELL =======================
    heading(doc, "Key Recommendations", page_break=True)
    rec = doc.add_table(rows=3, cols=1)
    table_borders(rec, "FFFFFF")
    col_widths(rec, [CONTENT_W])
    write(rec.cell(0, 0), "{%tr for f in top_findings %}", size=2, after=0, first=True)
    rc = rec.cell(1, 0)
    shade(rc, PINK)
    cell_margins(rc, 160, 160, 220, 220)
    write(rc, "Recommendation - {{ f.title }}", size=10.5, bold=True, colour=RED, after=4, first=True)
    write(rc, "{{ f.recommendation }}", size=10, colour=INK, after=0)
    write(rec.cell(2, 0), "{%tr endfor %}", size=2, after=0, first=True)
    tag(doc, "{%p if not top_findings %}")
    write(doc, "No changes are required based on this test. Continue to re-test after major releases.", size=10)
    tag(doc, "{%p endif %}")

    subheading(doc, "WHAT PERFORMED WELL", RED)
    write(doc, "Behaviour observed during the test that met or exceeded expectations.", size=9.5, colour=MUTED)
    good = doc.add_table(rows=3, cols=1)
    table_borders(good, "FFFFFF")
    col_widths(good, [CONTENT_W])
    write(good.cell(0, 0), "{%tr for g in positives %}", size=2, after=0, first=True)
    gc = good.cell(1, 0)
    shade(gc, LIGHT)
    cell_margins(gc, 120, 120, 220, 220)
    write(gc, "{{ g.title }}", size=10, bold=True, colour=INK, after=2, first=True)
    write(gc, "{{ g.text }}", size=9.5, after=0)
    write(good.cell(2, 0), "{%tr endfor %}", size=2, after=0, first=True)

    # ======================= SCOPE & METHODOLOGY =======================
    heading(doc, "Test Scope & Methodology", page_break=True)
    label_value_table(doc, [
        ("System under test", "{{ project_name }}"),
        ("Environment", "{{ environment }}"),
        ("Test type", "{{ test_type_name }}"),
        ("Tool", "{{ tool_name }}"),
        ("Test period", "{{ period }}"),
        ("Load profile", "{{ load_profile }}"),
        ("Test cases / endpoints", "{{ label_count }}"),
        ("Targets", "{{ targets }}"),
        ("Source data", "{{ source_file }}"),
    ])
    subheading(doc, "TESTING PERFORMED", RED)
    write(doc, "{{ method_text }}", size=10)
    tag(doc, "{%p if expected_load %}")
    write(doc, "Expected load: {{ expected_load }}", size=10)
    tag(doc, "{%p endif %}")
    tag(doc, "{%p if notes %}")
    subheading(doc, "TESTER NOTES", RED)
    write(doc, "{{ notes }}", size=10)
    tag(doc, "{%p endif %}")

    # ======================= RESULTS (chart grids) =======================
    heading(doc, "Detailed Results", page_break=True)
    write(doc, "Each chart is shown with a short explanation of what it measures and what this test's numbers mean.",
          size=9.5, colour=MUTED)

    wide = doc.add_table(rows=5, cols=1)
    table_borders(wide, None)
    col_widths(wide, [CONTENT_W])
    write(wide.cell(0, 0), "{%tr for c in wide_charts %}", size=2, after=0, first=True)
    t = wide.cell(1, 0)
    shade(t, SLATE)
    cell_margins(t, 70, 70, 160, 160)
    write(t, "{{ c.title }}", size=10, bold=True, colour="FFFFFF", after=0, first=True)
    im = wide.cell(2, 0)
    cell_margins(im, 80, 40, 0, 0)
    write(im, "{{ c.image }}", align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)
    ex = wide.cell(3, 0)
    shade(ex, LIGHT)
    cell_margins(ex, 110, 110, 180, 180)
    write(ex, "{{ c.text }}", size=9.5, colour=INK, after=0, first=True)
    write(wide.cell(4, 0), "{%tr endfor %}", size=2, after=0, first=True)
    keep_rows_together(wide)
    for p in wide.cell(3, 0).paragraphs:  # let the page break after the explanation box
        p.paragraph_format.keep_with_next = False

    write(doc, "", after=6)
    half = doc.add_table(rows=5, cols=2)
    table_borders(half, None)
    col_widths(half, [CONTENT_W / 2, CONTENT_W / 2])
    write(half.cell(0, 0), "{%tr for row in half_rows %}", size=2, after=0, first=True)
    for i, side in enumerate(["row.left", "row.right"]):
        t = half.cell(1, i)
        cell_margins(t, 70, 70, 140, 140)
        write(t, "{%% cellbg %s.bar %%}{{ %s.title }}" % (side, side), size=9.5, bold=True, colour="FFFFFF",
              after=0, first=True)
        im = half.cell(2, i)
        cell_margins(im, 80, 40, 40, 40)
        write(im, "{{ %s.image }}" % side, align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)
        ex = half.cell(3, i)
        cell_margins(ex, 100, 160, 140, 140)
        write(ex, "{%% cellbg %s.box %%}{{ %s.text }}" % (side, side), size=9, colour=INK, after=0, first=True)
    write(half.cell(4, 0), "{%tr endfor %}", size=2, after=0, first=True)
    keep_rows_together(half)
    for i in range(2):
        for p in half.cell(3, i).paragraphs:
            p.paragraph_format.keep_with_next = False

    # ======================= FINDINGS =======================
    heading(doc, "Findings", page_break=True)
    write(doc, "All findings from this test, ordered by severity.", size=9.5, colour=MUTED)
    ft = doc.add_table(rows=3, cols=3)
    table_borders(ft, "E4E4EA")
    col_widths(ft, [Cm(2.8), Cm(10.7), Cm(3.5)])
    for i, h in enumerate(["ID", "FINDING", "RATING"]):
        shade(ft.cell(0, i), SLATE)
        cell_margins(ft.cell(0, i), 90, 90)
        write(ft.cell(0, i), h, size=8.5, bold=True, colour="FFFFFF", after=0, first=True)
    write(ft.cell(1, 0), "{%tr for f in findings %}", size=2, after=0, first=True)
    for i, txt in enumerate(["{{ f.id }}", "{{ f.title }}", "{% cellbg f.colour %}{{ f.severity }}"]):
        cell_margins(ft.cell(2, i), 80, 80)
        write(ft.cell(2, i), txt, size=9.5, bold=(i == 2), colour="FFFFFF" if i == 2 else INK,
              align=WD_ALIGN_PARAGRAPH.CENTER if i == 2 else None, after=0, first=True)
    ft.add_row()
    write(ft.cell(3, 0), "{%tr endfor %}", size=2, after=0, first=True)
    tag(doc, "{%p if not findings %}")
    write(doc, "No findings - the API met expectations for this test.", size=10)
    tag(doc, "{%p endif %}")

    subheading(doc, "TEST NARRATIVE", RED)
    tag(doc, "{%p for para in narrative %}")
    write(doc, "{{ para }}", size=10, after=8)
    tag(doc, "{%p endfor %}")

    # one detail block per finding (like LMNTRIX VULN-01 pages)
    tag(doc, "{%p for f in findings %}")
    p = write(doc, "{{ f.id }} - {{ f.title }}", size=14, bold=True, colour=RED, before=0, after=8)
    p.paragraph_format.page_break_before = True
    keep_with_next(p)
    rt = doc.add_table(rows=1, cols=2)
    table_borders(rt, "E4E4EA")
    col_widths(rt, [Cm(12.5), Cm(4.5)])
    left, right = rt.cell(0, 0), rt.cell(0, 1)
    shade(left, LIGHT)
    cell_margins(left, 120, 120, 180, 180)
    write(left, "RISK RATING:  {{ f.severity }}", size=10, bold=True, colour=INK, after=3, first=True)
    write(left, "AREA:  {{ f.area }}", size=9.5, colour=TEXT, after=0)
    right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    write(right, "{% cellbg f.colour %}{{ f.severity }}", size=16, bold=True, colour="FFFFFF",
          align=WD_ALIGN_PARAGRAPH.CENTER, after=0, first=True)
    subheading(doc, "DESCRIPTION", RED)
    write(doc, "{{ f.description }}", size=10)
    subheading(doc, "BUSINESS IMPACT", RED)
    write(doc, "{{ f.impact }}", size=10)
    subheading(doc, "RECOMMENDATION", RED)
    write(doc, "{{ f.recommendation }}", size=10)
    tag(doc, "{%p if f.evidence %}")
    subheading(doc, "EVIDENCE", RED)
    write(doc, "{{ f.evidence }}", align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
    write(doc, "{{ f.evidence_caption }}", size=8.5, colour=MUTED, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    tag(doc, "{%p endif %}")
    tag(doc, "{%p endfor %}")

    # ======================= SEVERITY SCALE =======================
    heading(doc, "Severity Description", page_break=True)
    write(doc, "How each finding is rated. The overall result is set by the highest-rated finding.", size=9.5, colour=MUTED)
    sev = doc.add_table(rows=2, cols=2)
    table_borders(sev, "FFFFFF")
    col_widths(sev, [CONTENT_W / 2, CONTENT_W / 2])
    defs = [
        ("HIGH", RED, "A target was clearly missed or the API failed in a way users would notice. Fix before release."),
        ("MEDIUM", "E07A1F", "Behaviour that will cause problems under real traffic or over time. Plan a fix soon."),
        ("LOW", ORANGE, "A minor issue or an early warning sign. Fix when convenient and keep monitoring."),
        ("INFO", SLATE, "Not a defect - a note about how the test was run or how to make future tests more useful."),
    ]
    for i, (name, colour, text) in enumerate(defs):
        cell = sev.cell(i // 2, i % 2)
        shade(cell, colour)
        cell_margins(cell, 200, 200, 220, 220)
        write(cell, f"{name} RISK" if name != "INFO" else "INFORMATIONAL", size=11, bold=True, colour="FFFFFF",
              align=WD_ALIGN_PARAGRAPH.CENTER, after=6, first=True)
        write(cell, text, size=9.5, colour="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER, after=0)

    # ======================= APPENDIX =======================
    heading(doc, "Appendix A - Results per Test Case", page_break=True)
    ap = doc.add_table(rows=3, cols=6)
    table_borders(ap, "E4E4EA")
    col_widths(ap, [Cm(6.2), Cm(2), Cm(2), Cm(2.3), Cm(2.3), Cm(2.2)])
    for i, h in enumerate(["TEST CASE / ENDPOINT", "REQUESTS", "FAILED", "MEDIAN", "95TH PCT", "SLOWEST"]):
        shade(ap.cell(0, i), SLATE)
        cell_margins(ap.cell(0, i), 80, 80, 100, 100)
        write(ap.cell(0, i), h, size=7.5, bold=True, colour="FFFFFF", after=0, first=True)
    write(ap.cell(1, 0), "{%tr for l in labels %}", size=2, after=0, first=True)
    for i, key in enumerate(["name", "requests", "failed", "median", "p95", "max"]):
        cell_margins(ap.cell(2, i), 60, 60, 100, 100)
        write(ap.cell(2, i), "{{ l.%s }}" % key, size=8.5, colour=INK, after=0, first=True,
              align=WD_ALIGN_PARAGRAPH.RIGHT if i else None)
    ap.add_row()
    write(ap.cell(3, 0), "{%tr endfor %}", size=2, after=0, first=True)

    heading(doc, "Appendix B - Terms Used")
    label_value_table(doc, [
        ("Median", "The typical response time: half of requests were faster, half slower."),
        ("95th percentile (p95)", "95% of requests were faster than this. The most common performance target."),
        ("99th percentile (p99)", "99% of requests were faster than this. Shows the slowest experiences."),
        ("Throughput", "How many requests the API handled per second."),
        ("Virtual user (VU)", "A simulated client sending requests during the test."),
        ("Error rate", "The share of requests that failed (timeouts, 4xx/5xx responses or failed checks)."),
        ("Load / Stress / Soak / Spike", "Normal expected traffic / beyond normal to find limits / steady load for hours / sudden bursts."),
    ], label_w=Cm(5))

    heading(doc, "Document Information")
    label_value_table(doc, [
        ("Prepared by", "{{ tester_name }}"),
        ("Report date", "{{ report_date }}"),
        ("Generated by", "Sonar Performance Report Tool"),
        ("Source data", "{{ source_file }}"),
    ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print("Template written to", build())