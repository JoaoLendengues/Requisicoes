from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent


TITLE_COLOR = colors.HexColor("#17324D")
ACCENT_COLOR = colors.HexColor("#2E6DA4")
LIGHT_BG = colors.HexColor("#EEF4F9")
TEXT_COLOR = colors.HexColor("#222222")
BORDER_COLOR = colors.HexColor("#C7D5E2")


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ProposalTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=TITLE_COLOR,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ProposalSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=ACCENT_COLOR,
            alignment=TA_CENTER,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=TITLE_COLOR,
            spaceBefore=8,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyTextJustify",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=TEXT_COLOR,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallNote",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#555555"),
            spaceAfter=6,
        )
    )
    return styles


STYLES = build_styles()


COMMON_SCOPE = [
    "Central de pedidos e gestão de requisições.",
    "Cadastro e busca de clientes.",
    "Cadastro e gestão de usuários com perfis de acesso.",
    "Histórico de requisições com filtros e exportações.",
    "Editor de desenho/croqui vinculado à requisição.",
    "Geração automática de PDF.",
    "Notificações em tempo real.",
    "Backup automatizado do banco.",
    "Instalador e processo de atualização da aplicação.",
    "Documentação técnica e manual do usuário já existentes.",
]

EXCLUDED_SCOPE = [
    "Novas funcionalidades não previstas na versão atual.",
    "Integrações externas adicionais.",
    "Manutenção evolutiva ilimitada.",
    "Hospedagem em nuvem de terceiros.",
    "Suporte fora da janela comercial acordada.",
]

COMMON_CONDITIONS = [
    "Validade da proposta: 15 dias.",
    "Forma de pagamento da implantação: 40% na assinatura, 40% na disponibilização para homologação e 20% na entrada em produção.",
    "Prazos estimados: 10 a 20 dias úteis para implantação inicial e 1 a 2 dias para treinamento.",
    "Tributos e retenções legais serão tratados conforme o regime fiscal da contratada.",
]

LEGAL_BASIS = [
    "<b>Lei nº 9.609/1998 (Lei do Software)</b>: arts. 2º, 3º, 4º e 9º, especialmente para proteção do programa, titularidade e necessidade de contrato de licença.",
    "<b>Lei nº 9.610/1998 (Direitos Autorais)</b>: aplicação complementar para exploração econômica e cessão escrita dos direitos patrimoniais.",
    "<b>Lei nº 10.406/2002 (Código Civil)</b>: arts. 421, 422, 425 e 427, para função social do contrato, boa-fé, contratos atípicos e força vinculante da proposta.",
    "<b>Lei nº 13.709/2018 (LGPD)</b>: definição de controlador e operador, base legal para tratamento, medidas de segurança e resposta a incidentes.",
    "<b>Lei nº 12.965/2014 (Marco Civil da Internet)</b>: disciplina complementar sobre registros, segurança e uso de aplicações conectadas.",
]

CONTRACT_CLAUSES = [
    "Identificação completa das partes.",
    "Descrição objetiva do sistema e da versão contratada.",
    "Definição expressa entre licença ou cessão.",
    "Preço, forma de pagamento e marco de aceite.",
    "Escopo do suporte e do que fica fora dele.",
    "Confidencialidade e proteção de dados pessoais.",
    "Responsabilidade por ambiente, infraestrutura, backup e credenciais.",
    "Regras para customizações futuras e cobrança de evolutivas.",
    "Tratamento de componentes de terceiros e bibliotecas open source.",
    "Eleição de foro.",
]

OWNERSHIP_ALERT = (
    "Antes da assinatura, recomenda-se validar a cadeia de titularidade do software. "
    "Se o sistema foi desenvolvido dentro de vínculo empregatício, contrato de prestação de serviços, "
    "ou com recursos e atribuições diretamente ligados ao contratante, o art. 4º da Lei nº 9.609/1998 "
    "pode afetar a titularidade dos direitos patrimoniais."
)


