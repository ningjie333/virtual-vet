#!/usr/bin/env python3
"""Convert manuscript_v6.md to PDF for review."""

import re, os, textwrap
from fpdf import FPDF

PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(PAPER_DIR, "manuscript_v6.md")
PDF_PATH = os.path.join(PAPER_DIR, "manuscript_v6_final.pdf")

FONT_DIR = "C:/Windows/Fonts"


class ManuscriptPDF(FPDF):
    """Custom PDF class for SIMULATION journal manuscript format."""

    def __init__(self):
        super().__init__("P", "mm", "A4")
        # Register Times New Roman
        self.add_font("TNR", "", os.path.join(FONT_DIR, "times.ttf"))
        self.add_font("TNR", "B", os.path.join(FONT_DIR, "timesbd.ttf"))
        self.add_font("TNR", "I", os.path.join(FONT_DIR, "timesi.ttf"))
        self.add_font("TNR", "BI", os.path.join(FONT_DIR, "timesbi.ttf"))
        self.add_font("CourierNew", "", os.path.join(FONT_DIR, "cour.ttf"))

        self.set_auto_page_break(auto=True, margin=25.4)
        self.line_height = 12.0  # ~ double spacing for 12pt

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("TNR", "I", 9)
        self.cell(0, 10, f"{self.page_no()}", align="C")

    # ── helpers ─────────────────────────────────────────────────────────────────

    def add_title(self, text: str):
        self.set_font("TNR", "B", 16)
        self.multi_cell(0, 10, text.strip(), align="C")
        self.ln(4)

    def add_heading(self, text: str, level: int):
        sizes = {1: 14, 2: 12, 3: 11}
        self.ln(3)
        self.set_font("TNR", "B", sizes.get(level, 12))
        self.multi_cell(0, 7, text.strip())
        self.ln(2)

    def add_paragraph(self, text: str, indent=True):
        """Render a paragraph, handling inline bold/italic/code."""
        if not text.strip():
            return
        self.set_font("TNR", "", 12)
        x = self.get_x()
        y = self.get_y()
        if indent:
            self.cell(5)  # paragraph indent
        # Line width for wrapping
        lw = self.w - self.l_margin - self.r_margin - (5 if indent else 0)
        # Simple word wrap with markdown handling
        self._write_rich_text(text, lw)
        self.ln(self.line_height)

    @staticmethod
    def _sanitize_unicode(text: str) -> str:
        """Replace Unicode glyphs not in Times New Roman with ASCII equivalents."""
        replacements = {
            "∈": " in ",
            "∝": " ~ ",
            "₀": "0",
            "₁": "1",
            "₂": "2",
            "₃": "3",
            "₋": "-",
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    def _write_rich_text(self, text: str, w: float):
        """Write text with inline bold/italic/code support (simplified)."""
        # Strip markdown formatting for PDF
        clean = text
        # Handle bold
        clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
        # Handle italic
        clean = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'\1', clean)
        # Handle code backticks
        clean = re.sub(r'`(.*?)`', r'\1', clean)
        # Handle markdown links [text](url)
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
        # Handle reference URLs: [N] -> keep just [N]
        clean = re.sub(r'\[(\d+)\]', r'[\1]', clean)
        clean = self._sanitize_unicode(clean)
        self.set_font("TNR", "", 12)
        self.multi_cell(w, self.line_height, clean)

    def add_code_block(self, lines: list[str]):
        self.ln(2)
        self.set_font("CourierNew", "", 8)
        self.set_fill_color(245, 245, 245)
        code = "\n".join(lines)
        # Indent the code
        code = "    " + code.replace("\n", "\n    ")
        self.multi_cell(0, 4.5, code, fill=True)
        self.ln(2)

    def add_table(self, rows: list[list[str]]):
        """Render a table with word-wrapped cells and auto-sized columns."""
        if not rows:
            return
        # Filter out separator rows (---|---|---)
        data = []
        for r in rows:
            if all(re.match(r'^[\s\-:|]+$', c.strip()) for c in r):
                continue
            data.append(r)
        if not data:
            return

        self.ln(2)
        ncols = len(data[0])
        max_width = self.w - self.l_margin - self.r_margin  # usable page width

        # Determine font and cell height based on column count
        if ncols >= 8:
            font_size, cell_h = 7, 6
        elif ncols >= 6:
            font_size, cell_h = 8, 6
        elif ncols >= 4:
            font_size, cell_h = 9, 7
        else:
            font_size, cell_h = 9, 7

        # Measure each column's max string width + estimate proportional widths
        self.set_font("TNR", "", font_size)
        col_widths = []
        for ci in range(ncols):
            max_str = ""
            for row in data:
                val = row[ci].strip() if ci < len(row) else ""
                if len(val) > len(max_str):
                    max_str = val
            str_w = self.get_string_width(max_str) + 4  # 2mm padding each side
            col_widths.append(str_w)

        total_w = sum(col_widths)
        if total_w > max_width:
            # Scale down proportionally
            scale = max_width / total_w
            col_widths = [w * scale for w in col_widths]
        else:
            # Distribute remaining space evenly
            extra = (max_width - total_w) / ncols
            col_widths = [w + extra for w in col_widths]
        col_widths[-1] = max_width - sum(col_widths[:-1])  # snap last to edge

        def _render_row(row_data, is_header=False):
            """Render one table row with word-wrapped cells.
            Returns the row height used."""
            row_data = [r.strip() if r else "" for r in row_data]
            # Pad
            while len(row_data) < ncols:
                row_data.append("")

            # Calculate how many lines each cell needs
            max_lines = 1
            cell_lines = []
            for ci in range(ncols):
                txt = row_data[ci]
                cw = col_widths[ci] - 2  # slight inner padding
                self.set_font("TNR", "", font_size)
                lines = []
                words = txt.split()
                if not words:
                    lines = [""]
                else:
                    current = ""
                    for w in words:
                        test = current + (" " if current else "") + w
                        if self.get_string_width(test) > cw and current:
                            lines.append(current)
                            current = w
                        else:
                            current = test
                    lines.append(current)
                cell_lines.append(lines)
                max_lines = max(max_lines, len(lines))

            row_h = max(cell_h, max_lines * (cell_h - 1))

            # Check page break
            if self.get_y() + row_h > self.h - 25.4:
                self.add_page()

            y_start = self.get_y()

            # Draw cells column by column
            x_start = self.get_x()
            for ci in range(ncols):
                x = x_start + sum(col_widths[:ci])
                y = y_start
                cw = col_widths[ci]
                lines = cell_lines[ci]

                # Cell background
                if is_header:
                    self.set_fill_color(240, 240, 240)
                    self.rect(x, y, cw, row_h, "F")
                # Border
                self.rect(x, y, cw, row_h, "D")

                # Text
                if is_header:
                    self.set_font("TNR", "B", font_size)
                else:
                    self.set_font("TNR", "", font_size)
                for li, line in enumerate(lines):
                    ty = y + 1 + li * (cell_h - 1)
                    self.set_xy(x + 1, ty)
                    self.cell(cw - 2, cell_h - 2, line, align="C" if not is_header else "C")

            self.set_xy(x_start, y_start + row_h)

        # Header
        _render_row(data[0], is_header=True)

        # Body
        for row in data[1:]:
            _render_row(row)

        self.ln(3)

    @staticmethod
    def _replace_missing_glyphs(text: str) -> str:
        """Replace Unicode chars not in Times New Roman with ASCII equivalents."""
        return (
            text.replace("∈", " in ")
                .replace("∝", " ~ ")
                .replace("₀", "0")
                .replace("₁", "1")
                .replace("₂", "2")
                .replace("₃", "3")
                .replace("₋", "-")
        )

    def add_figure_caption(self, text: str):
        self.ln(2)
        self.set_font("TNR", "I", 10)
        clean = text.replace("**", "")
        clean = self._replace_missing_glyphs(clean)
        self.multi_cell(0, 6, clean)
        self.ln(2)

    def add_separator(self):
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def add_page_break(self):
        self.add_page()


