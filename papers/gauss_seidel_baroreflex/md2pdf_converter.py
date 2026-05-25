"""
Markdown to PDF converter using reportlab with SimHei font for Chinese support.
"""
import os, re, markdown
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAPER_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(PAPER_DIR, 'manuscript_v1.md')
OUT_PATH = os.path.join(PAPER_DIR, 'manuscript_v1_cjk.pdf')

# Register Chinese font
try:
    pdfmetrics.registerFont(TTFont('SimHei', 'C:/Windows/Fonts/simhei.ttf'))
    FONT = 'SimHei'
except Exception:
    FONT = 'Helvetica'

STYLES = {
    'normal': ParagraphStyle('Chinese', fontName=FONT, fontSize=10, leading=16, spaceAfter=6),
    'h1': ParagraphStyle('H1', fontName=FONT, fontSize=18, leading=22, spaceBefore=18, spaceAfter=8, textColor=colors.HexColor('#1a1a1a')),
    'h2': ParagraphStyle('H2', fontName=FONT, fontSize=14, leading=18, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor('#2a2a2a')),
    'h3': ParagraphStyle('H3', fontName=FONT, fontSize=12, leading=15, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor('#333')),
    'bq': ParagraphStyle('BQ', fontName=FONT, fontSize=10, leftIndent=20, backColor=colors.Color(0.96, 0.96, 0.96), leading=14),
    'cell': ParagraphStyle('Cell', fontName=FONT, fontSize=9, leading=12),
    'fig_cap': ParagraphStyle('FigCap', fontName=FONT, fontSize=9, leading=12, alignment=1, textColor=colors.HexColor('#555')),
    'code': ParagraphStyle('Code', fontName='Courier', fontSize=8, backColor=colors.Color(0.95, 0.95, 0.95), leftIndent=8, rightIndent=8, leading=11),
}


def clean_html(text):
    return re.sub(r'<[^>]*>', '', text).strip()


def fix_special_chars(text):
    """Fix Unicode chars that reportlab can't render: subscripts, superscripts, arrows, Greek, etc."""
    # Subscripts
    for i in range(10):
        text = text.replace(chr(0x2080 + i), '_' + str(i))
    # Superscripts
    for i in range(10):
        text = text.replace(chr(0x2070 + i), '^' + str(i))
    text = text.replace('⁰', '^0')
    text = text.replace('ⁱ', '^1')
    text = text.replace('⁴', '^4')
    text = text.replace('⁵', '^5')
    text = text.replace('⁶', '^6')
    text = text.replace('⁷', '^7')
    text = text.replace('⁸', '^8')
    text = text.replace('⁹', '^9')
    text = text.replace('⁻', '^-')
    # Arrows
    text = text.replace('→', '->').replace('←', '<-').replace('↔', '<->')
    # Greek
    greek = {
        'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta',
        'ε': 'epsilon', 'ζ': 'zeta', 'η': 'eta', 'θ': 'theta',
        'κ': 'kappa', 'λ': 'lambda', 'μ': 'mu', 'ν': 'nu',
        'ξ': 'xi', 'ο': 'omicron', 'π': 'pi', 'ρ': 'rho',
        'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon', 'φ': 'phi',
        'χ': 'chi', 'ψ': 'psi', 'ω': 'omega',
        'Α': 'Alpha', 'Β': 'Beta', 'Γ': 'Gamma', 'Δ': 'Delta',
        'Ε': 'Epsilon', 'Θ': 'Theta', 'Λ': 'Lambda', 'Ξ': 'Xi',
        'Π': 'Pi', 'Σ': 'Sigma', 'Φ': 'Phi', 'Ψ': 'Psi', 'Ω': 'Omega',
    }
    for k, v in greek.items():
        text = text.replace(k, v)
    # Math / symbols
    text = text.replace('≤', '<=').replace('≥', '>=').replace('≠', '!=')
    text = text.replace('∈', 'in').replace('∉', 'not in').replace('∞', 'inf')
    text = text.replace('∂', 'd').replace('∇', 'grad').replace('∆', 'delta')
    text = text.replace('×', 'x').replace('÷', '/').replace('≈', '~')
    text = text.replace('±', '+/-').replace('°', 'deg')
    text = text.replace('²', '^2').replace('³', '^3')
    text = text.replace('¼', '1/4').replace('½', '1/2').replace('¾', '3/4')
    # Em dashes and hyphens
    text = text.replace('—', '--').replace('–', '-')
    # Smart quotes - use unicode code points to avoid parser issues
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('…', '...')
    # Non-breaking space
    text = text.replace(' ', ' ')
    return text


