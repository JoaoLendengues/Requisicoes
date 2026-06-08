from __future__ import annotations

import re
import subprocess
from collections import OrderedDict
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT_DOCX = ROOT / "docs" / "Proposta_Venda_Integral_Requisicoes_App.docx"
SELF_RELATIVE = Path("docs/build_sale_proposal.py")
EXCLUDED_RELATIVE = {
    Path("docs/build_sale_proposal.py"),
    Path("docs/Proposta_Venda_Integral_Requisicoes_App.docx"),
    Path("docs/Proposta_Venda_Integral_Requisicoes_App.pdf"),
}
EXCLUDED_PREFIXES = (
    Path("venv"),
    Path(".git"),
    Path("__pycache__"),
    Path("docs/qa_proposta_venda"),
)

NAVY = RGBColor(0x14, 0x2B, 0x4A)
BLUE = RGBColor(0x2C, 0x5D, 0x8A)
BLUE_LIGHT = RGBColor(0xE9, 0xF1, 0xF7)
GRAY = RGBColor(0x5A, 0x5A, 0x5A)
GRAY_LIGHT = RGBColor(0xF4, 0xF6, 0xF8)
BLACK = RGBColor(0x22, 0x22, 0x22)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2F, 0x6E, 0x4F)
AMBER = RGBColor(0x8A, 0x62, 0x12)
RED = RGBColor(0x9B, 0x2F, 0x2F)


def iter_project_files() -> list[Path]:
    files: list[Path] = []
    excluded_files = {path.as_posix() for path in EXCLUDED_RELATIVE}
    excluded_prefixes = tuple(prefix.as_posix() for prefix in EXCLUDED_PREFIXES)
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        rel_posix = rel.as_posix()
        if rel_posix in excluded_files:
            continue
        if any(part == "__pycache__" for part in rel.parts):
            continue
        if any(
            rel_posix == prefix or rel_posix.startswith(prefix + "/")
            for prefix in excluded_prefixes
        ):
            continue
        files.append(rel)
    return sorted(files)


def git_output(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def count_python_loc(files: list[Path]) -> int:
    total = 0
    for rel in files:
        if rel.suffix.lower() != ".py":
            continue
        try:
            with (ROOT / rel).open("r", encoding="utf-8", errors="ignore", newline=None) as handle:
                total += sum(1 for _ in handle)
        except Exception:
            continue
    return total


def count_regex_matches(paths: list[Path], pattern: str) -> int:
    regex = re.compile(pattern, re.MULTILINE)
    total = 0
    for rel in paths:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        total += len(regex.findall(text))
    return total


def fmt_brl(value: int | float) -> str:
    text = f"{value:,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def set_cell_background(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tc_pr.append(shd)


def set_table_fixed_layout(table) -> None:
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")


def set_cell_width(cell, width_inches: float) -> None:
    width = Inches(width_inches)
    cell.width = width
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(int(width.inches * 1440)))
    tc_w.set(qn("w:type"), "dxa")


def set_cell_margins(cell, *, top=80, bottom=80, left=120, right=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for tag, value in (
        ("top", top),
        ("bottom", bottom),
        ("start", left),
        ("end", right),
    ):
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tbl_header.set(qn("w:val"), "true")
        tr_pr.append(tbl_header)


def add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    fld_char_1 = OxmlElement("w:fldChar")
    fld_char_1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"
    fld_char_2 = OxmlElement("w:fldChar")
    fld_char_2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_1)
    run._r.append(instr_text)
    run._r.append(fld_char_2)


def configure_styles(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.5)
    section.footer_distance = Inches(0.5)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = BLACK
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    normal.paragraph_format.line_spacing = 1.33

    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 12, 6),
        ("Heading 3", 12, NAVY, 8, 4),
    ):
        style = doc.styles[name]
        style.font.name = "Calibri"
        style.font.bold = True
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        style.paragraph_format.line_spacing = 1.15

    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_run = p.add_run("Requisições App | Avaliação para venda integral")
    p_run.font.name = "Calibri"
    p_run.font.size = Pt(9)
    p_run.font.color.rgb = GRAY

    footer = section.footer
    f = footer.paragraphs[0]
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label = f.add_run("Página ")
    label.font.name = "Calibri"
    label.font.size = Pt(9)
    label.font.color.rgb = GRAY
    add_page_number(f)


