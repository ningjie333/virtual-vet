"""
Generate PDF from manuscript_v1.md with embedded figures.
Requires: fpdf2
"""
import os, re, base64
from fpdf import FPDF

PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(PAPER_DIR, 'manuscript_v1.md')
FIG_DIR = os.path.join(PAPER_DIR, 'figures')
OUT_PATH = os.path.join(PAPER_DIR, 'manuscript_v1.pdf')

# ── parse markdown ──────────────────────────────────────────────
def parse_md(path):
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # headings
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            blocks.append(('H', level, m.group(2).strip()))
            i += 1
            continue
        # horizontal rule
        if re.match(r'^---+$', line.strip()):
            blocks.append(('HR',))
            i += 1
            continue
        # table: collect rows until blank or non-table row
        if '|' in line and line.strip().startswith('|'):
            table_rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                row = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                table_rows.append(row)
                i += 1
            blocks.append(('TABLE', table_rows))
            continue
        # code block
        if line.startswith('```'):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i].rstrip())
                i += 1
            blocks.append(('CODE', lang, '\n'.join(code_lines)))
            i += 1  # skip closing ```
            continue
        # blank line
        if line.strip() == '':
            blocks.append(('BLANK',))
            i += 1
            continue
        # paragraph
        para = line.rstrip()
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#'):
            para += ' ' + lines[i].strip()
            i += 1
        # inline figures: "![alt](path)" → store for rendering
        blocks.append(('P', para))
    return blocks

