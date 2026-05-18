"""
Gerador de PDF para requisições de obras — orientação PAISAGEM.
Requer: pip install reportlab>=4.0.0
"""
import io
import json
import os
import re
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, KeepTogether,
        Image as RLImage, PageBreak,
    )
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

if HAS_REPORTLAB:
    C_HEADER   = colors.HexColor("#0F2044")
    C_PRIMARY  = colors.HexColor("#1D4ED8")
    C_LIGHT_BG = colors.HexColor("#EFF6FF")
    C_GRAY_BG  = colors.HexColor("#F1F5F9")
    C_BORDER   = colors.HexColor("#CBD5E1")
    C_TEXT     = colors.HexColor("#1E293B")
    C_TEXT_MID = colors.HexColor("#475569")
    C_WHITE    = colors.white


# ── Formatação de números ─────────────────────────────────────────────────────

def _clean_filename(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', s).strip()[:80]


def _fmt_qty(v) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def _fmt_kg(v) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


# ── Renderização offscreen do canvas ─────────────────────────────────────────

def _build_canvas_item(d: dict):
    """Reconstrói um QGraphicsItem a partir de um dicionário serializado."""
    try:
        from PySide6.QtWidgets import (
            QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem,
            QGraphicsPathItem, QGraphicsTextItem, QGraphicsPixmapItem,
        )
        from PySide6.QtGui import QPen, QColor, QPainterPath, QFont, QPixmap
        from PySide6.QtCore import Qt, QPointF

        t     = d.get("type")
        pen_d = d.get("pen", {})
        pen   = QPen(QColor(pen_d.get("color", "#000000")), pen_d.get("width", 2))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        if t == "line":
            item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
            item.setPen(pen)
            return item
        if t == "rect":
            item = QGraphicsRectItem(d["x"], d["y"], d["w"], d["h"])
            item.setPen(pen)
            return item
        if t == "ellipse":
            item = QGraphicsEllipseItem(d["x"], d["y"], d["w"], d["h"])
            item.setPen(pen)
            return item
        if t == "path":
            path = QPainterPath()
            pts  = d.get("points", [])
            if pts:
                path.moveTo(QPointF(pts[0][0], pts[0][1]))
                for pt in pts[1:]:
                    path.lineTo(QPointF(pt[0], pt[1]))
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            return item
        if t == "text":
            item = QGraphicsTextItem(d.get("text", ""))
            item.setPos(QPointF(d.get("x", 0), d.get("y", 0)))
            item.setDefaultTextColor(QColor(d.get("color", "#000000")))
            item.setFont(QFont("Segoe UI", d.get("font_size", 12)))
            return item
        if t == "image":
            path = d.get("path", "")
            if path and os.path.exists(path):
                pix  = QPixmap(path)
                item = QGraphicsPixmapItem(pix)
                item.setPos(QPointF(d.get("x", 0), d.get("y", 0)))
                return item
    except Exception:
        pass
    return None


def _render_canvas_to_png(canvas_json: str,
                           max_w: int = 2400) -> tuple[bytes, int, int] | None:
    """
    Renderiza o canvas JSON num QGraphicsScene offscreen e retorna PNG.
    Retorna (bytes_png, largura_px, altura_px) ou None se vazio/erro.
    """
    try:
        from PySide6.QtWidgets import QGraphicsScene
        from PySide6.QtGui  import QImage, QPainter, QBrush, QColor
        from PySide6.QtCore import QRectF, QBuffer, QByteArray

        obj        = json.loads(canvas_json or "{}")
        items_data = obj.get("items", [])
        if not items_data:
            return None

        scene = QGraphicsScene()
        scene.setBackgroundBrush(QBrush(QColor("#ffffff")))

        for d in items_data:
            item = _build_canvas_item(d)
            if item:
                scene.addItem(item)

        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty() or bounds.width() <= 0:
            return None

        bounds = bounds.adjusted(-30, -30, 30, 30)   # margem interna

        scale = min(1.0, max_w / bounds.width())
        img_w = max(1, int(bounds.width()  * scale))
        img_h = max(1, int(bounds.height() * scale))

        img = QImage(img_w, img_h, QImage.Format.Format_RGB32)
        img.fill(0xFFFFFF)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, img_w, img_h), bounds)
        painter.end()

        ba  = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        return bytes(ba), img_w, img_h

    except Exception:
        return None


