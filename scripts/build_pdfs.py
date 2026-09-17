from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "knowledge" / "sources"
PDF_DIR = ROOT / "knowledge" / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)


class ReportPDF(FPDF):
    def header(self) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(27, 58, 47)
        self.cell(0, 8, "Darukaa.Earth | Biodiversity Intelligence Knowledge Base", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(197, 225, 122)
        self.set_line_width(0.6)
        self.line(self.l_margin, 16, 210 - self.r_margin, 16)
        self.set_y(20)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(90, 100, 90)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def render_markdown_as_pdf(md_path: Path, pdf_path: Path) -> None:
    pdf = ReportPDF()
    pdf.set_left_margin(14)
    pdf.set_right_margin(14)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_text_color(26, 46, 36)
    usable = pdf.epw
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line:
            pdf.ln(3)
            continue
        pdf.set_x(pdf.l_margin)
        if line.startswith("#"):
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(usable, 8, line.lstrip("# ").encode("latin-1", "replace").decode("latin-1"))
            pdf.ln(1)
            continue
        if len(line) > 1 and line[0].isdigit() and line[1] == ".":
            pdf.set_font("Helvetica", "B", 12)
        else:
            pdf.set_font("Helvetica", "", 11)
        safe = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(usable, 6, safe)
    pdf.output(str(pdf_path))


def main() -> None:
    count = 0
    for md in sorted(SOURCE.glob("*.md")):
        out = PDF_DIR / (md.stem + ".pdf")
        render_markdown_as_pdf(md, out)
        print(f"Wrote {out.name}")
        count += 1
    if count == 0:
        print("No markdown sources found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