def md_to_pdf(md_path, out_path):
    with open(md_path, encoding='utf-8') as f:
        md_content = f.read()

    # Remove HTML comments
    md_content = re.sub(r'<!--.*?-->', '', md_content, flags=re.DOTALL)

    html = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
        title='Order-Dependent Bias in Sequential Euler',
        author='Virtual Vet Research',
    )

    story = []
    content = html.replace('\n', '')
    blocks = re.split(
        r'(<h[123][^>]*>.*?</h[123]>|<pre>.*?</pre>|<blockquote>.*?</blockquote>'
        r'|<p>.*?</p>|<table>.*?</table>|<hr[^>]*/?>)',
        content, flags=re.DOTALL
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if block.startswith('<h1'):
            story.append(Paragraph(fix_special_chars(clean_html(block)), STYLES['h1']))
        elif block.startswith('<h2'):
            story.append(Paragraph(fix_special_chars(clean_html(block)), STYLES['h2']))
        elif block.startswith('<h3'):
            story.append(Paragraph(fix_special_chars(clean_html(block)), STYLES['h3']))
        elif block.startswith('<pre'):
            story.append(Spacer(1, 4))
            story.append(Paragraph(fix_special_chars(clean_html(block)), STYLES['code']))
            story.append(Spacer(1, 4))
        elif block.startswith('<blockquote'):
            story.append(Paragraph(fix_special_chars(clean_html(block)), STYLES['bq']))
        elif block.startswith('<hr'):
            story.append(Spacer(1, 8))
            story.append(HRFlowable(width='100%', thickness=0.5, color=colors.gray))
            story.append(Spacer(1, 8))
        elif block.startswith('<table'):
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', block, flags=re.DOTALL)
            table_data = []
            for ri, row in enumerate(rows):
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, flags=re.DOTALL)
                if cells:
                    row_cells = [Paragraph(fix_special_chars(clean_html(c)), STYLES['cell']) for c in cells]
                    table_data.append(row_cells)

            if table_data:
                num_cols = len(table_data[0])
                page_width = A4[0] - 4*cm
                col_w = page_width / num_cols
                t = Table(table_data, colWidths=[col_w]*num_cols, repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.85, 0.88, 0.95)),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                    *[('BACKGROUND', (0, i), (-1, i), colors.Color(0.97, 0.97, 1.0))
                      for i in range(2, len(table_data), 2)],
                ]))
                story.append(t)
                story.append(Spacer(1, 8))
        elif block.startswith('<p>'):
            text = clean_html(block)
            if not text:
                continue
            # Handle inline images: ![alt](path)
            if '![' in text:
                parts = re.split(r'(<!\[.*?\]\([^)]+\))', text)
                for part in parts:
                    m = re.match(r'<!\[([^\]]*)\]\(([^)]+)\)', part)
                    if m:
                        fname = os.path.basename(m.group(2))
                        cap = m.group(1)
                        fig_path = os.path.join(PAPER_DIR, 'figures', fname)
                        if os.path.exists(fig_path):
                            img_w = min(16, A4[0] - 4*cm)
                            story.append(Spacer(1, 6))
                            story.append(Image(fig_path, width=img_w, height=img_w * 0.55))
                            story.append(Paragraph('Figure: ' + fix_special_chars(cap), STYLES['fig_cap']))
                            story.append(Spacer(1, 6))
                        else:
                            story.append(Paragraph('[Figure not found: ' + fname + ']', STYLES['normal']))
                    elif part.strip():
                        story.append(Paragraph(fix_special_chars(part), STYLES['normal']))
                story.append(Spacer(1, 4))
            else:
                story.append(Paragraph(fix_special_chars(text), STYLES['normal']))

    doc.build(story)
    print('PDF saved to: ' + out_path)


if __name__ == '__main__':
    md_to_pdf(MD_PATH, OUT_PATH)