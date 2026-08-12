"""Render README.md to the submission PDF using ReportLab."""

from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak,
                               Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                               TableStyle)

ROOT = Path(__file__).parents[1]


def _footer(canvas, document):
    canvas.saveState()
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, 10 * mm, "MTGNP Required Baseline")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def _inline(text: str) -> str:
    escaped = html.escape(text)
    while "`" in escaped:
        left, marker, rest = escaped.partition("`")
        code, marker2, tail = rest.partition("`")
        if not marker2: return escaped
        escaped = left + f'<font name="Courier">{code}</font>' + tail
    return escaped


def build(source: Path = ROOT / "README.md", target: Path = ROOT / "README.pdf") -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCustom", parent=styles["Title"],
                              fontName="Helvetica-Bold", fontSize=18, leading=22,
                              textColor=colors.black, alignment=TA_CENTER,
                              spaceAfter=12))
    styles.add(ParagraphStyle(name="H2Custom", parent=styles["Heading2"],
                              fontName="Helvetica-Bold", fontSize=13, leading=16,
                              textColor=colors.black, spaceBefore=12,
                              spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"],
                              fontName="Helvetica", fontSize=9.2, leading=13,
                              textColor=colors.black, spaceAfter=6))
    styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodyCustom"],
                              fontName="Helvetica-Bold", fontSize=8,
                              leading=10, textColor=colors.black))
    styles.add(ParagraphStyle(name="TableBody", parent=styles["BodyCustom"],
                              fontSize=8, leading=10, textColor=colors.black))
    code_style = ParagraphStyle(name="CodeCustom", fontName="Courier", fontSize=7.6,
                                leading=10, leftIndent=5, rightIndent=5,
                                textColor=colors.black)
    story = []
    lines = source.read_text(encoding="utf-8").splitlines()
    index = 0
    in_code = False
    code: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if in_code:
                box = Table([[Preformatted("\n".join(code), code_style)]], colWidths=[168 * mm])
                box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                          ("TOPPADDING", (0, 0), (-1, -1), 6),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
                story.extend([box, Spacer(1, 6)])
                code = []
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue
        if line.startswith("| "):
            table_lines = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index]); index += 1
            raw_rows = [row for row in table_lines
                        if not set(row.replace("|", "").replace("-", "").replace(":", "").strip()) == set()]
            rows = [[Paragraph(_inline(cell.strip()),
                               styles["TableHeader"] if row_index == 0 else styles["TableBody"])
                     for cell in row.strip("|").split("|")]
                    for row_index, row in enumerate(raw_rows)]
            if len(rows) > 1:
                column_count = len(rows[0])
                widths = {
                    2: [45 * mm, 123 * mm],
                    3: [30 * mm, 75 * mm, 63 * mm],
                    5: [76 * mm, 23 * mm, 23 * mm, 23 * mm, 23 * mm],
                }.get(column_count, [168 * mm / column_count] * column_count)
                table = Table(rows, repeatRows=1, colWidths=widths)
                table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
                                           ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                           ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                           ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
                story.extend([table, Spacer(1, 7)])
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline(line[2:]), styles["TitleCustom"]))
        elif line.startswith("## "):
            if line == "## Specification interpretations":
                story.append(PageBreak())
            story.append(Paragraph(_inline(line[3:]), styles["H2Custom"]))
        elif line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(ListItem(Paragraph(_inline(lines[index][2:]), styles["BodyCustom"]),
                                      leftIndent=10)); index += 1
            bullets = ListFlowable(items, bulletType="bullet", leftIndent=16,
                                   bulletFontSize=7, spaceAfter=5)
            story.append(KeepTogether([bullets]) if len(items) <= 4 else bullets)
            continue
        elif line.strip():
            story.append(Paragraph(_inline(line), styles["BodyCustom"]))
        index += 1
    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=18 * mm,
                            rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                            title="MTGNP Required Baseline", author="Course team")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


if __name__ == "__main__":
    build()