# ═══════════════════════════════════════════════════════════════════════════════
def _replace_all(text):
    """Replace problematic unicode chars; useful at parse time."""
    return (text.replace("∈", " in ")
                .replace("∝", " ~ ")
                .replace("₀", "0")
                .replace("₁", "1")
                .replace("₂", "2")
                .replace("₃", "3")
                .replace("₋", "-"))


def parse_markdown(md_path: str):
    """Parse markdown into a list of block elements."""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Remove the title page separator (first --- block)
    text = re.sub(r"^---.*?---", "", text, count=1, flags=re.DOTALL)

    lines = text.split("\n")
    blocks = []
    i = 0
    N = len(lines)

    while i < N:
        line = lines[i]
        stripped = line.rstrip()

        # Empty line — skip
        if not stripped.strip():
            i += 1
            continue

        # Image reference (remove completely)
        if re.match(r"!\[.*?\]\(.*?\)", stripped):
            i += 1
            continue

        # Code block
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < N and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip())
                i += 1
            i += 1  # skip closing ```
            if code_lines:
                # Sanitize for CourierNew glyph coverage
                code_lines = [_replace_all(cl) for cl in code_lines]
                blocks.append(("code", code_lines))
            continue

        # Figure caption (starts with **Figure)
        if stripped.startswith("**Figure") or stripped.startswith("*Figure"):
            caption = _replace_all(stripped.strip("* "))
            # Continue collecting multi-line caption
            i += 1
            while i < N and lines[i].strip() and not lines[i].strip().startswith("---"):
                caption += " " + _replace_all(lines[i].strip())
                i += 1
            blocks.append(("caption", caption))
            continue

        # Table (rows starting with |)
        if stripped.startswith("|"):
            table = []
            while i < N and lines[i].strip().startswith("|"):
                cells = [_replace_all(c.strip()) for c in lines[i].strip().strip("|").split("|")]
                table.append(cells)
                i += 1
            if table:
                blocks.append(("table", table))
            continue

        # Horizontal rule → page break
        if stripped.strip() == "---":
            # Check if consecutive
            j = i + 1
            while j < N and not lines[j].strip():
                j += 1
            if j < N and lines[j].strip() == "---":
                blocks.append(("pagebreak", None))
                i = j + 1
                continue
            else:
                blocks.append(("separator", None))
                i += 1
                continue

        # Heading
        hm = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if hm:
            level = len(hm.group(1))
            text = _replace_all(hm.group(2).strip())
            blocks.append(("heading", (level, text)))
            i += 1
            continue

        # Bold standalone line (like **Title**)
        if re.match(r"^\*\*.+\*\*$", stripped):
            blocks.append(("bold", _replace_all(stripped.strip("* "))))
            i += 1
            continue

        # Regular paragraph (collect until blank line or heading)
        para_lines = []
        while i < N:
            l = lines[i].rstrip()
            if not l.strip():
                break
            if l.startswith("```") or l.startswith("|") or l.startswith("---"):
                break
            if re.match(r"^#{1,3}\s", l):
                break
            if re.match(r"!\[", l):
                i += 1
                continue
            # Numbered reference lines: if we already have para text and see
            # a new "N." start, flush the accumulated paragraph first.
            if para_lines and re.match(r"^\d+\.\s", l):
                break
            para_lines.append(_replace_all(l))
            i += 1

        if para_lines:
            para = " ".join(para_lines)
            blocks.append(("paragraph", para))
            continue

        i += 1

    return blocks


