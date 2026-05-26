"""Script para gerar Manual do Usuário (.docx) e Apresentação (.pptx)"""

# ── DOCX ──────────────────────────────────────────────────────────────────────
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

AZUL_ESCURO = RGBColor(0x1E, 0x3A, 0x5F)
AZUL_MEDIO  = RGBColor(0x2E, 0x6D, 0xA4)
AZUL_CLARO  = RGBColor(0xD6, 0xE4, 0xF0)
BRANCO      = RGBColor(0xFF, 0xFF, 0xFF)
CINZA_ALT   = RGBColor(0xF0, 0xF4, 0xF8)


def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def add_heading(doc, text, level=1):
    p = doc.add_paragraph(style=f'Heading {level}')
    run = p.runs[0] if p.runs else p.add_run(text)
    if not p.runs:
        run = p.add_run(text)
    else:
        run.text = text
    run.bold = True
    run.font.color.rgb = AZUL_ESCURO
    run.font.size = Pt(14 if level == 1 else 12)
    return p


def add_body(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.name = 'Calibri'
    return p


def add_tip(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    shading = OxmlElement('w:pPr')
    run = p.add_run(f'💡  {text}')
    run.font.size = Pt(10)
    run.font.color.rgb = AZUL_MEDIO
    run.font.italic = True
    return p


def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
    hdr = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.color.rgb = BRANCO
        run.font.size = Pt(10)
        set_cell_bg(cell, '1E3A5F')

    # Data rows
    for ri, row in enumerate(rows):
        tr = table.rows[ri + 1]
        bg = 'F0F4F8' if ri % 2 == 0 else 'FFFFFF'
        for ci, val in enumerate(row):
            cell = tr.cells[ci]
            cell.text = ''
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(10)
            set_cell_bg(cell, bg)

    # Column widths
    if col_widths:
        for i, w in enumerate(col_widths):
            for cell in table.columns[i].cells:
                cell.width = Inches(w)

    doc.add_paragraph()
    return table


def build_docx():
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin    = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin   = Inches(1.2)
        section.right_margin  = Inches(1.2)

        # Header
        header = section.header
        hp = header.paragraphs[0]
        hp.text = 'Ferragens Pinheiro — Requisições App'
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for run in hp.runs:
            run.font.size = Pt(9)
            run.font.color.rgb = AZUL_MEDIO

        # Footer
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_f = fp.add_run('Página ')
        run_f.font.size = Pt(9)
        fldChar1 = OxmlElement('w:fldChar')
        fldChar1.set(qn('w:fldCharType'), 'begin')
        instrText = OxmlElement('w:instrText')
        instrText.text = 'PAGE'
        fldChar2 = OxmlElement('w:fldChar')
        fldChar2.set(qn('w:fldCharType'), 'end')
        run_pg = fp.add_run()
        run_pg._r.append(fldChar1)
        run_pg._r.append(instrText)
        run_pg._r.append(fldChar2)
        run_pg.font.size = Pt(9)

    # ── CAPA ──────────────────────────────────────────────────────────────────
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(80)
    run = p_title.add_run('Manual do Usuário')
    run.bold = True
    run.font.size = Pt(28)
    run.font.color.rgb = AZUL_ESCURO
    run.font.name = 'Calibri'

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_sub.add_run('Requisições App  v1.1.0')
    run.font.size = Pt(16)
    run.font.color.rgb = AZUL_MEDIO
    run.font.name = 'Calibri'

    p_emp = doc.add_paragraph()
    p_emp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_emp.paragraph_format.space_before = Pt(20)
    run = p_emp.add_run('Ferragens Pinheiro')
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = AZUL_ESCURO

    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_date.add_run('Maio de 2026')
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_page_break()

    # ── 1. PRIMEIRO ACESSO ────────────────────────────────────────────────────
    add_heading(doc, '1. Primeiro Acesso e Login')
    add_heading(doc, 'Abrindo o sistema', 2)
    add_body(doc, 'Clique duas vezes no ícone Requisições App na área de trabalho ou na barra de tarefas.')

    add_heading(doc, 'Fazendo login', 2)
    for step in [
        '1.  Digite seu código de usuário no primeiro campo.',
        '2.  Digite sua senha no segundo campo.',
        '3.  Clique em Entrar ou pressione Enter.',
    ]:
        p = doc.add_paragraph(style='List Number')
        p.add_run(step.split('. ', 1)[1]).font.size = Pt(11)

    add_tip(doc, 'Primeiro acesso: se for a primeira vez, será solicitado que você crie uma nova senha.')

    add_heading(doc, 'Esqueci minha senha', 2)
    add_body(doc, 'Entre em contato com o administrador do sistema para redefinição de senha.')

    # ── 2. TELA PRINCIPAL ─────────────────────────────────────────────────────
    add_heading(doc, '2. Tela Principal e Navegação')
    add_heading(doc, 'Sidebar', 2)
    add_body(doc, 'A sidebar exibe apenas as telas disponíveis para o seu perfil:')
    add_table(doc,
        ['Ícone', 'Tela', 'Disponível para'],
        [
            ['📊', 'Dashboard', 'Admin, Gerente'],
            ['📋', 'Central de Pedidos', 'Todos'],
            ['🏭', 'A&R / Indústria', 'Producao, Indústria, Admin, Gerente'],
            ['👥', 'Gestão de Usuários', 'Admin'],
            ['🔧', 'Painel Técnico', 'Admin'],
            ['🕐', 'Histórico', 'Todos'],
            ['💬', 'Feedback', 'Todos'],
            ['⚙️', 'Configurações', 'Todos'],
        ],
        col_widths=[0.7, 2.0, 2.8]
    )

    add_heading(doc, 'Tema claro/escuro', 2)
    add_body(doc, 'Clique no ícone de lua/sol na parte inferior da sidebar para alternar entre modo claro e escuro.')

    # ── 3. CENTRAL DE PEDIDOS ─────────────────────────────────────────────────
    add_heading(doc, '3. Central de Pedidos')
    add_body(doc, 'A Central de Pedidos é a tela principal do sistema, onde você visualiza, cria e gerencia as requisições.')
    add_heading(doc, 'Status das requisições', 2)
    add_table(doc,
        ['Status', 'Significado'],
        [
            ['🔵 Em andamento', 'Requisição em elaboração ou aguardando'],
            ['🟡 Aguardando recebimento', 'Material aguardando chegada'],
            ['🟠 Em produção', 'Em processamento pela A&R ou Indústria'],
            ['🟢 Faturado', 'Pedido faturado e concluído'],
            ['🔴 Cancelada', 'Requisição cancelada'],
        ],
        col_widths=[2.2, 3.5]
    )

    # ── 4. CRIANDO REQUISIÇÃO ─────────────────────────────────────────────────
    add_heading(doc, '4. Criando uma Nova Requisição')
    add_tip(doc, 'Disponível para: Vendedor, Gerente, Admin.')
    add_heading(doc, 'Passo a passo', 2)
    steps = [
        'Na Central de Pedidos, clique em + Nova Requisição.',
        'Busque o cliente digitando nome, código ou CNPJ. Clique no cliente desejado.',
        'Preencha o número do pedido (campo PED).',
        'Informe se é retirada ou entrega.',
        'Adicione os itens: clique em + Adicionar Item, busque o produto, informe quantidade e preço.',
        'Adicione observações se necessário.',
        'Clique em Salvar. O PDF será gerado e enviado automaticamente para a pasta de rede.',
    ]
    for s in steps:
        p = doc.add_paragraph(style='List Number')
        p.add_run(s).font.size = Pt(11)

    # ── 5. EDITOR DE DESENHO ──────────────────────────────────────────────────
    add_heading(doc, '5. Editor de Desenho')
    add_body(doc, 'O editor permite criar croquis, anotações e medidas diretamente na requisição.')
    add_heading(doc, 'Ferramentas disponíveis', 2)
    add_table(doc,
        ['Ferramenta', 'Atalho', 'Função'],
        [
            ['Seleção', 'S', 'Seleciona e move elementos'],
            ['Caneta', 'P', 'Desenho livre'],
            ['Linha', 'L', 'Linha reta com snap nos extremos'],
            ['Seta', 'A', 'Linha com ponta de seta'],
            ['Retângulo', 'R', 'Retângulo'],
            ['Triângulo', 'T', 'Triângulo'],
            ['Texto', 'X', 'Inserir texto'],
            ['Cota MM', 'M', 'Medida em milímetros com rótulo automático'],
            ['Borracha', 'E', 'Apagar elementos'],
        ],
        col_widths=[1.5, 0.8, 3.4]
    )
    add_tip(doc, 'Pressione Esc para desmarcar a ferramenta sem fechar o editor.')
    add_tip(doc, 'A ferramenta Cota MM posiciona o rótulo automaticamente para evitar sobreposição.')

    # ── 6. HISTÓRICO ──────────────────────────────────────────────────────────
    add_heading(doc, '6. Histórico de Requisições')
    add_body(doc, 'O histórico exibe todas as requisições, independentemente do status.')
    add_heading(doc, 'Filtros disponíveis', 2)
    for item in ['Data: filtre por intervalo de datas.', 'Status: filtre por um ou mais status.', 'Vendedor/Cliente: busca por texto.']:
        p = doc.add_paragraph(style='List Bullet')
        p.add_run(item).font.size = Pt(11)

    # ── 7. NOTIFICAÇÕES ───────────────────────────────────────────────────────
    add_heading(doc, '7. Notificações')
    add_body(doc, 'O sistema envia notificações em tempo real para eventos importantes.')
    for item in [
        'O badge vermelho no sino indica notificações não lidas.',
        'Clique no sino para abrir o painel lateral com todas as notificações.',
        'Notificações novas aparecem como toasts no canto da tela.',
    ]:
        p = doc.add_paragraph(style='List Bullet')
        p.add_run(item).font.size = Pt(11)

    # ── 8. CALCULADORA ────────────────────────────────────────────────────────
    add_heading(doc, '8. Calculadora de Peso')
    add_body(doc, 'Calcula a massa de materiais metálicos com base em dimensões.')
    for step in [
        'Selecione o tipo de perfil (chato, quadrado, redondo, tubo etc.).',
        'Informe as dimensões em milímetros.',
        'Informe o comprimento em metros.',
        'O resultado em kg é exibido automaticamente.',
    ]:
        p = doc.add_paragraph(style='List Number')
        p.add_run(step).font.size = Pt(11)
    add_tip(doc, 'A densidade do aço (7,865 g/cm³) é fixa e não pode ser alterada.')

    # ── 9. CONFIGURAÇÕES ──────────────────────────────────────────────────────
    add_heading(doc, '9. Configurações')
    add_table(doc,
        ['Opção', 'Função'],
        [
            ['Tema', 'Alterna entre claro e escuro'],
            ['Tamanho da fonte', 'Ajusta o tamanho da fonte da interface'],
            ['Pasta de backgrounds', 'Define a pasta de imagens de fundo do login'],
            ['Alerta de vencimento', 'Define quantos dias antes de alertar sobre notas a vencer'],
            ['Alterar senha', 'Permite alterar sua senha de acesso'],
            ['Ver Guia Rápido', 'Abre o tour interativo do sistema'],
            ['Verificar atualizações', 'Verifica se há nova versão disponível'],
        ],
        col_widths=[2.0, 4.0]
    )

    # ── 10. GUIA RÁPIDO ───────────────────────────────────────────────────────
    add_heading(doc, '10. Guia Rápido')
    add_body(doc, 'O Guia Rápido é um tour interativo que apresenta as principais funcionalidades.')
    add_tip(doc, 'Aparece automaticamente no primeiro login. Pode ser reaberto em Configurações → Ver Guia Rápido.')
    for item in [
        'Use Próximo e Anterior para navegar entre as dicas.',
        'Clique em Fechar para encerrar o tour.',
        'O guia destaca o elemento relevante na tela com animação de foco.',
    ]:
        p = doc.add_paragraph(style='List Bullet')
        p.add_run(item).font.size = Pt(11)

    # ── 11. PERFIS ────────────────────────────────────────────────────────────
    add_heading(doc, '11. Perfis de Acesso')
    add_table(doc,
        ['Perfil', 'O que pode fazer'],
        [
            ['Admin', 'Acesso total — usuários, painel técnico, configurações avançadas'],
            ['Gerente', 'Dashboard, central de pedidos, histórico, gestão de usuários'],
            ['Vendedor', 'Criar, editar e acompanhar suas requisições'],
            ['Produção (A&R)', 'Visualizar requisições e tela de A&R em modo leitura'],
            ['Indústria', 'Visualizar requisições e tela de Indústria em modo leitura'],
            ['Entrega', 'Visualizar Central de Pedidos em modo leitura'],
        ],
        col_widths=[1.8, 4.5]
    )

    # ── 12. FAQ ───────────────────────────────────────────────────────────────
    add_heading(doc, '12. Perguntas Frequentes')
    faqs = [
        ('O PDF não foi gerado. O que fazer?',
         'Verifique se o caminho da pasta de PDFs está acessível na rede. Contate o administrador se persistir.'),
        ('Não consigo ver determinada tela.',
         'Cada perfil tem acesso apenas às telas pertinentes à sua função. Solicite acesso ao administrador.'),
        ('O sistema avisou que há uma atualização. Posso instalar?',
         'Sim. Clique em "Atualizar agora". O sistema baixa, aplica e reabre automaticamente. Seus dados são preservados.'),
        ('Esqueci minha senha.',
         'Entre em contato com o administrador do sistema para redefinição.'),
    ]
    for q, a in faqs:
        p = doc.add_paragraph()
        run = p.add_run(q)
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = AZUL_ESCURO
        add_body(doc, a)
        doc.add_paragraph()

    out = r'C:\Users\João\Desktop\requisicoes\docs\Manual_do_Usuario_Requisicoes_App.docx'
    doc.save(out)
    print(f'DOCX salvo: {out}')


# ── PPTX ──────────────────────────────────────────────────────────────────────
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor as PptxRGB
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

AZUL   = PptxRGB(0x1E, 0x3A, 0x5F)
AZUL_M = PptxRGB(0x2E, 0x6D, 0xA4)
AZUL_C = PptxRGB(0xD6, 0xE4, 0xF0)
BRANCO_P = PptxRGB(0xFF, 0xFF, 0xFF)
CINZA  = PptxRGB(0xF0, 0xF4, 0xF8)
VERDE  = PptxRGB(0x27, 0xAE, 0x60)
LARANJA = PptxRGB(0xE6, 0x7E, 0x22)

W = Inches(13.33)
H = Inches(7.5)


def prs_new():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H
    return prs


def blank_slide(prs):
    layout = prs.slide_layouts[6]  # blank
    return prs.slides.add_slide(layout)


def bg(slide, color: PptxRGB):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def box(slide, x, y, w, h, fill_color=None, line_color=None, line_width=Pt(0)):
    from pptx.util import Emu
    shape = slide.shapes.add_shape(1, x, y, w, h)  # MSO_SHAPE_TYPE.RECTANGLE = 1
    shape.line.width = line_width
    if fill_color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
    else:
        shape.fill.background()
    if line_color:
        shape.line.color.rgb = line_color
    else:
        shape.line.fill.background()
    return shape


def txbox(slide, x, y, w, h, text, size=Pt(14), color=BRANCO_P, bold=False, align=PP_ALIGN.LEFT, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = size
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = 'Calibri'
    return tb


def title_slide_layout(slide, title, subtitle='', footer='', dark=True):
    bg(slide, AZUL if dark else CINZA)
    # Title
    txbox(slide, Inches(1), Inches(2.2), Inches(11.3), Inches(1.5),
          title, size=Pt(44), color=BRANCO_P if dark else AZUL, bold=True, align=PP_ALIGN.CENTER)
    if subtitle:
        txbox(slide, Inches(1), Inches(3.8), Inches(11.3), Inches(0.8),
              subtitle, size=Pt(22), color=AZUL_C if dark else AZUL_M, align=PP_ALIGN.CENTER)
    if footer:
        txbox(slide, Inches(1), Inches(6.2), Inches(11.3), Inches(0.6),
              footer, size=Pt(14), color=PptxRGB(0xAA, 0xBB, 0xCC) if dark else AZUL_M, align=PP_ALIGN.CENTER)


def content_title(slide, title):
    txbox(slide, Inches(0.5), Inches(0.25), Inches(12.3), Inches(0.7),
          title, size=Pt(28), color=AZUL, bold=True, align=PP_ALIGN.LEFT)
    # Divider line using a thin rectangle
    s = slide.shapes.add_shape(1, Inches(0.5), Inches(1.0), Inches(12.3), Inches(0.04))
    s.fill.solid(); s.fill.fore_color.rgb = AZUL_M
    s.line.fill.background()


def card(slide, x, y, w, h, icon, title, bullets, bg_color=AZUL_C, text_color=AZUL):
    b = box(slide, x, y, w, h, fill_color=bg_color, line_color=AZUL_M, line_width=Pt(1))
    # Icon + title
    txbox(slide, x + Inches(0.15), y + Inches(0.1), w - Inches(0.3), Inches(0.55),
          f'{icon}  {title}', size=Pt(14), color=text_color, bold=True)
    # Bullets
    tb = slide.shapes.add_textbox(x + Inches(0.15), y + Inches(0.65), w - Inches(0.3), h - Inches(0.75))
    tf = tb.text_frame; tf.word_wrap = True
    for i, b_text in enumerate(bullets):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = f'• {b_text}'
        p.font.size = Pt(11)
        p.font.color.rgb = text_color
        p.font.name = 'Calibri'


def _bullets(slide, x, y, w, h, items, size=Pt(16), gap=Pt(14)):
    """Render a simple emoji-bullet list."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, (emoji, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f'{emoji}  {text}' if emoji else text
        p.font.size = size
        p.font.color.rgb = PptxRGB(0x22, 0x22, 0x22)
        p.font.name = 'Calibri'
        p.space_after = gap


def build_pptx():
    prs = prs_new()

    # ── SLIDE 1 — Capa ────────────────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, AZUL)
    # Bottom accent strip
    strip = box(s, Inches(0), Inches(6.1), W, Inches(1.4), fill_color=PptxRGB(0x16, 0x2D, 0x4F))
    strip.line.fill.background()
    txbox(s, Inches(1), Inches(1.9), Inches(11.3), Inches(1.4),
          'Requisições App', size=Pt(52), color=BRANCO_P, bold=True, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(3.5), Inches(11.3), Inches(0.8),
          'Ferragens Pinheiro', size=Pt(26), color=AZUL_C, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(6.2), Inches(11.3), Inches(0.6),
          'Maio de 2026  |  v1.1.0', size=Pt(14),
          color=PptxRGB(0xAA, 0xBB, 0xCC), align=PP_ALIGN.CENTER)

    # ── SLIDE 2 — Antes: papel ────────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Como era antes: o papel')
    txbox(s, Inches(10.3), Inches(1.8), Inches(2.5), Inches(2.5),
          '📄', size=Pt(90), align=PP_ALIGN.CENTER, color=PptxRGB(0xCC, 0xCC, 0xCC))
    _bullets(s, Inches(0.6), Inches(1.4), Inches(9.4), Inches(5.5), [
        ('→', 'Requisições escritas à mão, sem padronização'),
        ('→', 'Nenhum registro centralizado — cada um guardava o seu'),
        ('→', 'Impossível consultar o histórico de forma rápida'),
        ('→', 'Informações chegavam incompletas ou com atraso às equipes'),
        ('→', 'Erros de transcrição e muito retrabalho'),
    ])

    # ── SLIDE 3 — Evolução: Excel ─────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'A evolução: a planilha Excel')
    txbox(s, Inches(10.3), Inches(1.8), Inches(2.5), Inches(2.5),
          '📊', size=Pt(90), align=PP_ALIGN.CENTER, color=PptxRGB(0xCC, 0xCC, 0xCC))

    txbox(s, Inches(0.6), Inches(1.35), Inches(9.4), Inches(0.5),
          'O que melhorou:', size=Pt(15), color=PptxRGB(0x27, 0xAE, 0x60), bold=True)
    _bullets(s, Inches(0.6), Inches(1.85), Inches(9.4), Inches(1.8), [
        ('✅', 'Requisições digitadas e editáveis'),
        ('✅', 'Fácil duplicar pedidos semelhantes'),
        ('✅', 'Mais fácil corrigir erros'),
    ], size=Pt(15), gap=Pt(8))

    txbox(s, Inches(0.6), Inches(3.75), Inches(9.4), Inches(0.5),
          'O que ainda faltava:', size=Pt(15), color=PptxRGB(0xC0, 0x39, 0x2B), bold=True)
    _bullets(s, Inches(0.6), Inches(4.25), Inches(9.4), Inches(2.8), [
        ('❌', 'Sem rastreamento de status em tempo real'),
        ('❌', 'Produção e indústria sem acesso direto às informações'),
        ('❌', 'Histórico espalhado, difícil de consultar'),
        ('❌', 'Atualizações recorrentes eram inviáveis na planilha'),
    ], size=Pt(15), gap=Pt(8))

    # ── SLIDE 4 — Apresentando o app ──────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, AZUL)
    txbox(s, Inches(1), Inches(1.5), Inches(11.3), Inches(0.8),
          'A solução:', size=Pt(22), color=AZUL_C, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(2.3), Inches(11.3), Inches(1.4),
          'Requisições App', size=Pt(52), color=BRANCO_P, bold=True, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(3.75), Inches(11.3), Inches(0.65),
          'Desenvolvido especialmente para a Ferragens Pinheiro',
          size=Pt(18), color=AZUL_C, align=PP_ALIGN.CENTER)
    # 4 highlights
    highlights = [
        ('🖥️', 'Desktop\nnativo'),
        ('⚡', 'Tempo\nreal'),
        ('🔐', 'Perfis e\npermissões'),
        ('🔄', 'Atualização\nautomática'),
    ]
    for i, (icon, label) in enumerate(highlights):
        cx = Inches(1.1 + i * 2.85)
        pb = box(s, cx, Inches(4.7), Inches(2.5), Inches(2.35), fill_color=PptxRGB(0x16, 0x2D, 0x4F))
        pb.line.fill.background()
        txbox(s, cx, Inches(4.75), Inches(2.5), Inches(0.8),
              icon, size=Pt(30), align=PP_ALIGN.CENTER, color=BRANCO_P)
        txbox(s, cx, Inches(5.55), Inches(2.5), Inches(1.3),
              label, size=Pt(14), align=PP_ALIGN.CENTER, color=AZUL_C, wrap=True)

    # ── SLIDE 5 — Interface e Navegação ──────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Interface e Navegação')
    _bullets(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), [
        ('🏠', 'Tela de login com imagem de fundo personalizável'),
        ('🗂️', 'Barra lateral com acesso rápido a todas as telas do seu perfil'),
        ('🌙', 'Tema claro e escuro, alternável a qualquer momento'),
        ('🔤', 'Tamanho de fonte configurável individualmente'),
        ('🎓', 'Guia Rápido interativo para novos usuários (e revisão quando quiser)'),
        ('📐', 'Interface adaptável a qualquer resolução — de projetores a telas 4K'),
    ])

    # ── SLIDE 6 — Central de Pedidos ─────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Central de Pedidos')

    _bullets(s, Inches(0.6), Inches(1.4), Inches(7.8), Inches(5.5), [
        ('📋', 'Visualização de todas as requisições em tempo real'),
        ('🔍', 'Busca por cliente, CNPJ, número do pedido ou vendedor'),
        ('➕', 'Criação rápida com busca inteligente de clientes'),
        ('📄', 'PDF gerado e enviado automaticamente para a pasta de rede'),
        ('↕️', 'Ordenação por qualquer coluna com um clique'),
    ])

    # Status sidebar
    hb = box(s, Inches(8.8), Inches(1.4), Inches(4.0), Inches(0.55), fill_color=AZUL)
    hb.line.fill.background()
    txbox(s, Inches(8.8), Inches(1.4), Inches(4.0), Inches(0.55),
          'Status dos pedidos', size=Pt(13), color=BRANCO_P, bold=True, align=PP_ALIGN.CENTER)
    status_colors = [
        (PptxRGB(0x41, 0x8B, 0xCA), 'Em andamento'),
        (PptxRGB(0xF3, 0x9C, 0x12), 'Aguardando recebimento'),
        (PptxRGB(0xE6, 0x7E, 0x22), 'Em produção'),
        (PptxRGB(0x27, 0xAE, 0x60), 'Faturado'),
        (PptxRGB(0xE7, 0x4C, 0x3C), 'Cancelada'),
    ]
    for i, (color, label) in enumerate(status_colors):
        cy = Inches(1.95 + i * 0.78)
        sb = box(s, Inches(8.8), cy, Inches(4.0), Inches(0.72),
                 fill_color=AZUL_C if i % 2 == 0 else BRANCO_P)
        sb.line.fill.background()
        dot = box(s, Inches(9.0), cy + Inches(0.18), Inches(0.35), Inches(0.35), fill_color=color)
        dot.line.fill.background()
        txbox(s, Inches(9.45), cy + Inches(0.1), Inches(3.2), Inches(0.52),
              label, size=Pt(12), color=PptxRGB(0x22, 0x22, 0x22))

    # ── SLIDE 7 — Criando uma Requisição ─────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Criando uma Requisição')
    steps_req = [
        ('Clique em  + Nova Requisição  na Central de Pedidos',),
        ('Busque o cliente por nome, código ou CNPJ',),
        ('Preencha o número do pedido e defina se é retirada ou entrega',),
        ('Adicione os itens: produto, quantidade e preço unitário',),
        ('Inclua observações ou um croqui no editor de desenho (opcional)',),
        ('Salve — o PDF é gerado e enviado automaticamente para a rede',),
    ]
    for i, (text,) in enumerate(steps_req):
        cy = Inches(1.4 + i * 0.97)
        circ = s.shapes.add_shape(9, Inches(0.5), cy + Inches(0.1), Inches(0.65), Inches(0.65))
        circ.fill.solid()
        circ.fill.fore_color.rgb = AZUL
        circ.line.fill.background()
        txbox(s, Inches(0.5), cy + Inches(0.1), Inches(0.65), Inches(0.65),
              str(i + 1), size=Pt(15), color=BRANCO_P, bold=True, align=PP_ALIGN.CENTER)
        txbox(s, Inches(1.35), cy + Inches(0.05), Inches(11.5), Inches(0.85),
              text, size=Pt(15), color=PptxRGB(0x22, 0x22, 0x22))

    # ── SLIDE 8 — Editor de Desenho ───────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Editor de Desenho Integrado')
    _bullets(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), [
        ('✏️', 'Croquis e medidas criados diretamente dentro da requisição'),
        ('🛠️', '9 ferramentas: caneta, linha, seta, retângulo, texto, cota MM e mais'),
        ('📏', 'Cota MM calcula e posiciona o rótulo automaticamente, sem sobreposição'),
        ('🔗', 'Snap de extremidades para linhas precisas e bem conectadas'),
        ('⌨️', 'Atalho de teclado para cada ferramenta — P, L, A, R, M...'),
        ('📄', 'O desenho é exportado junto com o PDF da requisição'),
    ])

    # ── SLIDE 9 — Notificações ────────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Notificações em Tempo Real')
    _bullets(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), [
        ('🔔', 'Badge na sidebar indica quantas notificações estão não lidas'),
        ('💬', 'Pop-ups aparecem automaticamente ao surgir um evento'),
        ('📋', 'Painel lateral com histórico completo de notificações'),
        ('⚡', 'Atualizações instantâneas — sem precisar recarregar a tela'),
        ('📡', 'Reconexão automática em caso de queda de rede'),
        ('👤', 'Cada perfil recebe apenas as notificações pertinentes à sua função'),
    ])

    # ── SLIDE 10 — Mais Recursos ──────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Mais Recursos do Sistema')
    _bullets(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), [
        ('📅', 'Histórico — filtre e exporte todas as requisições por data, status ou vendedor'),
        ('⚖️', 'Calculadora de Peso — calcule a massa de perfis metálicos por dimensão'),
        ('🔒', 'Perfis de Acesso — 6 perfis, cada usuário vê e faz apenas o da sua função'),
        ('🔄', 'Atualização Automática — nova versão detectada no startup, instala com um clique'),
        ('🌙', 'Personalização — tema claro/escuro e tamanho de fonte por usuário'),
        ('💾', 'Backup Automático — banco de dados salvo diariamente em pasta de rede'),
    ])

    # ── SLIDE 11 — O que mudou na prática ────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'O que mudou na prática')
    _bullets(s, Inches(0.6), Inches(1.4), Inches(12.1), Inches(5.5), [
        ('✅', 'Rastreabilidade total de cada requisição, do pedido ao faturamento'),
        ('✅', 'Produção e indústria com acesso em tempo real, sem depender de ninguém'),
        ('✅', 'PDFs padronizados, gerados automaticamente e organizados por vendedor'),
        ('✅', 'Histórico completo e pesquisável — anos de pedidos a um clique'),
        ('✅', 'Menos retrabalho, menos erros, menos tempo perdido'),
        ('✅', 'Sistema atualizado automaticamente, sem precisar chamar a TI'),
    ], size=Pt(17), gap=Pt(16))

    # ── SLIDE 12 — Próximos Passos ────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, BRANCO_P)
    content_title(s, 'Próximos Passos')
    roadmap_items = [
        (PptxRGB(0x27, 0xAE, 0x60), '✅  Atual  —  v1.1.0',
         'Guia Rápido · Backup automático · Editor de desenho aprimorado · '
         'Atualização automática · Notificações em tempo real'),
        (PptxRGB(0xF3, 0x9C, 0x12), '🔜  Próxima versão',
         'Melhorias no dashboard · Integração com WhatsApp · '
         'Relatórios exportáveis · Filtros avançados no histórico'),
        (PptxRGB(0x95, 0xA5, 0xA6), '🔮  Futuro',
         'App mobile para visualização · Portal web para clientes · Integração com ERP'),
    ]
    for i, (color, title_r, desc_r) in enumerate(roadmap_items):
        cy = Inches(1.4 + i * 1.6)
        cb = box(s, Inches(0.4), cy, Inches(0.2), Inches(1.4), fill_color=color)
        cb.line.fill.background()
        br = box(s, Inches(0.65), cy, Inches(12.1), Inches(1.4),
                 fill_color=PptxRGB(0xF8, 0xF9, 0xFA) if i % 2 == 0 else BRANCO_P)
        br.line.fill.background()
        txbox(s, Inches(0.85), cy + Inches(0.1), Inches(11.7), Inches(0.48),
              title_r, size=Pt(14), color=color, bold=True)
        txbox(s, Inches(0.85), cy + Inches(0.6), Inches(11.7), Inches(0.7),
              desc_r, size=Pt(12), color=PptxRGB(0x44, 0x44, 0x44), wrap=True)

    txbox(s, Inches(0.4), Inches(6.35), Inches(12.5), Inches(0.7),
          '💬  As próximas melhorias serão guiadas pelo feedback dos usuários — suas sugestões são bem-vindas!',
          size=Pt(13), color=AZUL_M, wrap=True)

    # ── SLIDE 13 — Encerramento ───────────────────────────────────────────────
    s = blank_slide(prs)
    bg(s, AZUL)
    strip2 = box(s, Inches(0), Inches(6.1), W, Inches(1.4), fill_color=PptxRGB(0x16, 0x2D, 0x4F))
    strip2.line.fill.background()
    txbox(s, Inches(1), Inches(2.2), Inches(11.3), Inches(1.4),
          'Obrigado', size=Pt(56), color=BRANCO_P, bold=True, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(3.8), Inches(11.3), Inches(0.7),
          'Requisições App — Ferragens Pinheiro',
          size=Pt(20), color=AZUL_C, align=PP_ALIGN.CENTER)
    txbox(s, Inches(1), Inches(6.2), Inches(11.3), Inches(0.6),
          'Dúvidas e sugestões: fale com a equipe de TI',
          size=Pt(14), color=PptxRGB(0xAA, 0xBB, 0xCC), align=PP_ALIGN.CENTER)

    out = r'C:\Users\João\Desktop\requisicoes\docs\Apresentacao_Requisicoes_App.pptx'
    prs.save(out)
    print(f'PPTX salvo: {out}')


if __name__ == '__main__':
    import sys
    if '--docx' in sys.argv:
        build_docx()
    elif '--pptx' in sys.argv:
        build_pptx()
    else:
        build_docx()
        build_pptx()
    print('Concluído!')