# ── build PDF ──────────────────────────────────────────────────
class PDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Order-Dependent Bias in Sequential Euler - v1    Page {self.page_no()}', align='C')

    def section_title(self, level, text):
        if level == 1:
            self.set_font('Helvetica', 'B', 16)
            self.set_text_color(30, 30, 30)
            self.ln(4)
            self.cell(0, 10, self.sanitize_text(text), new_x='LMARGIN', new_y='NEXT')
            self.ln(2)
        elif level == 2:
            self.set_font('Helvetica', 'B', 13)
            self.set_text_color(40, 40, 40)
            self.ln(2)
            self.cell(0, 8, self.sanitize_text(text), new_x='LMARGIN', new_y='NEXT')
            self.ln(1)
        elif level == 3:
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(50, 50, 50)
            self.ln(2)
            self.cell(0, 7, self.sanitize_text(text), new_x='LMARGIN', new_y='NEXT')
            self.ln(1)
        else:
            self.set_font('Helvetica', 'B', 10)
            self.cell(0, 7, self.sanitize_text(text), new_x='LMARGIN', new_y='NEXT')

    def sanitize_text(self, text):
        """Remove or replace all non-latin-1 characters."""
        # Greek letters
        greek = {
            'α':'alpha','β':'beta','γ':'gamma','δ':'delta','ε':'epsilon',
            'ζ':'zeta','η':'eta','θ':'theta','ι':'iota','κ':'kappa',
            'λ':'lambda','μ':'mu','ν':'nu','ξ':'xi','ο':'omicron',
            'π':'pi','ρ':'rho','σ':'sigma','τ':'tau','υ':'upsilon',
            'φ':'phi','χ':'chi','ψ':'psi','ω':'omega',
            'Α':'Alpha','Β':'Beta','Γ':'Gamma','Δ':'Delta','Ε':'Epsilon',
            'Θ':'Theta','Λ':'Lambda','Ξ':'Xi','Π':'Pi','Σ':'Sigma',
            'Φ':'Phi','Ψ':'Psi','Ω':'Omega',
        }
        for k, v in greek.items():
            text = text.replace(k, v)
        # replace Unicode chars
        text = text.replace('→','->').replace('←','<-').replace('↔','<->')
        text = text.replace('↑','^').replace('↓','v')
        text = text.replace('²','^2').replace('³','^3').replace('¹','^1')
        text = text.replace('½','1/2').replace('¼','1/4').replace('¾','3/4')
        text = text.replace('×','x').replace('÷','/')
        text = text.replace('—','--').replace('–','-').replace('‘',"'").replace('’',"'")
        text = text.replace('“','"').replace('”','"').replace('…','...')
        text = text.replace(' ',' ')
        for i in range(10):
            text = text.replace(chr(0x2080+i), f'_{i}')
            text = text.replace(chr(0x2070+i), f'^{i}')
        text = text.replace('⁰','^0').replace('°',' deg')
        text = text.replace('≤','<=').replace('≥','>=').replace('≠','!=')
        text = text.replace('∈','in').replace('∉','not in')
        text = text.replace('∂','d').replace('∇','grad')
        # remove any remaining non-latin-1 chars
        text = text.encode('latin-1', errors='replace').decode('latin-1')
        return text

    def para(self, text):
        # handle inline bold/italic
        self.set_font('Helvetica', '', 10)
        self.set_text_color(20, 20, 20)
        # replace **bold**
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'`(.*?)`', r'\1', text)
        # replace Unicode arrows and special chars
        text = text.replace('→', '->').replace('←', '<-').replace('↔', '<->')
        text = text.replace('²', '^2').replace('³', '^3')
        text = text.replace('⁰', '^0').replace('¹', '^1').replace('½', '1/2')
        text = text.replace('×', 'x').replace('÷', '/')
        text = text.replace('τ', 'tau').replace('α', 'alpha').replace('Δ', 'Delta')
        # subscripts: ₜ → _t, ₀ → _0, ₁ → _1, ₂ → _2, etc.
        for i in range(10):
            text = text.replace(chr(0x2080+i), f'_{i}')
        text = text.replace('Τ', 'Sigma').replace('λ', 'lambda')
        # handle markdown image refs -> we handle separately
        if text.strip():
            self.multi_cell(0, 5.5, self.sanitize_text(text), new_x='LMARGIN', new_y='NEXT')
            self.ln(1)

    def code_block(self, lang, code):
        self.set_font('Courier', '', 8)
        self.set_fill_color(248, 248, 248)
        self.set_text_color(50, 50, 50)
        lines = code.split('\n')
        for l in lines:
            self.cell(0, 4.5, self.sanitize_text(l[:120]), new_x='LMARGIN', new_y='NEXT', fill=True)
        self.ln(2)
        self.set_text_color(20, 20, 20)

    def render_table(self, rows):
        if not rows:
            return
        # col widths
        n_col = len(rows[0])
        col_w = (self.w - 2 * self.l_margin) / n_col
        self.set_font('Helvetica', 'B', 8)
        self.set_fill_color(220, 230, 242)
        # header row
        for j, cell in enumerate(rows[0]):
            x = self.get_x() + j * col_w
            self.set_xy(x, self.get_y())
            self.cell(col_w, 6, self.sanitize_text(cell[:30]), border=1, fill=True, align='C')
        self.ln()
        # data rows
        for ri, row in enumerate(rows[1:]):
            self.set_font('Helvetica', '', 8)
            fill = ri % 2 == 0
            if fill:
                self.set_fill_color(245, 248, 252)
            else:
                self.set_fill_color(255, 255, 255)
            for j, cell in enumerate(row):
                x = self.get_x() + j * col_w
                self.set_xy(x, self.get_y())
                self.cell(col_w, 5.5, self.sanitize_text(cell[:30]), border=1, fill=fill, align='C')
            self.ln()
        self.ln(3)

    def insert_figure(self, fig_name, caption, w=None):
        if w is None:
            w = min(170, self.w - 2 * self.l_margin)
        fig_path = os.path.join(FIG_DIR, fig_name)
        if not os.path.exists(fig_path):
            self.set_font('Helvetica', 'I', 9)
            self.set_text_color(180, 0, 0)
            self.multi_cell(0, 5, f'[Figure not found: {fig_name}]', ln=True)
            self.set_text_color(20, 20, 20)
            return
        self.ln(2)
        x = self.get_x()
        self.image(fig_path, x=x, w=w)
        # caption below
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(80, 80, 80)
        cap_y = self.get_y() + 1
        self.set_xy(x, cap_y)
        self.multi_cell(w, 4.5, self.sanitize_text(caption), new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(20, 20, 20)
        self.ln(3)

# ── map figure names to figure numbers ────────────────────────
FIG_MAP = {
    'fig_1_architecture.png':     ('Figure 1: Virtual Vet 11-Organ Architecture and Baroreflex Loop', 170),
    'fig_2_convergence.png':      ('Figure 2: Pure Euler Convergence — First Order Confirmed', 160),
    'fig_3_baseline_swap.png':    ('Figure 3: Baseline Swap — Order Determines Equilibrium MAP', 170),
    'fig_4_hemorrhage_transient.png': ('Figure 4: Hemorrhage Transient — Order Accuracy Reversal at t=30s', 170),
    'fig_5_dt_independence.png':  ('Figure 5: Convergence Comparison — Pure vs Sequential Euler', 170),
    'fig_s1_dt_invariance.png':    ('Figure S1: Sequential Euler MAP at t=60s — dt-Independence Confirmed', 170),
}

# ── main ──────────────────────────────────────────────────────
pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

blocks = parse_md(MD_PATH)

for block in blocks:
    kind = block[0]

    if kind == 'H':
        _, lvl, text = block
        # check if page break needed
        if pdf.get_y() > 240 and lvl <= 2:
            pdf.add_page()
        pdf.section_title(lvl, text)

    elif kind == 'HR':
        pdf.ln(2)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)

    elif kind == 'P':
        text = block[1]
        # check for figure inserts mid-text
        if '![' in text:
            # find all figure refs
            for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
                before = text[:match.start()]
                after = text[match.end():]
                if before.strip():
                    pdf.para(before)
                fname = os.path.basename(match.group(2))
                cap, w = FIG_MAP.get(fname, (f'[{fname}]', 140))
                pdf.insert_figure(fname, cap, w)
                text = after
            if text.strip():
                pdf.para(text)
        else:
            pdf.para(text)

    elif kind == 'CODE':
        _, lang, code = block
        pdf.code_block(lang, code)

    elif kind == 'TABLE':
        pdf.render_table(block[1])

    elif kind == 'BLANK':
        pass

# ── save ──────────────────────────────────────────────────────
pdf.output(OUT_PATH)
print(f'PDF saved to: {OUT_PATH}')