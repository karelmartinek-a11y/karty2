"""Landscape, repeating table headers and readable complete evidence details."""

from pathlib import Path
from html import escape
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    LongTable,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def render_pdf(data, path, check):
    from kajovokarty.infrastructure.export import columns, values

    pdfmetrics.registerFont(
        TTFont("KK", str(Path(__file__).parents[1] / "assets/DejaVuSans.ttf"))
    )
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "KK"
    styles["Normal"].fontSize = 8
    styles["Normal"].leading = 11
    styles["Heading3"].fontSize = 9
    metadata = {r["key"]: r["value_json"] for r in data["metadata"]}
    title = "KájovoKarty · " + metadata["report_id"]

    def para(text):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles["Normal"])

    story = [Paragraph(escape(title), styles["Title"]), para(metadata["exported_at"])]
    for dataset, rows in data.items():
        check()
        story.append(Paragraph(dataset, styles["Heading2"]))
        cols = columns(dataset)
        if not rows:
            story.append(para("Žádné řádky."))
            continue
        # Up to six short scalar columns; remaining values are complete details below.
        candidates = [
            i
            for i, (k, t) in enumerate(cols)
            if not t.startswith("J") and not k.endswith("_minor")
        ]
        primary = candidates[:6]
        if not primary:
            primary = [0]
        width = (landscape(A4)[0] - 56) / len(primary)
        headers = [para(cols[i][0]) for i in primary]
        table = [headers]
        spans = []
        for number, row in enumerate(rows, 1):
            check()
            vs = values(dataset, row)
            compact = []
            details = []
            for i in primary:
                v = vs[i]
                if v is not None and len(str(v)) > 110:
                    compact.append(para("Podrobný obsah níže"))
                    details.append(i)
                else:
                    compact.append(para("" if v is None else v))
            table.append(compact)
            details += [
                i for i, v in enumerate(vs) if i not in primary and v is not None
            ]
            for i in details:
                raw = str(vs[i])
                # Split BEFORE HTML escaping, with each chunk short enough to fit a page.
                for offset in range(0, max(1, len(raw)), 1600):
                    detail = para(cols[i][0] + ": " + raw[offset : offset + 1600])
                    spans.append(("SPAN", (0, len(table)), (-1, len(table))))
                    table.append([detail] + [""] * (len(primary) - 1))
        t = LongTable(
            table, colWidths=[width] * len(primary), repeatRows=1, hAlign="LEFT"
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eff5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#5b7286")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.2, colors.HexColor("#dce3e9")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    *spans,
                ]
            )
        )
        story.extend([t, Spacer(1, 10)])

    def page(canvas, doc):
        check()
        canvas.setFont("KK", 8)
        canvas.drawString(28, 18, title)
        canvas.drawRightString(810, 18, str(doc.page))

    SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=32,
    ).build(story, onFirstPage=page, onLaterPages=page)