def add_title_paragraph(doc: Document, text: str, *, size: int, color: RGBColor, bold=True, after=0, align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.bold = bold


def add_body(doc: Document, text: str, *, bold_label: str | None = None) -> None:
    p = doc.add_paragraph()
    if bold_label:
        label_run = p.add_run(bold_label)
        label_run.bold = True
        label_run.font.name = "Calibri"
        label_run.font.size = Pt(11)
        label_run.font.color.rgb = BLACK
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.color.rgb = BLACK


def add_bullet(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(11)


def add_number(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(11)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"
    table.autofit = False
    set_table_fixed_layout(table)

    header_row = table.rows[0]
    set_repeat_table_header(header_row)
    for idx, header in enumerate(headers):
        cell = header_row.cells[idx]
        set_cell_width(cell, widths[idx])
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(header)
        run.bold = True
        run.font.name = "Calibri"
        run.font.size = Pt(10)
        run.font.color.rgb = WHITE
        set_cell_background(cell, "2C5D8A")

    for row_index, data in enumerate(rows):
        row = table.add_row()
        for col_index, value in enumerate(data):
            cell = row.cells[col_index]
            set_cell_width(cell, widths[col_index])
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            run = paragraph.add_run(value)
            run.font.name = "Calibri"
            run.font.size = Pt(10)
            run.font.color.rgb = BLACK
            set_cell_background(cell, "F4F6F8" if row_index % 2 == 0 else "FFFFFF")

    doc.add_paragraph()


def add_callout(doc: Document, title: str, text: str, fill_hex: str = "E9F1F7") -> None:
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"
    table.autofit = False
    set_table_fixed_layout(table)
    cell = table.cell(0, 0)
    set_cell_width(cell, 6.5)
    set_cell_margins(cell, top=110, bottom=110, left=140, right=140)
    set_cell_background(cell, fill_hex)
    cell.text = ""

    p1 = cell.paragraphs[0]
    p1.paragraph_format.space_after = Pt(4)
    r1 = p1.add_run(title)
    r1.bold = True
    r1.font.name = "Calibri"
    r1.font.size = Pt(11)
    r1.font.color.rgb = NAVY

    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    r2 = p2.add_run(text)
    r2.font.name = "Calibri"
    r2.font.size = Pt(10.5)
    r2.font.color.rgb = BLACK

    doc.add_paragraph()


def collect_inventory() -> OrderedDict[str, list[str]]:
    groups: OrderedDict[str, list[str]] = OrderedDict()
    excluded_files = {path.as_posix() for path in EXCLUDED_RELATIVE}

    def names_in(path: Path, *, include_hidden=True) -> list[str]:
        if not path.exists():
            return []
        items: list[str] = []
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            if child.name == "__pycache__":
                continue
            if child.is_dir():
                continue
            rel = child.relative_to(ROOT)
            if rel.as_posix() in excluded_files:
                continue
            if not include_hidden and child.name.startswith("."):
                continue
            items.append(child.name)
        return items

    groups["Raiz do projeto"] = names_in(ROOT)
    groups["GitHub workflow"] = ["build_release.yml"] if (ROOT / ".github" / "workflows" / "build_release.yml").exists() else []
    groups["client/api"] = names_in(ROOT / "client" / "api")
    groups["client/core"] = names_in(ROOT / "client" / "core")
    groups["client/services"] = names_in(ROOT / "client" / "services")
    groups["client/views"] = names_in(ROOT / "client" / "views")
    groups["client/widgets"] = names_in(ROOT / "client" / "widgets")
    groups["server"] = names_in(ROOT / "server")
    groups["server/models"] = names_in(ROOT / "server" / "models")
    groups["server/routers"] = names_in(ROOT / "server" / "routers")
    groups["server/schemas"] = names_in(ROOT / "server" / "schemas")
    groups["server/services"] = names_in(ROOT / "server" / "services")
    groups["tests"] = names_in(ROOT / "tests")
    groups["docs"] = names_in(ROOT / "docs")

    asset_root = ROOT / "client" / "assets"
    for subdir in sorted((d for d in asset_root.iterdir() if d.is_dir()), key=lambda p: p.name.lower()):
        if subdir.name == "__pycache__":
            continue
        asset_files = []
        for asset in sorted(subdir.rglob("*"), key=lambda p: p.as_posix().lower()):
            if not asset.is_file():
                continue
            rel = asset.relative_to(asset_root)
            if rel.name == "_state.json":
                continue
            asset_files.append(str(rel).replace("\\", "/"))
        groups[f"client/assets/{subdir.name}"] = asset_files

    standalone_assets = [f.name for f in sorted(asset_root.iterdir(), key=lambda p: p.name.lower()) if f.is_file()]
    groups["client/assets (arquivos soltos)"] = standalone_assets
    return groups


def build_metrics(files: list[Path]) -> OrderedDict[str, str]:
    python_files = [f for f in files if f.suffix.lower() == ".py"]
    server_router_files = [f for f in files if f.as_posix().startswith("server/routers/") and f.suffix.lower() == ".py"]
    server_model_files = [f for f in files if f.as_posix().startswith("server/models/") and f.suffix.lower() == ".py"]
    client_view_files = [
        f for f in files
        if f.as_posix().startswith("client/views/")
        and f.suffix.lower() == ".py"
        and f.name != "__init__.py"
    ]
    test_files = [
        f for f in files
        if f.as_posix().startswith("tests/")
        and f.suffix.lower() == ".py"
        and f.name != "__init__.py"
    ]
    asset_files = [
        f for f in files
        if f.as_posix().startswith("client/assets/")
        and f.name != "_state.json"
    ]
    doc_files = [f for f in files if f.as_posix().startswith("docs/")]

    tags = [tag for tag in git_output("tag", "--list").splitlines() if tag.strip()]
    commits = git_output("rev-list", "--count", "HEAD") or "n/d"

    metrics = OrderedDict()
    metrics["Arquivos totais do repositório avaliado"] = str(len(files))
    metrics["Arquivos Python"] = str(len(python_files))
    # Medido em auditoria local com PowerShell para evitar distorções de
    # quebra de linha causadas por arquivos CRLF muito grandes.
    metrics["Linhas aproximadas de Python"] = "50.342"
    metrics["Commits no histórico Git"] = commits
    metrics["Tags de versão encontradas"] = ", ".join(tags) if tags else "n/d"
    metrics["Telas/arquivos de views no cliente"] = str(len(client_view_files))
    metrics["Endpoints FastAPI mapeados"] = str(count_regex_matches(server_router_files, r"@router\.(?:get|post|put|patch|delete)"))
    metrics["Modelos ORM identificados"] = str(count_regex_matches(server_model_files, r"^class\s+\w+\(Base\):"))
    metrics["Arquivos de teste"] = str(len(test_files))
    metrics["Arquivos de documentação"] = str(len(doc_files))
    metrics["Ativos visuais empacotados"] = str(len(asset_files))
    return metrics


def add_cover(doc: Document) -> None:
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(95)

    add_title_paragraph(doc, "PROPOSTA DE VENDA INTEGRAL", size=14, color=GRAY, after=8)
    add_title_paragraph(doc, "Requisições App", size=28, color=NAVY, after=6)
    add_title_paragraph(doc, "Avaliação financeira para cessão patrimonial de 100% do ativo", size=14, color=BLUE, bold=False, after=20)
    add_title_paragraph(doc, "Código-fonte, documentação, scripts de build, instalador e artefatos correlatos", size=11, color=GRAY, bold=False, after=28)

    meta = doc.add_table(rows=4, cols=2)
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta.style = "Table Grid"
    meta.autofit = False
    set_table_fixed_layout(meta)
    rows = [
        ("Data da avaliação", date.today().strftime("%d/%m/%Y")),
        ("Modelo avaliado", "Venda exclusiva / cessão patrimonial integral"),
        ("Escopo", "Ativo de software sem retenção de propriedade pelo vendedor"),
        ("Observação", "Avaliação baseada no repositório local e nos artefatos presentes no workspace"),
    ]
    for row_idx, (left, right) in enumerate(rows):
        for col_idx, text in enumerate((left, right)):
            cell = meta.rows[row_idx].cells[col_idx]
            set_cell_width(cell, 2.05 if col_idx == 0 else 4.45)
            set_cell_margins(cell)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(10.5)
            run.bold = col_idx == 0
            run.font.color.rgb = NAVY if col_idx == 0 else BLACK
            set_cell_background(cell, "E9F1F7" if col_idx == 0 else "FFFFFF")
    doc.add_page_break()


def add_summary_section(doc: Document, metrics: OrderedDict[str, str]) -> None:
    doc.add_heading("1. Resumo executivo", level=1)
    add_body(
        doc,
        "A análise do repositório indica que o Requisições App é um ativo de software maduro, "
        "com cliente desktop em PySide6, API em FastAPI, banco PostgreSQL, automações de backup, "
        "sistema de atualização, documentação técnica, testes e pipeline de release para Windows."
    )
    add_body(
        doc,
        "Para uma venda integral, sem manutenção de titularidade pelo vendedor, o ativo deve ser "
        "precificado acima de uma simples licença de uso, porque a negociação transfere o valor do "
        "código autoral, da lógica de negócio incorporada, do histórico evolutivo e do potencial de reuso futuro."
    )
    add_callout(
        doc,
        "Recomendação objetiva",
        "Ofertar a venda integral por R$ 168.000,00, trabalhar para fechar entre R$ 145.000,00 e "
        "R$ 160.000,00, e evitar descer abaixo de R$ 125.000,00 salvo necessidade de liquidação rápida.",
    )

    doc.add_heading("2. Métricas do ativo analisado", level=1)
    metric_rows = [[key, value] for key, value in metrics.items()]
    add_table(doc, ["Indicador", "Valor"], metric_rows, [4.5, 2.0])


def add_scope_section(doc: Document) -> None:
    doc.add_heading("3. Escopo da venda de 100%", level=1)
    add_body(doc, "Esta proposta considera a cessão patrimonial integral do ativo de software em seu estado atual, incluindo:")
    included = [
        "código-fonte do cliente desktop, do servidor FastAPI e dos módulos auxiliares",
        "modelagem de banco, schemas, regras de negócio, testes, scripts de seed e migração",
        "documentação técnica, manual de usuário, notas de release e scripts de geração documental",
        "scripts de empacotamento com PyInstaller, instalador Inno Setup e workflow de release do GitHub",
        "ativos visuais do projeto, fontes empacotadas, ícones, imagens e arquivos auxiliares do produto",
        "direito de alterar, empacotar, instalar e evoluir o software sem retenção de propriedade pelo vendedor",
    ]
    for item in included:
        add_bullet(doc, item)

    add_body(doc, "Itens que normalmente ficam fora da cessão, salvo cláusula contratual expressa:")
    excluded = [
        "licenças proprietárias de terceiros e titularidade de bibliotecas open source, que permanecem sob suas licenças originais",
        "dados reais de produção, credenciais, contas externas, hardware e infraestrutura física",
        "suporte continuado, manutenção evolutiva e operação assistida por prazo indeterminado",
    ]
    for item in excluded:
        add_bullet(doc, item)


def add_system_inventory_section(doc: Document, inventory: OrderedDict[str, list[str]]) -> None:
    doc.add_heading("4. O que existe no sistema hoje", level=1)
    add_body(
        doc,
        "Abaixo está o inventário consolidado do ativo encontrado no repositório. A pasta local `venv/` não foi considerada "
        "na avaliação econômica por ser ambiente reproduzível e não ativo autoral essencial."
    )

    doc.add_heading("4.1 Componentes funcionais e de negócio", level=2)
    feature_groups = [
        "login, primeiro acesso, troca de senha e controle de sessão por perfil",
        "central de pedidos, formulário de requisição, histórico, entregas, produção e dashboard gerencial",
        "editor gráfico/canvas com linhas, formas, cotas, texto, imagens e persistência no banco",
        "geração automática de PDF com QR code, assinatura, renderização do desenho e roteamento por pasta",
        "notificações em tempo real via SSE, painel lateral, badge e toasts no cliente",
        "cadastros e importação em lote de usuários, clientes, produtos, operadores e máquinas",
        "backup automatizado com retenção diária, semanal e mensal, mais cópia das configurações operacionais",
        "auto-update do executável via GitHub Releases, helper externo e mecanismo de rollback",
        "painel técnico, métricas de runtime, cache em memória e scheduler de alertas operacionais",
        "módulo de feedback com status, publicação, reações e contagem de não lidos",
    ]
    for item in feature_groups:
        add_bullet(doc, item)

    doc.add_heading("4.2 Inventário por diretório", level=2)
    for group, names in inventory.items():
        if not names:
            continue
        title = f"{group} ({len(names)})"
        doc.add_heading(title, level=3)
        add_body(doc, ", ".join(names))


def add_valuation_section(doc: Document) -> None:
    doc.add_heading("5. Metodologia de valuation", level=1)
    add_body(
        doc,
        "Como não há dados de faturamento recorrente anexados ao repositório, a avaliação foi baseada principalmente em "
        "custo de reposição, complexidade funcional, maturidade dos artefatos e desconto de mercado por se tratar de uma solução vertical e interna."
    )

    effort_rows = [
        ["Arquitetura, API, autenticação, banco e permissões", "280 a 360 h"],
        ["Cliente desktop, navegação, UX e telas operacionais", "420 a 560 h"],
        ["Regras de negócio de requisições, produção e entregas", "320 a 420 h"],
        ["Canvas, PDF, notificações, updater e backup", "240 a 320 h"],
        ["Empacotamento, CI/CD, testes, documentação e polimento", "180 a 260 h"],
        ["Esforço total estimado de reposição", "1.440 a 1.920 h"],
    ]
    add_table(doc, ["Bloco de esforço", "Faixa estimada"], effort_rows, [4.7, 1.8])

    financial_rows = [
        ["Faixa horária de referência", fmt_brl(110), fmt_brl(150)],
        ["Custo bruto de reposição", fmt_brl(158400), fmt_brl(288000)],
        ["Faixa ajustada para venda de ativo", fmt_brl(135000), fmt_brl(165000)],
    ]
    add_table(doc, ["Critério", "Base conservadora", "Base alta"], financial_rows, [3.4, 1.55, 1.55])

    add_body(doc, "Ajustes aplicados sobre o custo bruto:")
    adjustments = [
        "desconto por aderência específica ao fluxo de uma operação industrial/comercial interna, o que reduz o universo de compradores",
        "prêmio por cessão patrimonial total, já que o vendedor deixará de reutilizar economicamente o ativo",
        "prêmio por existência de documentação, testes, instalador e pipeline de release, que diminuem custo de assimilação para o comprador",
    ]
    for item in adjustments:
        add_bullet(doc, item)

    add_callout(
        doc,
        "Leitura prática da faixa",
        "A banda de R$ 135 mil a R$ 165 mil é a faixa mais equilibrada para uma venda séria. "
        "Abaixo disso o ativo começa a ficar barato diante do custo de reconstrução; acima de R$ 179 mil a venda depende "
        "de um comprador que enxergue valor estratégico muito alto no processo já pronto.",
    )


def add_price_strategy_section(doc: Document) -> None:
    doc.add_heading("6. Estratégia de preço recomendada", level=1)
    price_rows = [
        ["Liquidação rápida", fmt_brl(115000), "para fechamento veloz e baixo tempo de transição"],
        ["Piso técnico de negociação", fmt_brl(125000), "não recomendado aceitar abaixo disso sem urgência real"],
        ["Faixa justa de fechamento", f"{fmt_brl(145000)} a {fmt_brl(160000)}", "faixa mais defensável para comprador e vendedor"],
        ["Preço de oferta inicial", fmt_brl(168000), "melhor ponto de abertura para negociação"],
        ["Âncora agressiva", fmt_brl(179000), "válida se o comprador enxergar alto valor estratégico"],
    ]
    add_table(doc, ["Cenário", "Valor", "Leitura"], price_rows, [2.1, 1.7, 2.7])

    add_body(
        doc,
        "Minha recomendação é abrir a conversa em R$ 168.000,00, sustentar a negociação pelo ganho de tempo e pelo custo evitado de reconstrução, "
        "e buscar fechamento acima de R$ 145.000,00."
    )

    doc.add_heading("7. Condições comerciais sugeridas", level=1)
    terms = [
        "objeto: cessão patrimonial integral do software, sem retenção de propriedade pelo vendedor",
        "pagamento sugerido: 60% na assinatura e 40% na entrega formal do pacote e repasse técnico",
        "janela de transição incluída: até 20 horas remotas em até 30 dias corridos após a assinatura",
        "suporte posterior: não incluído; qualquer demanda futura deve ser contratada à parte, se houver interesse do vendedor",
        "validade sugerida da proposta: 15 dias",
    ]
    for item in terms:
        add_bullet(doc, item)


def add_due_diligence_section(doc: Document) -> None:
    doc.add_heading("8. Pontos de due diligence antes de vender", level=1)
    add_body(doc, "Antes de encaminhar esta proposta ao comprador, recomendo fechar estes pontos:")
    checks = [
        "formalizar a cadeia de titularidade com todos os contribuidores relevantes do projeto, se houver mais de um autor com participação material",
        "sanitizar o repositório para remover ou rotacionar credenciais, chaves, URLs internas, e dados sensíveis antes da abertura para terceiros",
        "definir se a marca, o nome do sistema, o histórico do repositório Git e os releases do GitHub serão efetivamente transferidos ou apenas exportados",
        "separar claramente o que é código autoral próprio do que é dependência open source de terceiros",
    ]
    for item in checks:
        add_bullet(doc, item)

    add_callout(
        doc,
        "Observação relevante",
        "O valor econômico da cessão melhora quando o comprador recebe o pacote limpo, documentado e juridicamente regularizado. "
        "Essa preparação reduz fricção, diminui pedidos de desconto e acelera o fechamento.",
        fill_hex="F8F4E8",
    )


def add_final_recommendation(doc: Document) -> None:
    doc.add_heading("9. Conclusão", level=1)
    add_body(
        doc,
        "Considerando o volume de código, o número de módulos, a existência de instalador, pipeline de release, documentação, "
        "testes e regras de negócio já consolidadas, o Requisições App deve ser tratado como um ativo completo e não como um projeto embrionário."
    )
    add_body(
        doc,
        "Para venda integral, exclusiva e sem intenção de permanência do vendedor no projeto, a proposta mais equilibrada é "
        "apresentar o ativo por R$ 168.000,00, aceitar negociação na faixa de R$ 145.000,00 a R$ 160.000,00 e preservar "
        "R$ 125.000,00 como piso técnico mínimo."
    )


def build_document() -> Path:
    files = iter_project_files()
    metrics = build_metrics(files)
    inventory = collect_inventory()

    doc = Document()
    configure_styles(doc)
    add_cover(doc)
    add_summary_section(doc, metrics)
    add_scope_section(doc)
    add_system_inventory_section(doc, inventory)
    add_valuation_section(doc)
    add_price_strategy_section(doc)
    add_due_diligence_section(doc)
    add_final_recommendation(doc)
    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    return OUT_DOCX


if __name__ == "__main__":
    out = build_document()
    print(out)
