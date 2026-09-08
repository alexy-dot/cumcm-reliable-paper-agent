"""Render a structured paper to matching Markdown and A4 PDF. Optional dependencies."""
import argparse
import html
import json
from pathlib import Path


def render(run: Path, source: Path, font: Path | None = None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    from pypdf import PdfReader
    run = run.resolve()
    if (run / "state.json").is_file() and json.loads((run / "state.json").read_text())["stage"] == "VERIFIED":
        raise ValueError("create a new version before rendering a sealed run")
    data = json.loads(source.read_text(encoding="utf-8"))
    candidates = [font] if font else [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    ]
    font_path = next((path for path in candidates if path and path.is_file()), None)
    if font_path is None:
        raise ValueError("provide an embeddable CJK TrueType font using --font")
    paper_font = TTFont("PaperFont", str(font_path))
    pdfmetrics.registerFont(paper_font)
    content = json.dumps(data, ensure_ascii=False)
    missing = sorted({character for character in content if ord(character) > 127 and ord(character) not in paper_font.face.charToGlyph})
    if missing:
        raise ValueError("selected font lacks glyphs: " + "".join(missing))
    styles = getSampleStyleSheet()
    body = ParagraphStyle("CJKBody", fontName="PaperFont", fontSize=10.5, leading=17, wordWrap="CJK", spaceAfter=7)
    title = ParagraphStyle("CJKTitle", parent=body, fontSize=19, leading=26, alignment=TA_CENTER, spaceAfter=16)
    heading = ParagraphStyle("CJKHeading", parent=body, fontSize=13, leading=20, spaceBefore=13, spaceAfter=8, keepWithNext=True)
    caption = ParagraphStyle("CJKCaption", parent=body, fontSize=9, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#475569"))
    cell_style = ParagraphStyle("Cell", parent=body, fontSize=8.5, leading=12, spaceAfter=0)
    story = [Paragraph(html.escape(data["title"]), title)]
    markdown = ["# " + data["title"], ""]
    if data.get("status_note"):
        story.append(Paragraph(html.escape(data["status_note"]), caption))
        story.append(Spacer(1, .25 * cm))
        markdown.extend(["> " + data["status_note"], ""])
    for section in data["sections"]:
        if section.get("page_break_before"):
            story.append(PageBreak())
        story.append(Paragraph(html.escape(section["title"]), heading))
        markdown.extend(["## " + section["title"], ""])
        for block in section["blocks"]:
            if "text" in block:
                text = block["text"]
                story.append(Paragraph(html.escape(text), body))
                markdown.extend([text, ""])
            elif "table" in block:
                rows = block["table"]
                width = 16.6 * cm / len(rows[0])
                table = Table([[Paragraph(html.escape(str(cell)), cell_style) for cell in row] for row in rows],
                              colWidths=[width] * len(rows[0]), repeatRows=1, hAlign="CENTER")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef2")),
                    ("LINEABOVE", (0, 0), (-1, 0), .8, colors.HexColor("#334155")),
                    ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#334155")),
                    ("LINEBELOW", (0, -1), (-1, -1), .8, colors.HexColor("#334155")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(KeepTogether([table, Spacer(1, .2 * cm)]) if len(rows) <= 10 else table)
                for index, row in enumerate(rows):
                    markdown.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |")
                    if index == 0:
                        markdown.append("| " + " | ".join("---" for _ in row) + " |")
                markdown.append("")
            elif "image" in block:
                path = (run / block["image"]).resolve()
                path.relative_to(run)
                graphic = Image(str(path))
                width = float(block.get("width_cm", 16.4)) * cm
                graphic.drawHeight *= width / graphic.drawWidth
                graphic.drawWidth = width
                image_block = [graphic]
                if block.get("caption"):
                    image_block.append(Paragraph(html.escape(block["caption"]), caption))
                story.append(KeepTogether(image_block))
                markdown.extend([f"![{block.get('caption', '')}](../{block['image']})", ""])
    output = run / "paper"
    output.mkdir(exist_ok=True)
    (output / "main.md").write_text("\n".join(markdown), encoding="utf-8")
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("PaperFont", 9)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawCentredString(10.5 * cm, 1.2 * cm, str(document.page))
        canvas.restoreState()
    document = SimpleDocTemplate(str(output / "main.pdf"), pagesize=(21 * cm, 29.7 * cm),
                                 leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=1.9 * cm, bottomMargin=1.9 * cm,
                                 title=data["title"], author="")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = PdfReader(output / "main.pdf")
    report = {"pages": len(pdf.pages), "encrypted": pdf.is_encrypted,
              "text_characters": sum(len(page.extract_text() or "") for page in pdf.pages),
              "visual_review": "PENDING", "source": source.name, "embedded_font": font_path.name}
    (output / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    render(args.run, args.source, args.font)