PROPOSALS = [
    {
        "filename": "proposta-licenca-de-uso-requisicoes-app.pdf",
        "mode_name": "Licença de Uso + Implantação",
        "summary": (
            "Modelo recomendado quando o desenvolvedor deseja manter a titularidade do código-fonte "
            "e conceder à contratante licença de uso perpétua, não exclusiva, para operação interna do sistema."
        ),
        "table_rows": [
            ["1", "Licença de uso perpétua, não exclusiva, da versão atual do sistema para uso interno.", "R$ 42.000,00"],
            ["2", "Implantação, parametrização, publicação em ambiente do cliente e validação operacional inicial.", "R$ 8.000,00"],
            ["3", "Treinamento de usuários-chave, repasse operacional e apoio de entrada em produção.", "R$ 6.000,00"],
            ["4", "Garantia de correções por 90 dias para falhas da versão entregue.", "Incluso"],
        ],
        "total_label": "Total da implantação inicial",
        "total_value": "R$ 56.000,00",
        "extra_notes": [
            "Suporte mensal opcional: R$ 2.200,00/mês, com até 12 horas de atendimento remoto.",
            "Hora adicional para demandas excedentes ou evolutivas: R$ 180,00/hora.",
            "A formalização jurídica recomendada é por contrato de licença de uso, com cláusulas de suporte, confidencialidade e LGPD.",
        ],
    },
    {
        "filename": "proposta-cessao-patrimonial-requisicoes-app.pdf",
        "mode_name": "Cessão Patrimonial do Software",
        "summary": (
            "Modelo indicado quando a negociação exigir transferência dos direitos patrimoniais "
            "do software, com cessão contratual do ativo intelectual da versão atual à contratante."
        ),
        "table_rows": [
            ["1", "Cessão patrimonial do código-fonte, artefatos de build, instalador e documentação da versão atual.", "R$ 95.000,00"],
            ["2", "Implantação, parametrização, publicação em ambiente do cliente e validação operacional inicial.", "R$ 8.000,00"],
            ["3", "Treinamento de usuários-chave, repasse operacional e apoio de entrada em produção.", "R$ 6.000,00"],
            ["4", "Garantia de correções por 90 dias para falhas da versão entregue.", "Incluso"],
        ],
        "total_label": "Total da cessão + implantação",
        "total_value": "R$ 109.000,00",
        "extra_notes": [
            "O valor é superior ao da licença porque envolve alienação do ativo intelectual e restrição de reuso econômico futuro pelo desenvolvedor.",
            "A cessão deve ser expressa, escrita e juridicamente compatível com a cadeia de titularidade do software.",
            "Mesmo com cessão, componentes open source permanecem sujeitos às respectivas licenças de terceiros.",
        ],
    },
]


def make_bullets(items):
    return ListFlowable(
        [
            ListItem(
                Paragraph(item, STYLES["BodyTextJustify"]),
                leftIndent=8,
            )
            for item in items
        ],
        bulletType="bullet",
        start="circle",
        leftIndent=14,
        bulletFontName="Helvetica",
        bulletFontSize=8,
        bulletColor=ACCENT_COLOR,
        spaceBefore=2,
        spaceAfter=6,
    )


def make_money_table(rows):
    table = Table(
        [["Item", "Descrição", "Valor"], *rows],
        colWidths=[14 * mm, 123 * mm, 38 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TITLE_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ]
        )
    )
    return table


def make_total_box(label, value):
    table = Table(
        [[label, value]],
        colWidths=[140 * mm, 35 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDER_COLOR),
                ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, -1), TITLE_COLOR),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def add_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(ACCENT_COLOR)
    canvas.drawString(doc.leftMargin, A4[1] - 18 * mm, "Requisições App - Proposta Comercial e Jurídica")
    canvas.drawRightString(
        A4[0] - doc.rightMargin,
        12 * mm,
        f"Página {doc.page}",
    )
    canvas.restoreState()