# ═══════════════════════════════════════════════════════════════════════════════
def build_pdf(blocks: list, output: str):
    """Build the PDF from parsed blocks."""
    pdf = ManuscriptPDF()
    pdf.set_margins(25.4, 25.4, 25.4)  # 1 inch
    pdf.add_page()

    for btype, bdata in blocks:
        if btype == "paragraph":
            pdf.add_paragraph(bdata)
        elif btype == "heading":
            level, text = bdata
            pdf.add_heading(text, level)
        elif btype == "code":
            pdf.add_code_block(bdata)
        elif btype == "table":
            pdf.add_table(bdata)
        elif btype == "caption":
            pdf.add_figure_caption(bdata)
        elif btype == "separator":
            pdf.add_separator()
        elif btype == "pagebreak":
            pdf.add_page_break()
        elif btype == "bold":
            pdf.set_font("TNR", "B", 12)
            pdf.multi_cell(0, pdf.line_height, bdata)
            pdf.ln(2)

    pdf.output(output)
    print(f"  Saved: {output}")


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Parsing manuscript...")
    blocks = parse_markdown(MD_PATH)
    print(f"  Found {len(blocks)} blocks")

    # Count by type
    counts = {}
    for btype, _ in blocks:
        counts[btype] = counts.get(btype, 0) + 1
    for k, v in sorted(counts.items()):
        print(f"    {k}: {v}")

    print("Generating PDF...")
    build_pdf(blocks, PDF_PATH)
    print("Done.")
