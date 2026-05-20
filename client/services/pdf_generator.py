"""
Gerador de PDF de requisições — layout paisagem A4.
Modelo: Pinheiro Ferragens (base visual aprovada).
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas as pdfcanvas

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ── Paleta ───────────────────────────────────────────────────────────────────
if HAS_REPORTLAB:
    C_WHITE      = colors.white
    C_BRAND      = colors.HexColor("#0E3A70")   # azul escuro corporativo
    C_BRAND_LIGHT= colors.HexColor("#1A4F8A")
    C_RED        = colors.HexColor("#D90F1C")   # número do PED
    C_GREEN      = colors.HexColor("#16A34A")   # WhatsApp
    C_TEXT       = colors.HexColor("#17324F")   # texto principal
    C_TEXT_SOFT  = colors.HexColor("#6D7B8C")   # rótulos e muted
    C_BORDER     = colors.HexColor("#C8D5E3")   # borda suave
    C_GRID       = colors.HexColor("#D7E3F0")   # linhas do quadriculado
    C_MUTED_BG   = colors.HexColor("#F4F7FA")   # fundo interno do desenho

# ── Dados da empresa ─────────────────────────────────────────────────────────
COMPANY_PHONES   = ("(61) 3354-8181", "(61) 3012-8181")
COMPANY_SITE     = "www.pinheiroferragens.com.br"
COMPANY_LOCATION = "SIA E TAGUATINGA"
ITEM_POSITIONS   = list("ABCDEFGHIJ")

# Colunas da tabela (9 colunas — soma = 1.00)
TABLE_COLS = [
    ("POS.",    0.06),
    ("CÓDIGO",  0.11),
    ("NOME",    0.20),
    ("QUANT.",  0.08),
    ("COMP.",   0.11),
    ("DESENV.", 0.11),
    ("CHAPA",   0.11),
    ("TIPO.",   0.11),
    ("PESO",    0.11),
]

GAP = 6   # espaçamento padrão entre seções


# ── Utilidades de texto e formatação ─────────────────────────────────────────

def _clean_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip()[:80]


def _fmt_qty(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        n = float(value)
        return str(int(n)) if n == int(n) else f"{n:.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def _fmt_kg(value: object) -> str:
    if value in (None, ""):
        return "0,00"
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def _fmt_optional_kg(value: object) -> str:
    return "" if value in (None, "") else _fmt_kg(value)


def _fmt_date(value: object, fallback: str = "--") -> str:
    if not value:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return text[:10] or fallback


def _fmt_yes_no(value: object) -> str:
    return "SIM" if bool(value) else "NÃO"   # NÃO


def _safe(value: object, fallback: str = "--") -> str:
    return str(value or "").strip() or fallback


def _format_phone(value: object, fallback: str = "--") -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return raw or fallback


def _resolve_phone(req: dict, client: dict | None, fallback: str = "--") -> str:
    return _format_phone(req.get("phone") or (client or {}).get("phone"), fallback)


def _resolve_weight(req: dict, items: list[dict]) -> float:
    weights = [float(i.get("weight") or 0) for i in items if i.get("weight") not in (None, "")]
    return sum(weights) if weights else float(req.get("weight") or 0)


def _fit(text: str, font: str, size: float, max_w: float) -> str:
    if pdfmetrics.stringWidth(text, font, size) <= max_w:
        return text
    trimmed = text
    while trimmed:
        cand = trimmed.rstrip() + "..."
        if pdfmetrics.stringWidth(cand, font, size) <= max_w:
            return cand
        trimmed = trimmed[:-1]
    return "..."


# ── Primitivos de desenho ─────────────────────────────────────────────────────

def _txt(
    pdf: pdfcanvas.Canvas,
    text: str,
    x: float,
    y: float,
    size: float,
    color,
    *,
    bold: bool = False,
    align: str = "left",
    max_w: float | None = None,
) -> None:
    font = "Helvetica-Bold" if bold else "Helvetica"
    content = str(text or "")
    if max_w is not None:
        content = _fit(content, font, size, max_w)
    pdf.saveState()
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    if align == "center":
        pdf.drawCentredString(x, y, content)
    elif align == "right":
        pdf.drawRightString(x, y, content)
    else:
        pdf.drawString(x, y, content)
    pdf.restoreState()


def _box(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    radius: float = 8,
    fill=None,
    stroke=None,
    lw: float = 0.7,
) -> None:
    pdf.saveState()
    pdf.setLineWidth(lw)
    pdf.setStrokeColor(stroke or C_BORDER)
    pdf.setFillColor(fill or C_WHITE)
    pdf.roundRect(x, y, w, h, radius, fill=1, stroke=1)
    pdf.restoreState()


def _line(pdf: pdfcanvas.Canvas, x1, y1, x2, y2, color=None, lw: float = 0.6) -> None:
    pdf.saveState()
    pdf.setStrokeColor(color or C_BORDER)
    pdf.setLineWidth(lw)
    pdf.line(x1, y1, x2, y2)
    pdf.restoreState()


def _grid(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    step: float = 16,
) -> None:
    pdf.saveState()
    pdf.setStrokeColor(C_GRID)
    pdf.setLineWidth(0.4)
    pdf.setDash(1, 2)
    cx = x + step
    while cx < x + w - 1:
        pdf.line(cx, y, cx, y + h)
        cx += step
    cy = y + step
    while cy < y + h - 1:
        pdf.line(x, cy, x + w, cy)
        cy += step
    pdf.restoreState()


def _small_dot(pdf: pdfcanvas.Canvas, cx: float, cy: float, r: float = 2.5, color=None) -> None:
    pdf.saveState()
    pdf.setFillColor(color or C_TEXT_SOFT)
    pdf.circle(cx, cy, r, fill=1, stroke=0)
    pdf.restoreState()


# ── Seções do documento ───────────────────────────────────────────────────────

def _draw_header(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    req: dict,
    client: dict | None,
    ped: str,
    vendor_name: str,
) -> None:
    """Cabeçalho completo: logo | contato || REQUISIÇÃO | data/vendedor || PED"""

    # ── proporções da faixa do cabeçalho
    sep_gap   = 6
    logo_w    = w * 0.245          # logo maior
    contact_w = w * 0.185
    ped_w     = w * 0.165          # PED box menor
    title_w   = w - logo_w - contact_w - ped_w - sep_gap * 2 - 10

    # --- Logo (esquerda) -----------------------------------------------------
    logo_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
    )
    logo_area_x = x
    logo_area_y = y
    logo_area_w = logo_w
    logo_area_h = h

    if os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            # padding mínimo para logo maior
            scale = min((logo_area_w - 4) / iw, (logo_area_h - 4) / ih)
            dw, dh = iw * scale, ih * scale
            dx = logo_area_x + (logo_area_w - dw) / 2
            dy = logo_area_y + (logo_area_h - dh) / 2
            pdf.drawImage(img, dx, dy, width=dw, height=dh, mask="auto")
        except Exception:
            _txt(pdf, "PINHEIRO FERRAGENS", logo_area_x + logo_area_w / 2,
                 logo_area_y + logo_area_h / 2, 10, C_BRAND, bold=True, align="center")
    else:
        _txt(pdf, "PINHEIRO FERRAGENS", logo_area_x + logo_area_w / 2,
             logo_area_y + logo_area_h / 2, 10, C_BRAND, bold=True, align="center")

    # separador logo | contato
    sep_x = x + logo_w + sep_gap
    _line(pdf, sep_x, y + 6, sep_x, y + h - 6, C_BORDER, lw=1.0)

    # --- Informações de contato -----------------------------------------------
    contact_x = sep_x + sep_gap + 2
    icon_r = 2.8
    line_h = 15
    lines = [
        (COMPANY_PHONES[0],),
        (COMPANY_PHONES[1],),
        (COMPANY_SITE,),
        (COMPANY_LOCATION,),
    ]
    ty = y + h - 14
    for (label,) in lines:
        _small_dot(pdf, contact_x + icon_r, ty + 3.5, icon_r, C_BRAND)
        _txt(pdf, label, contact_x + icon_r * 2 + 5, ty, 8, C_TEXT,
             max_w=contact_w - 18)
        ty -= line_h

    # separador contato | título
    sep2_x = contact_x + contact_w
    _line(pdf, sep2_x, y + 6, sep2_x, y + h - 6, C_BORDER, lw=1.0)

    # --- Título + data + vendedor ---------------------------------------------
    title_x = sep2_x + 6
    tx_center = title_x + title_w / 2

    _txt(pdf, "REQUISIÇÃO", tx_center, y + h - 28, 26,
         C_BRAND, bold=True, align="center")

    emission = _fmt_date(req.get("emission_date"), datetime.now().strftime("%d/%m/%Y"))
    half_w = title_w / 2
    date_cx = title_x + half_w * 0.37
    vendor_cx = title_x + half_w * 0.37 + half_w

    # data
    _txt(pdf, emission, date_cx, y + 30, 10, C_TEXT, bold=True, align="center")
    _txt(pdf, "Data", date_cx, y + 18, 7, C_TEXT_SOFT, align="center")

    # vendedor
    _txt(pdf, vendor_name, vendor_cx, y + 30, 10, C_TEXT, bold=True,
         align="center", max_w=half_w + 10)
    _txt(pdf, "Vendedor", vendor_cx, y + 18, 7, C_TEXT_SOFT, align="center")

    # --- PED box (direita) ---------------------------------------------------
    ped_x = title_x + title_w + 6
    ped_h = h
    ped_label_w = ped_w * 0.38

    # fundo geral
    _box(pdf, ped_x, y, ped_w, ped_h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    # fundo do rótulo "PED:"
    pdf.saveState()
    pdf.setFillColor(C_BRAND)
    pdf.roundRect(ped_x, y, ped_label_w, ped_h, 8, fill=1, stroke=0)
    pdf.rect(ped_x + ped_label_w - 8, y, 8, ped_h, fill=1, stroke=0)
    pdf.restoreState()

    _txt(pdf, "PED:", ped_x + ped_label_w / 2, y + ped_h / 2 - 9,
         14, C_WHITE, bold=True, align="center")

    _txt(pdf, _safe(ped, "0"),
         ped_x + ped_label_w + (ped_w - ped_label_w) / 2,
         y + ped_h / 2 - 9,
         20, C_RED, bold=True, align="center",
         max_w=ped_w - ped_label_w - 10)


def _draw_info_bar(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    req: dict,
    client: dict | None,
    items: list[dict],
    vendor_phone: str = "--",
) -> None:
    """Barra de informações: Prazo | Retirada | Entrega | Telefone Vendedor | Peso"""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    weight_val = _resolve_weight(req, items)

    cells = [
        ("\U0001f4c5", "PRAZO DE ENTREGA", _fmt_date(req.get("delivery_date")),  0.24, C_TEXT),
        ("\U0001f69a", "RETIRADA",         _fmt_yes_no(req.get("retirada")),     0.18, C_BRAND),
        ("\U0001f69a", "ENTREGA",          _fmt_yes_no(req.get("entrega")),      0.18, C_BRAND),
        ("\U0001f4f1", vendor_phone,       "",                                   0.25, C_GREEN),
        ("⚖",         "PESO:",            _fmt_kg(weight_val),                  0.15, C_TEXT),
    ]

    cx = x
    for idx, (icon, label, value, ratio, val_color) in enumerate(cells):
        cw = w * ratio
        cy_center = y + h / 2

        if idx > 0:
            _line(pdf, cx, y + 4, cx, y + h - 4, C_BORDER, lw=0.5)

        # posições verticais
        val_y   = cy_center - 1
        label_y = cy_center - 11

        if value:
            # label em cima, valor abaixo
            _txt(pdf, label, cx + cw / 2, val_y + 10, 7,
                 C_TEXT_SOFT, align="center", max_w=cw - 8)
            _txt(pdf, value, cx + cw / 2, label_y, 9.5,
                 val_color, bold=True, align="center", max_w=cw - 8)
        else:
            # célula do telefone WhatsApp — apenas número grande
            _txt(pdf, label, cx + cw / 2, cy_center - 5, 10,
                 val_color, bold=True, align="center", max_w=cw - 8)

        cx += cw


def _draw_client_section(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    req: dict,
    client: dict | None,
) -> None:
    """Duas linhas: CLIENTE | OBRA  /  FONE | ENDEREÇO A ENTREGAR"""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    split_y   = y + h / 2
    obra_x    = x + w * 0.58
    fone_end  = x + w * 0.29

    # linhas internas
    _line(pdf, x, split_y, x + w, split_y, C_BORDER)
    _line(pdf, obra_x, split_y, obra_x, y + h, C_BORDER)
    _line(pdf, fone_end, y, fone_end, split_y, C_BORDER)

    lbl_size  = 7.5
    val_size  = 9.5
    pad       = 10
    lbl_color = C_TEXT_SOFT
    val_color = C_TEXT

    client_name   = _safe(
        (client or {}).get("name") or req.get("client_name"), "--"
    )
    obra          = _safe(req.get("obra"), "--")
    phone_display = _resolve_phone(req, client, "--")
    address       = _safe(req.get("delivery_address"), "--")

    # linha superior: CLIENTE | OBRA
    def _label_val(lx, ly, lw, lh, lbl, val):
        _txt(pdf, lbl, lx + pad, ly + lh - 10, lbl_size, lbl_color, bold=True)
        _txt(pdf, val, lx + pad + pdfmetrics.stringWidth(lbl, "Helvetica-Bold", lbl_size) + 5,
             ly + lh - 10, val_size, val_color,
             max_w=lw - pad - pdfmetrics.stringWidth(lbl, "Helvetica-Bold", lbl_size) - 12)

    _label_val(x, split_y, obra_x - x, h / 2, "CLIENTE:", client_name)
    _label_val(obra_x, split_y, x + w - obra_x, h / 2, "OBRA:", obra)

    # linha inferior: FONE | ENDEREÇO
    _label_val(x, y, fone_end - x, h / 2, "FONE:", phone_display)
    _label_val(fone_end, y, x + w - fone_end, h / 2,
               "ENDEREÇO A ENTREGAR:", address)


def _prepare_rows(items: list[dict]) -> list[dict]:
    rows: list[dict | None] = [None] * len(ITEM_POSITIONS)
    used: set[int] = set()

    def next_free():
        for i in range(len(rows)):
            if i not in used:
                return i
        return None

    for item in items[:len(ITEM_POSITIONS)]:
        if not isinstance(item, dict):
            continue
        pos = _safe(item.get("position"), "").upper()
        if pos in ITEM_POSITIONS:
            slot = ITEM_POSITIONS.index(pos)
            if rows[slot] is None:
                rows[slot] = item
                used.add(slot)
                continue
        fb = next_free()
        if fb is not None:
            rows[fb] = item
            used.add(fb)

    result = []
    for i, pos in enumerate(ITEM_POSITIONS):
        item = rows[i] or {}
        result.append({
            "position":     pos,
            "product_code": _safe(item.get("product_code"), ""),
            "product_name": _safe(item.get("product_name"), ""),
            "quantity":     _fmt_qty(item.get("quantity")),
            "comp":         _safe(item.get("comp"), ""),
            "desenv":       _safe(item.get("desenv"), ""),
            "chapa":        _safe(item.get("chapa"), ""),
            "tipo":         _safe(item.get("tipo"), ""),
            "weight":       _fmt_optional_kg(item.get("weight")) if item else "",
        })
    return result


def _draw_items_table(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    items: list[dict],
) -> None:
    """Tabela de itens POSIÇÃO / QUANT. / COMP. / DESENV. / CHAPA / TIPO. / PESO"""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    header_h = 22
    row_h    = (h - header_h) / len(ITEM_POSITIONS)
    edges    = [x]
    for _, ratio in TABLE_COLS:
        edges.append(edges[-1] + w * ratio)

    # Fundo do cabeçalho
    pdf.saveState()
    pdf.setFillColor(C_BRAND)
    pdf.roundRect(x, y + h - header_h, w, header_h, 8, fill=1, stroke=0)
    pdf.rect(x, y + h - header_h, w, header_h - 8, fill=1, stroke=0)
    pdf.restoreState()

    # Rótulos do cabeçalho
    for i, (label, _) in enumerate(TABLE_COLS):
        cx = edges[i]
        cw = edges[i + 1] - edges[i]
        _txt(pdf, label, cx + cw / 2, y + h - 14, 7.5,
             C_WHITE, bold=True, align="center", max_w=cw - 4)

    # Linhas internas
    pdf.saveState()
    pdf.setStrokeColor(C_BORDER)
    pdf.setLineWidth(0.55)
    for edge in edges[1:-1]:
        pdf.line(edge, y, edge, y + h)
    pdf.line(x, y + h - header_h, x + w, y + h - header_h)
    for ri in range(1, len(ITEM_POSITIONS)):
        ry = y + h - header_h - ri * row_h
        pdf.line(x, ry, x + w, ry)
    pdf.restoreState()

    # Dados das linhas
    rows = _prepare_rows(items)
    for ri, row in enumerate(rows):
        base_y = y + h - header_h - (ri + 1) * row_h + row_h / 2 - 4
        values = [
            row["position"],
            row["product_code"],
            row["product_name"],
            row["quantity"],
            row["comp"],
            row["desenv"],
            row["chapa"],
            row["tipo"],
            row["weight"],
        ]
        for ci, val in enumerate(values):
            cx = edges[ci]
            cw = edges[ci + 1] - edges[ci]
            # NOME alinhado à esquerda; demais centrado
            align = "left" if ci == 2 else "center"
            pad   = 4 if ci == 2 else 0
            _txt(pdf, val, cx + pad + (cw - pad) / 2 if align == "center" else cx + pad + 2,
                 base_y, 7.5, C_TEXT,
                 bold=(ci == 0), align=align, max_w=cw - 6)


def _draw_drawing_box(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    canvas_result: tuple[bytes, int, int] | None = None,
    title: str = "DESENHO",
) -> None:
    """Caixa do desenho técnico com grid interno."""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    # rótulo centralizado no topo
    if title:
        _txt(pdf, title, x + w / 2, y + h - 14, 8.5,
             C_BRAND, bold=True, align="center")

    inner_x = x + 6
    inner_y = y + 6
    inner_w = w - 12
    inner_h = h - 22

    # fundo interno
    _box(pdf, inner_x, inner_y, inner_w, inner_h,
         radius=5, fill=C_MUTED_BG, stroke=C_GRID, lw=0.5)
    _grid(pdf, inner_x + 2, inner_y + 2, inner_w - 4, inner_h - 4, step=14)

    if not canvas_result:
        return

    png_bytes, img_w, img_h = canvas_result
    if img_w <= 0 or img_h <= 0:
        return

    usable_w = inner_w - 10
    usable_h = inner_h - 10
    scale = min(usable_w / img_w, usable_h / img_h)
    dw, dh = img_w * scale, img_h * scale
    dx = inner_x + (inner_w - dw) / 2
    dy = inner_y + (inner_h - dh) / 2
    pdf.drawImage(
        ImageReader(io.BytesIO(png_bytes)),
        dx, dy, width=dw, height=dh,
        preserveAspectRatio=True, mask="auto",
    )


def _draw_grid_area(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
) -> None:
    """Grande área quadriculada (bloco de anotações)."""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)
    _grid(pdf, x + 4, y + 4, w - 8, h - 8, step=14)


def _make_qr_bytes(text: str) -> bytes | None:
    """Gera QR Code como PNG bytes. Retorna None se qrcode não estiver instalado."""
    try:
        import qrcode as _qrc
        qr = _qrc.QRCode(version=1, box_size=4, border=2,
                         error_correction=_qrc.constants.ERROR_CORRECT_M)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0E3A70", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _draw_footer(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    obs: str,
    vendor_phone: str = "--",
) -> None:
    """Rodapé:  [OBSERVAÇÃO]  /  [QR code]  [ASSINATURA DO CLIENTE: ____]"""

    right_x = x + w * 0.45   # bloco ocupa a metade direita
    right_w = w - (right_x - x)

    gap   = 6
    obs_h = max(26, (h - gap) * 0.40)
    sig_h = h - obs_h - gap

    # ── Observação (em cima) ──────────────────────────────────────────────────
    obs_y = y + sig_h + gap
    _box(pdf, right_x, obs_y, right_w, obs_h, radius=6, fill=C_WHITE, stroke=C_BORDER)
    lbl = "OBSERVAÇÃO:"
    lbl_w = pdfmetrics.stringWidth(lbl, "Helvetica-Bold", 8) + 10
    _txt(pdf, lbl, right_x + 8, obs_y + obs_h / 2 - 4, 8, C_TEXT, bold=True)
    _txt(pdf, _safe(obs, ""), right_x + lbl_w, obs_y + obs_h / 2 - 4, 8.5,
         C_TEXT_SOFT, max_w=right_w - lbl_w - 10)

    # ── Assinatura + QR (embaixo) ─────────────────────────────────────────────
    sig_y  = y
    qr_sz  = sig_h - 4          # QR ocupa quase toda a altura da linha

    # QR code — WhatsApp do vendedor
    digits = "".join(c for c in vendor_phone if c.isdigit())
    wa_url = f"https://wa.me/55{digits}" if digits else "https://wa.me/"
    qr_bytes = _make_qr_bytes(wa_url)
    if qr_bytes:
        pdf.drawImage(
            ImageReader(io.BytesIO(qr_bytes)),
            right_x + 2, sig_y + 2, width=qr_sz, height=qr_sz,
            preserveAspectRatio=True, mask="auto",
        )

    # Linha de assinatura
    after_qr = right_x + qr_sz + 8
    sig_lbl  = "ASSINATURA DO CLIENTE:"
    sig_mid  = sig_y + sig_h / 2
    _txt(pdf, sig_lbl, after_qr, sig_mid + 2, 8, C_TEXT, bold=False)
    line_x = after_qr + pdfmetrics.stringWidth(sig_lbl, "Helvetica", 8) + 6
    _line(pdf, line_x, sig_mid, right_x + right_w, sig_mid, C_TEXT, lw=0.8)


# ── Canvas → PNG ─────────────────────────────────────────────────────────────

def _build_canvas_item(data: dict):
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QPixmap
        from PySide6.QtWidgets import (
            QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
            QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem,
        )
        t = data.get("type")
        pen_d = data.get("pen", {})
        pen = QPen(QColor(pen_d.get("color", "#000000")), pen_d.get("width", 2))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        if t == "line":
            it = QGraphicsLineItem(data["x1"], data["y1"], data["x2"], data["y2"])
            it.setPen(pen); return it
        if t == "rect":
            it = QGraphicsRectItem(data["x"], data["y"], data["w"], data["h"])
            it.setPen(pen); return it
        if t == "ellipse":
            it = QGraphicsEllipseItem(data["x"], data["y"], data["w"], data["h"])
            it.setPen(pen); return it
        if t == "path":
            path = QPainterPath()
            pts = data.get("points", [])
            if pts:
                path.moveTo(QPointF(pts[0][0], pts[0][1]))
                for p in pts[1:]:
                    path.lineTo(QPointF(p[0], p[1]))
            it = QGraphicsPathItem(path)
            it.setPen(pen); return it
        if t == "text":
            it = QGraphicsTextItem(data.get("text", ""))
            it.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
            it.setDefaultTextColor(QColor(data.get("color", "#000000")))
            it.setFont(QFont("Segoe UI", data.get("font_size", 12)))
            return it
        if t == "image":
            path = data.get("path", "")
            if path and os.path.exists(path):
                it = QGraphicsPixmapItem(QPixmap(path))
                it.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                return it
    except Exception:
        pass
    return None


def _render_canvas(canvas_json: str, max_w: int = 2400) -> tuple[bytes, int, int] | None:
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QRectF
        from PySide6.QtGui import QBrush, QColor, QImage, QPainter
        from PySide6.QtWidgets import QGraphicsScene

        payload    = json.loads(canvas_json or "{}")
        items_data = payload.get("items", [])
        if not items_data:
            return None

        scene = QGraphicsScene()
        scene.setBackgroundBrush(QBrush(QColor("#FFFFFF")))
        for d in items_data:
            it = _build_canvas_item(d)
            if it:
                scene.addItem(it)

        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty() or bounds.width() <= 0:
            return None

        bounds = bounds.adjusted(-30, -30, 30, 30)
        scale  = min(1.0, max_w / bounds.width())
        img_w  = max(1, int(bounds.width() * scale))
        img_h  = max(1, int(bounds.height() * scale))

        image = QImage(img_w, img_h, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFF)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, img_w, img_h), bounds)
        painter.end()

        data   = QByteArray()
        buf    = QBuffer(data)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        buf.close()
        return bytes(data), img_w, img_h
    except Exception:
        return None


# ── Segunda página: desenho em tela cheia ────────────────────────────────────

def _draw_second_page(
    pdf: pdfcanvas.Canvas,
    ped: str,
    canvas_result: tuple[bytes, int, int],
) -> None:
    pw, ph = landscape(A4)
    mx, my = 10 * mm, 10 * mm
    cw     = pw - 2 * mx

    pdf.setFillColor(C_WHITE)
    pdf.rect(0, 0, pw, ph, fill=1, stroke=0)

    hdr_y = ph - my - 32
    _box(pdf, mx, hdr_y, cw, 32, radius=8, fill=C_BRAND, stroke=C_BRAND)
    _txt(pdf, f"DESENHO TÉCNICO — REQUISIÇÃO {ped}",
         mx + 12, hdr_y + 11, 12, C_WHITE, bold=True)
    _txt(pdf, datetime.now().strftime("%d/%m/%Y %H:%M"),
         mx + cw - 10, hdr_y + 11, 8, C_WHITE, align="right")

    body_h = ph - 2 * my - 32 - 8
    _draw_drawing_box(pdf, mx, my, cw, body_h, canvas_result=canvas_result, title="")


# ── Ponto de entrada público ─────────────────────────────────────────────────

def generate_pdf(
    req: dict,
    client: dict | None,
    obs: str,
    folder: str,
    canvas_json: str = "{}",
) -> str:
    if not HAS_REPORTLAB:
        raise ImportError("reportlab não instalado. Execute: pip install reportlab>=4.0.0")

    os.makedirs(folder, exist_ok=True)

    ped_raw      = str(req.get("ped_number") or "0")
    ped_file     = ped_raw.zfill(6)
    client_name  = (client or {}).get("name", "") or f"ID{req.get('client_id', '')}"
    date_str     = datetime.now().strftime("%Y%m%d")
    filename     = _clean_filename(f"REQ-{ped_file}-{date_str}-{client_name}") + ".pdf"
    filepath     = os.path.join(folder, filename)

    from ..core.session import session as _session

    pw, ph = landscape(A4)
    mx, my = 10 * mm, 10 * mm
    cw     = pw - 2 * mx

    pdf = pdfcanvas.Canvas(filepath, pagesize=landscape(A4))
    pdf.setTitle(f"Requisicao {ped_file} - Ferragens Pinheiro")
    pdf.setAuthor("Ferragens Pinheiro")

    # Fundo branco
    pdf.setFillColor(C_WHITE)
    pdf.rect(0, 0, pw, ph, fill=1, stroke=0)

    vendor_name  = _safe(req.get("vendor_name"), _session.user_name or "--")
    vendor_phone = _format_phone(_session.whatsapp or req.get("vendor_whatsapp") or "", "--")
    items_list   = req.get("items") or []
    if not isinstance(items_list, list):
        items_list = []

    top = ph - my   # cursor vertical (de cima para baixo)

    # 1. CABEÇALHO ─────────────────────────────────────────────────────────────
    hdr_h = 76
    hdr_y = top - hdr_h
    _draw_header(pdf, mx, hdr_y, cw, hdr_h, req, client, ped_raw, vendor_name)
    top = hdr_y - GAP

    # 2. BARRA DE INFORMAÇÕES ──────────────────────────────────────────────────
    bar_h = 42
    bar_y = top - bar_h
    _draw_info_bar(pdf, mx, bar_y, cw, bar_h, req, client, items_list,
                   vendor_phone=vendor_phone)
    top = bar_y - GAP

    # 3. DADOS DO CLIENTE ──────────────────────────────────────────────────────
    cli_h = 46
    cli_y = top - cli_h
    _draw_client_section(pdf, mx, cli_y, cw, cli_h, req, client)
    top = cli_y - GAP

    # 4. TABELA + DESENHO (lado a lado) ────────────────────────────────────────
    body_h  = 182
    body_y  = top - body_h
    table_w = cw * 0.465
    draw_w  = cw - table_w - GAP

    _draw_items_table(pdf, mx, body_y, table_w, body_h, items_list)

    canvas_result = _render_canvas(canvas_json)
    _draw_drawing_box(pdf, mx + table_w + GAP, body_y, draw_w, body_h,
                      canvas_result=canvas_result, title="DESENHO")
    top = body_y - GAP

    # 5. RODAPÉ (ocupa o espaço restante até a margem inferior) ────────────────
    footer_h = max(top - my, 70)   # usa todo o espaço disponível
    foot_y   = top - footer_h
    observation = obs or req.get("obs") or ""
    _draw_footer(pdf, mx, foot_y, cw, footer_h, observation,
                 vendor_phone=vendor_phone)

    # 7. SEGUNDA PÁGINA (desenho em tela cheia, apenas se houver canvas) ───────
    if canvas_result:
        pdf.showPage()
        _draw_second_page(pdf, _safe(ped_raw, "0"), canvas_result)

    pdf.save()
    return filepath