def build_story(config):
    story = []
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Proposta Comercial e Jurídica", STYLES["ProposalTitle"]))
    story.append(Paragraph("Requisições App - Ferragens Pinheiro", STYLES["ProposalSubtitle"]))
    story.append(Paragraph(config["mode_name"], STYLES["SectionTitle"]))
    story.append(Paragraph(config["summary"], STYLES["BodyTextJustify"]))

    story.append(Paragraph("1. Objeto", STYLES["SectionTitle"]))
    story.append(
        Paragraph(
            "Formalização comercial do sistema interno Requisições App, composto por aplicação desktop, "
            "API FastAPI e banco PostgreSQL, com rotinas de geração de PDF, notificações em tempo real, "
            "controle de acesso, backup e atualização automatizada.",
            STYLES["BodyTextJustify"],
        )
    )

    story.append(Paragraph("2. Escopo contemplado", STYLES["SectionTitle"]))
    story.append(make_bullets(COMMON_SCOPE))
    story.append(Paragraph("Itens não incluídos nesta proposta:", STYLES["BodyTextJustify"]))
    story.append(make_bullets(EXCLUDED_SCOPE))

    story.append(Paragraph("3. Composição comercial", STYLES["SectionTitle"]))
    story.append(make_money_table(config["table_rows"]))
    story.append(Spacer(1, 5 * mm))
    story.append(make_total_box(config["total_label"], config["total_value"]))
    story.append(Spacer(1, 4 * mm))
    story.append(make_bullets(config["extra_notes"]))

    story.append(Paragraph("4. Condições comerciais", STYLES["SectionTitle"]))
    story.append(make_bullets(COMMON_CONDITIONS))

    story.append(PageBreak())

    story.append(Paragraph("5. Bases legais principais", STYLES["SectionTitle"]))
    story.append(make_bullets(LEGAL_BASIS))

    story.append(Paragraph("6. Cláusulas contratuais recomendadas", STYLES["SectionTitle"]))
    story.append(make_bullets(CONTRACT_CLAUSES))

    story.append(Paragraph("7. Alerta de titularidade", STYLES["SectionTitle"]))
    story.append(Paragraph(OWNERSHIP_ALERT, STYLES["BodyTextJustify"]))

    story.append(Paragraph("8. Observação sobre componentes de terceiros", STYLES["SectionTitle"]))
    story.append(
        Paragraph(
            "Dependências e bibliotecas open source utilizadas no projeto continuam sujeitas às respectivas "
            "licenças de terceiros. A licença ou cessão tratada nesta proposta deve recair sobre o código "
            "autoral próprio, regras de negócio, documentação própria, instaladores e artefatos autorais do projeto.",
            STYLES["BodyTextJustify"],
        )
    )

    story.append(Paragraph("9. Fontes legais consultadas", STYLES["SectionTitle"]))
    sources = [
        "Lei do Software - Lei nº 9.609/1998: https://planalto.gov.br/ccivil_03/leis/l9609.htm",
        "Lei de Direitos Autorais - Lei nº 9.610/1998: https://www.planalto.gov.br/ccivil_03/leis/l9610.htm",
        "Código Civil - Lei nº 10.406/2002: https://www.planalto.gov.br/ccivil_03/LEIS/2002/L10406compilada.htm",
        "LGPD - Lei nº 13.709/2018: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
        "Marco Civil da Internet - Lei nº 12.965/2014: https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm",
    ]
    story.append(make_bullets(sources))

    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "Documento gerado em 28/05/2026 a partir da proposta comercial do projeto Requisições App.",
            STYLES["SmallNote"],
        )
    )
    return story


def build_pdf(config):
    output_path = ROOT / config["filename"]
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
        title=f"Proposta - {config['mode_name']}",
        author="OpenAI Codex",
    )
    doc.build(
        build_story(config),
        onFirstPage=add_header_footer,
        onLaterPages=add_header_footer,
    )
    return output_path


def main():
    generated = [build_pdf(config) for config in PROPOSALS]
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