# ── Geração do PDF ────────────────────────────────────────────────────────────

def generate_pdf(req: dict, client: dict | None, obs: str,
                 folder: str, canvas_json: str = "{}") -> str:
    """
    Gera o PDF da requisição em orientação paisagem e salva na pasta especificada.
    Página 1: dados do formulário.
    Página 2 (se houver desenho): canvas técnico em tamanho máximo.
    Retorna o caminho completo do arquivo gerado.
    """
    if not HAS_REPORTLAB:
        raise ImportError(
            "reportlab não instalado. Execute: pip install reportlab>=4.0.0"
        )

    os.makedirs(folder, exist_ok=True)

    ped      = str(req.get("ped_number", "0")).zfill(6)
    c_name   = (client or {}).get("name", "") or f"ID{req.get('client_id', '')}"
    date_str = datetime.now().strftime("%Y%m%d")
    filename = _clean_filename(f"REQ-{ped}-{date_str}-{c_name}") + ".pdf"
    filepath = os.path.join(folder, filename)

    # ── Dimensões (paisagem A4) ───────────────────────────────────────────────
    PAGE_W, PAGE_H = landscape(A4)   # ≈ 841 × 595 pt
    MARGIN  = 18 * mm                # 18 mm em cada lado
    MARGIN_V = 14 * mm
    doc = SimpleDocTemplate(
        filepath, pagesize=landscape(A4),
        leftMargin=MARGIN,  rightMargin=MARGIN,
        topMargin=MARGIN_V, bottomMargin=MARGIN_V,
        title=f"Requisição #{ped} — Ferragens Pinheiro",
        author="Ferragens Pinheiro",
    )
    CW = PAGE_W - 2 * MARGIN    # largura útil ≈ 739 pt
    CH = PAGE_H - 2 * MARGIN_V  # altura útil  ≈ 527 pt

    # ── Helper de parágrafo ───────────────────────────────────────────────────
    def P(text, size=9, color=None, bold=False, align=TA_LEFT, leading=None):
        return Paragraph(text, ParagraphStyle(
            name=f"_p{abs(hash(text[:30] + str(size) + str(bold)))}",
            fontSize=size,
            textColor=color or C_TEXT,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            alignment=align,
            leading=leading or (size * 1.45),
        ))

    emissao = datetime.now().strftime("%d/%m/%Y  %H:%M")
    story   = []

    # ══════════════════════════════════════════════════════════════════════════
    # 1) CABEÇALHO
    # ══════════════════════════════════════════════════════════════════════════
    hdr_t = Table([[
        P(f"<b>FERRAGENS PINHEIRO</b><br/>"
          f"<font color='#94A3B8' size='8'>SIA e Taguatinga</font>",
          size=13, color=C_WHITE, leading=20),
        P(f"<b>REQUISIÇÃO #{ped}</b><br/>"
          f"<font color='#94A3B8' size='8'>{emissao}</font>",
          size=12, color=C_WHITE, align=TA_RIGHT, leading=20),
    ]], colWidths=[CW * 0.55, CW * 0.45])
    hdr_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_HEADER),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [
        hdr_t,
        Spacer(1, 2 * mm),
        HRFlowable(width="100%", thickness=3, color=C_PRIMARY, spaceAfter=2 * mm),
    ]

    # ══════════════════════════════════════════════════════════════════════════
    # 2) BARRA: vendedor / ped / status / emissão
    # ══════════════════════════════════════════════════════════════════════════
    from ..core.session import session as _sess

    status_labels = {
        "em_andamento": "Em Andamento",
        "em_producao":  "Em Produção",
        "cancelada":    "Cancelada",
    }
    status_str = status_labels.get(req.get("status", ""), req.get("status", "—"))
    vendor_str = req.get("vendor_name", "") or _sess.user_name or "—"
    try:
        emission_str = datetime.fromisoformat(
            str(req.get("emission_date", ""))[:19]
        ).strftime("%d/%m/%Y")
    except Exception:
        emission_str = emissao[:10]

    cw4 = CW / 4
    info_t = Table([[
        P(f"<b>VENDEDOR</b><br/>{vendor_str}",               size=9, leading=14),
        P(f"<b>Nº PED</b><br/>{req.get('ped_number','—')}",  size=9, leading=14),
        P(f"<b>STATUS</b><br/>{status_str}",                 size=9, leading=14),
        P(f"<b>DATA EMISSÃO</b><br/>{emission_str}",         size=9, leading=14),
    ]], colWidths=[cw4] * 4)
    info_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_GRAY_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEAFTER",     (0, 0), (-2, 0),  0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story += [info_t, Spacer(1, 3 * mm)]

    # ══════════════════════════════════════════════════════════════════════════
    # 3) DADOS DO CLIENTE
    # ══════════════════════════════════════════════════════════════════════════
    c    = client or {}
    code = c.get("code", "")
    client_full = (
        f"{code} — {c.get('name', '')}" if code
        else c.get("name", f"ID {req.get('client_id', '')}")
    )
    obra    = req.get("obra") or "—"
    fone    = req.get("phone") or c.get("phone") or "—"
    address = req.get("delivery_address") or "—"

    def lbl(t): return P(f"<b>{t}</b>", size=8, color=C_TEXT_MID)
    def val(t): return P(t or "—", size=10, color=C_TEXT, leading=15)

    cli_t = Table([
        [lbl("CLIENTE"),   lbl("OBRA")],
        [val(client_full), val(obra)],
        [lbl("FONE"),      lbl("ENDEREÇO DE ENTREGA")],
        [val(fone),        val(address)],
    ], colWidths=[CW * 0.35, CW * 0.65])
    cli_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEBELOW",     (0, 1), (-1, 1),  0.5, C_BORDER),
        ("LINEAFTER",     (0, 0), (0, -1),  0.5, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, 0),  C_LIGHT_BG),
        ("BACKGROUND",    (0, 2), (-1, 2),  C_LIGHT_BG),
    ]))
    story += [cli_t, Spacer(1, 3 * mm)]

    # ══════════════════════════════════════════════════════════════════════════
    # 4) PRAZO / ENTREGA
    # ══════════════════════════════════════════════════════════════════════════
    del_date = req.get("delivery_date")
    try:
        del_str = (
            datetime.fromisoformat(str(del_date)[:10]).strftime("%d/%m/%Y")
            if del_date else "—"
        )
    except Exception:
        del_str = str(del_date)[:10] if del_date else "—"

    retirada   = "SIM" if req.get("retirada") else "NÃO"
    entrega    = "SIM" if req.get("entrega")  else "NÃO"
    items_list = req.get("items", [])

    del_t = Table([[
        P(f"<b>PRAZO DE ENTREGA</b><br/>{del_str}", size=9, leading=14),
        P(f"<b>RETIRADA</b><br/>{retirada}",         size=9, leading=14),
        P(f"<b>ENTREGA</b><br/>{entrega}",           size=9, leading=14),
    ]], colWidths=[CW * w for w in (0.44, 0.28, 0.28)])
    del_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_GRAY_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEAFTER",     (0, 0), (-2, 0),  0.5, C_BORDER),
    ]))
    story += [del_t, Spacer(1, 4 * mm)]

    # ══════════════════════════════════════════════════════════════════════════
    # 5) TABELA DE ITENS
    # ══════════════════════════════════════════════════════════════════════════
    story += [P("ITENS DA REQUISIÇÃO", size=9, color=C_TEXT_MID, bold=True),
              Spacer(1, 2 * mm)]

    col_headers  = ["POS.", "CÓD.", "PRODUTO", "QTDE", "COMP", "DESENV.", "CHAPA", "TIPO", "PESO (KG)"]
    col_w_items  = [CW * w for w in (0.06, 0.10, 0.19, 0.08, 0.10, 0.10, 0.10, 0.14, 0.13)]

    def hcell(t):        return P(f"<b>{t}</b>", size=8.5, color=C_WHITE, align=TA_CENTER)
    def dcell(t, b=False): return P(str(t), size=9, color=C_TEXT, align=TA_CENTER, bold=b)

    hrow = [hcell(h) for h in col_headers]
    rows = [[
        dcell(it.get("position", ""), b=True),
        dcell(it.get("product_code") or ""),
        dcell(it.get("product_name") or ""),
        dcell(_fmt_qty(it.get("quantity"))),
        dcell(it.get("comp")   or ""),
        dcell(it.get("desenv") or ""),
        dcell(it.get("chapa")  or ""),
        dcell(it.get("tipo")   or ""),
        dcell(_fmt_kg(it.get("weight"))),
    ] for it in items_list] or [[dcell("") for _ in range(9)]] * 3

    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER),   # header escuro
        ("BACKGROUND", (0, 1), (0, -1), C_HEADER),   # coluna POS escura
    ]
    for i in range(1, len(rows) + 1):
        if i % 2 == 0:
            row_styles.append(("BACKGROUND", (1, i), (-1, i), C_GRAY_BG))

    items_t = Table([hrow] + rows, colWidths=col_w_items, repeatRows=1)
    items_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ] + row_styles))
    story += [items_t, Spacer(1, 4 * mm)]

    # ══════════════════════════════════════════════════════════════════════════
    # 6) OBSERVAÇÕES
    # ══════════════════════════════════════════════════════════════════════════
    if obs and obs.strip():
        obs_t = Table([[P(obs.strip(), size=9, leading=13)]], colWidths=[CW])
        obs_t.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("BACKGROUND",    (0, 0), (-1, -1), C_GRAY_BG),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        story.append(KeepTogether([
            P("OBSERVAÇÕES", size=9, color=C_TEXT_MID, bold=True),
            Spacer(1, 2 * mm),
            obs_t,
            Spacer(1, 4 * mm),
        ]))

    # ══════════════════════════════════════════════════════════════════════════
    # 7) ASSINATURA / RODAPÉ
    # ══════════════════════════════════════════════════════════════════════════
    sig_t = Table([[
        P("<b>ASSINATURA DO CLIENTE</b><br/><br/><br/><br/>"
          "_____________________________________<br/>"
          "<font color='#94A3B8' size='7'>Assinatura e data</font>",
          size=9, leading=14),
        P(f"<b>Emitido em:</b> {emissao}<br/>"
          f"<b>Ferragens Pinheiro</b><br/>"
          f"<font color='#475569' size='8'>pinheiroferragens.com.br</font><br/>"
          f"<font color='#475569' size='8'>SIA e Taguatinga</font>",
          size=9, align=TA_RIGHT, leading=14),
    ]], colWidths=[CW * 0.65, CW * 0.35])
    sig_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEAFTER",     (0, 0), (0, -1),  0.5, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), C_GRAY_BG),
    ]))
    story.append(KeepTogether([sig_t]))

    # ══════════════════════════════════════════════════════════════════════════
    # 8) DESENHO TÉCNICO — página dedicada (se houver conteúdo no canvas)
    # ══════════════════════════════════════════════════════════════════════════
    canvas_result = _render_canvas_to_png(canvas_json)
    if canvas_result:
        png_bytes, img_w, img_h = canvas_result

        # Ajusta para ocupar a largura total; limita a 88% da altura útil
        display_w = CW
        display_h = display_w * (img_h / img_w) if img_w > 0 else display_w
        max_h     = CH * 0.88
        if display_h > max_h:
            display_h = max_h
            display_w = display_h * (img_w / img_h) if img_h > 0 else CW

        canvas_img = RLImage(
            io.BytesIO(png_bytes),
            width=display_w, height=display_h,
        )

        # Cabeçalho da página de desenho
        draw_hdr = Table([[
            P(f"<b>DESENHO TÉCNICO  —  REQUISIÇÃO #{ped}</b>",
              size=11, color=C_WHITE, bold=True),
            P(emissao, size=9, color=C_WHITE, align=TA_RIGHT),
        ]], colWidths=[CW * 0.7, CW * 0.3])
        draw_hdr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_HEADER),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))

        # Imagem com borda
        draw_box = Table([[canvas_img]], colWidths=[CW])
        draw_box.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 1, C_BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("BACKGROUND",    (0, 0), (-1, -1), C_WHITE),
        ]))

        story += [
            PageBreak(),
            draw_hdr,
            Spacer(1, 3 * mm),
            draw_box,
        ]

    doc.build(story)
    return filepath
