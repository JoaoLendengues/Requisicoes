"""
Gerador de PDF de requisições — layout paisagem A4.
Modelo: Pinheiro Ferragens (base visual aprovada).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from ..core.datetime_utils import local_now

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
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
ASSETS_DIR       = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
LOGO_PATHS       = [
    r"Z:\REQUISIÇÕES (VENDAS)\logo_requisicao.png",
    r"\\data04tg\TI\REQUISIÇÕES (VENDAS)\logo_requisicao.png",
    os.path.join(ASSETS_DIR, "logo_requisicao.png"),
    os.path.join(ASSETS_DIR, "logo.png"),
]
PDF_INFO_ICON_DIRS = [
    r"Z:\REQUISIÇÕES (VENDAS)\ícones\EMOJI PDF",
    r"\\data04tg\TI\REQUISIÇÕES (VENDAS)\ícones\EMOJI PDF",
    os.path.join(ASSETS_DIR, "icons", "emoji_pdf"),
]
PDF_INFO_ICON_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg", ".bmp")
FONT_DIR         = os.path.join(ASSETS_DIR, "fonts")
FONT_REGULAR_TTF = os.path.join(FONT_DIR, "Montserrat-Regular.ttf")
FONT_BOLD_TTF    = os.path.join(FONT_DIR, "Montserrat-Bold.ttf")
PDF_FONT_REGULAR = "Helvetica"
PDF_FONT_BOLD    = "Helvetica-Bold"
QT_PDF_FONT      = "Montserrat"
_PDF_FONTS_READY = False
_QT_FONT_READY   = False

# Colunas da tabela (8 colunas — soma = 1.00)
TABLE_COLS = [
    ("POS.",    0.04),
    ("C\u00d3DIGO",  0.08),
    ("NOME",    0.42),
    ("QUANT.",  0.06),
    ("COMP.",   0.09),
    ("DESENV.", 0.09),
    ("CHAPA",   0.08),
    ("TIPO.",   0.14),
]

GAP = 6   # espaçamento padrão entre seções


# ── Utilidades de texto e formatação ─────────────────────────────────────────

def _clean_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip()[:80]


def _path_exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except OSError:
        return False


def _resolve_logo_path() -> str:
    for path in LOGO_PATHS:
        if _path_exists(path):
            return path
    return ""


def _normalize_icon_name(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", normalized).strip()
    return re.sub(r"\s+", "_", normalized).upper()


def _resolve_info_icon_path(*names: str) -> str:
    candidates: list[str] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        base_name, ext = os.path.splitext(name)
        variants = [name]
        if base_name:
            variants.append(base_name)
            variants.append(base_name.replace("_", " "))
            variants.append(_normalize_icon_name(base_name))
            variants.append(_normalize_icon_name(base_name).replace("_", " "))
        for variant in variants:
            if variant and variant not in candidates:
                candidates.append(variant)
        if ext:
            continue

    for folder in PDF_INFO_ICON_DIRS:
        if not _path_exists(folder):
            continue
        for candidate in candidates:
            root, ext = os.path.splitext(candidate)
            if ext:
                icon_path = os.path.join(folder, candidate)
                if _path_exists(icon_path):
                    return icon_path
                continue
            for suffix in PDF_INFO_ICON_EXTENSIONS:
                icon_path = os.path.join(folder, f"{candidate}{suffix}")
                if _path_exists(icon_path):
                    return icon_path
    return ""


def _register_pdf_fonts() -> None:
    global PDF_FONT_REGULAR, PDF_FONT_BOLD, _PDF_FONTS_READY
    if _PDF_FONTS_READY or not HAS_REPORTLAB:
        return

    if _path_exists(FONT_REGULAR_TTF) and _path_exists(FONT_BOLD_TTF):
        try:
            pdfmetrics.registerFont(TTFont("Montserrat", FONT_REGULAR_TTF))
            pdfmetrics.registerFont(TTFont("Montserrat-Bold", FONT_BOLD_TTF))
            PDF_FONT_REGULAR = "Montserrat"
            PDF_FONT_BOLD = "Montserrat-Bold"
        except Exception:
            PDF_FONT_REGULAR = "Helvetica"
            PDF_FONT_BOLD = "Helvetica-Bold"

    _PDF_FONTS_READY = True


def _fmt_qty(value: object) -> str:
    if value in (None, ""):
        return ""
    parsed = _parse_number(value)
    return str(value) if parsed is None else _fmt_number(parsed)


def _fmt_kg(value: object) -> str:
    if value in (None, ""):
        return "0,00"
    parsed = _parse_number(value)
    return str(value) if parsed is None else _fmt_number(parsed, strip_zero_decimals=False)


def _fmt_optional_kg(value: object) -> str:
    return "" if value in (None, "") else _fmt_kg(value)


def _parse_number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    cleaned = text.replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _fmt_number(value: object, decimals: int = 2, strip_zero_decimals: bool = True) -> str:
    parsed = _parse_number(value)
    if parsed is None:
        return str(value or "")

    formatted = f"{parsed:,.{decimals}f}"
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    if strip_zero_decimals and formatted.endswith(",00"):
        return formatted[:-3]
    return formatted


def _fmt_ped(value: object) -> str:
    parsed = _parse_number(value)
    return str(value or "0") if parsed is None else _fmt_number(parsed, decimals=0)


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


def _fit_font_size(text: str, font: str, size: float, max_w: float, min_size: float = 6.0) -> float:
    content = str(text or "").strip()
    if not content or max_w <= 0:
        return size
    current = size
    while current > min_size and pdfmetrics.stringWidth(content, font, current) > max_w:
        current -= 0.25
    return max(current, min_size)


def _wrap_text(text: str, font: str, size: float, max_w: float, max_lines: int | None = None) -> list[str]:
    raw = str(text or "")
    if not raw:
        return []

    lines: list[str] = []
    paragraphs = raw.splitlines() or [raw]

    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            if lines and (max_lines is None or len(lines) < max_lines):
                lines.append("")
            continue

        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font, size) <= max_w:
                current = candidate
                continue

            if current:
                lines.append(current)
                if max_lines is not None and len(lines) >= max_lines:
                    lines[-1] = _fit(lines[-1], font, size, max_w)
                    return lines

            current = word
            if pdfmetrics.stringWidth(current, font, size) > max_w:
                current = _fit(current, font, size, max_w)

        if current:
            lines.append(current)
            if max_lines is not None and len(lines) >= max_lines:
                lines[-1] = _fit(lines[-1], font, size, max_w)
                return lines

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(lines[-1], font, size, max_w)
    return lines


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
    font = PDF_FONT_BOLD if bold else PDF_FONT_REGULAR
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


def _draw_image_fit(
    pdf: pdfcanvas.Canvas,
    image_path: str,
    x: float,
    y: float,
    w: float,
    h: float,
) -> bool:
    if not _path_exists(image_path):
        return False
    try:
        img = ImageReader(image_path)
        iw, ih = img.getSize()
        if iw <= 0 or ih <= 0 or w <= 0 or h <= 0:
            return False
        scale = min(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        dx = x + (w - dw) / 2
        dy = y + (h - dh) / 2
        pdf.drawImage(img, dx, dy, width=dw, height=dh, mask="auto")
        return True
    except Exception:
        return False


def _draw_centered_icon_label(
    pdf: pdfcanvas.Canvas,
    center_x: float,
    baseline_y: float,
    label: str,
    *,
    icon_names: tuple[str, ...],
    font_size: float,
    color,
    max_w: float,
    bold: bool = False,
) -> None:
    font = PDF_FONT_BOLD if bold else PDF_FONT_REGULAR
    icon_path = _resolve_info_icon_path(*icon_names)
    icon_size = min(14.5, max(11.0, font_size + 4.0))
    icon_gap = 4.5
    text_max_w = max_w
    has_icon = bool(icon_path)

    if has_icon:
        text_max_w = max(12.0, max_w - icon_size - icon_gap)

    fitted_label = _fit(label, font, font_size, text_max_w)
    label_w = pdfmetrics.stringWidth(fitted_label, font, font_size)

    if has_icon:
        inline_w = min(max_w, icon_size + icon_gap + label_w)
        left_x = center_x - inline_w / 2
        icon_y = baseline_y - icon_size * 0.24
        has_icon = _draw_image_fit(pdf, icon_path, left_x, icon_y, icon_size, icon_size)
        if has_icon:
            _txt(
                pdf,
                fitted_label,
                left_x + icon_size + icon_gap,
                baseline_y,
                font_size,
                color,
                bold=bold,
                align="left",
                max_w=text_max_w,
            )
            return

    _txt(pdf, fitted_label, center_x, baseline_y, font_size, color, bold=bold, align="center", max_w=max_w)


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
    """Cabe?alho completo: logo | contato | requisi??o | data/vendedor | PED"""

    sep_gap = 6
    block_gap = 6
    logo_w = w * 0.27
    side_w = w * 0.20
    contact_w = side_w
    ped_w = side_w

    logo_path = _resolve_logo_path()
    logo_area_x = x
    logo_area_y = y
    logo_area_w = logo_w
    logo_area_h = h

    if _path_exists(logo_path):
        try:
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            scale = min((logo_area_w - 2) / iw, (logo_area_h - 2) / ih)
            dw, dh = iw * scale, ih * scale
            dx = logo_area_x + 2
            dy = logo_area_y + (logo_area_h - dh) / 2
            pdf.drawImage(img, dx, dy, width=dw, height=dh, mask="auto")
        except Exception:
            _txt(pdf, "PINHEIRO FERRAGENS", logo_area_x + 4,
                 logo_area_y + logo_area_h / 2 - 4, 10, C_BRAND, bold=True)
    else:
        _txt(pdf, "PINHEIRO FERRAGENS", logo_area_x + 4,
             logo_area_y + logo_area_h / 2 - 4, 10, C_BRAND, bold=True)

    sep_x = x + logo_w + sep_gap
    _line(pdf, sep_x, y + 6, sep_x, y + h - 6, C_BORDER, lw=1.0)

    contact_area_x = sep_x + sep_gap + 8
    contact_x = contact_area_x + 8
    icon_r = 2.8
    contact_icon_size = 11.5
    contact_gap = 5.0
    contact_text_size = 7.1
    contact_icon_offset = max(3.0, (contact_icon_size - contact_text_size) / 2 + 0.8)
    line_h = 13
    lines = [
        (("TELEFONE", "TELEFONE 1", "FONE"), COMPANY_PHONES[0]),
        (("TELEFONE", "TELEFONE 2", "FONE"), COMPANY_PHONES[1]),
        (("SITE", "WEBSITE"), COMPANY_SITE),
        (("LOCALIZAÇÃO", "LOCALIZACAO", "LOCAL"), COMPANY_LOCATION),
    ]
    ty = y + h - 12
    for icon_names, label in lines:
        icon_path = _resolve_info_icon_path(*icon_names)
        has_icon = _draw_image_fit(
            pdf,
            icon_path,
            contact_x,
            ty - contact_icon_offset,
            contact_icon_size,
            contact_icon_size,
        )
        text_x = contact_x + contact_icon_size + contact_gap if has_icon else contact_x + icon_r * 2 + 5
        if not has_icon:
            _small_dot(pdf, contact_x + icon_r, ty + 3.5, icon_r, C_BRAND)
        _txt(pdf, label, text_x, ty, contact_text_size, C_TEXT,
             max_w=contact_w - 28)
        ty -= line_h

    ped_x = x + w - ped_w
    title_x = contact_area_x + contact_w + block_gap
    title_right = ped_x - block_gap
    title_w = max(title_right - title_x, 120)
    title_shift = min(30, title_w * 0.12)
    group_center = title_x + title_w / 2 - title_shift
    group_w = min(title_w * 0.70, 170)
    title_text = "REQUISI\u00c7\u00c3O"
    title_text_w = pdfmetrics.stringWidth(title_text, PDF_FONT_BOLD, 26)
    title_left = group_center - title_text_w / 2
    vendor_title_anchor_x = title_left + pdfmetrics.stringWidth("REQU", PDF_FONT_BOLD, 26)
    _txt(pdf, title_text, group_center, y + h - 24, 26,
         C_BRAND, bold=True, align="center")

    emission = _fmt_date(req.get("emission_date"), local_now().strftime("%d/%m/%Y"))
    meta_shift = min(10, group_w * 0.08)
    meta_gap = 10
    date_w = min(58, group_w * 0.26)
    vendor_w = max(group_w - date_w - meta_gap, group_w * 0.58)
    vendor_cx = group_center + (date_w / 2 + meta_gap / 2 + vendor_w / 2) - meta_shift
    vendor_font_size = _fit_font_size(vendor_name, PDF_FONT_BOLD, 10, vendor_w, min_size=7.0)
    vendor_max_w = max(title_right - vendor_title_anchor_x, 40)
    fitted_vendor_name = _fit(vendor_name, PDF_FONT_BOLD, vendor_font_size, vendor_max_w)
    vendor_text_w = pdfmetrics.stringWidth(fitted_vendor_name, PDF_FONT_BOLD, vendor_font_size)
    vendor_label_cx = vendor_title_anchor_x + (vendor_text_w / 2)
    emission_text_w = pdfmetrics.stringWidth(emission, PDF_FONT_BOLD, 10)
    date_cx = title_left + emission_text_w / 2
    _txt(pdf, emission, date_cx, y + 30, 10, C_TEXT, bold=True, align="center")
    _draw_centered_icon_label(
        pdf,
        date_cx,
        y + 18,
        "Data",
        icon_names=("DATA",),
        font_size=7,
        color=C_TEXT_SOFT,
        max_w=date_w,
    )
    _txt(pdf, vendor_name, vendor_title_anchor_x, y + 30, vendor_font_size, C_TEXT, bold=True,
         align="left", max_w=vendor_max_w)
    _draw_centered_icon_label(
        pdf,
        vendor_label_cx,
        y + 18,
        "Vendedor",
        icon_names=("VENDEDOR",),
        font_size=7,
        color=C_TEXT_SOFT,
        max_w=vendor_max_w,
    )

    ped_h = h * 0.68
    ped_y = y + (h - ped_h) / 2
    ped_label_w = ped_w * 0.34
    _box(pdf, ped_x, ped_y, ped_w, ped_h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    pdf.saveState()
    pdf.setFillColor(C_BRAND)
    pdf.roundRect(ped_x, ped_y, ped_label_w, ped_h, 8, fill=1, stroke=0)
    pdf.rect(ped_x + ped_label_w - 8, ped_y, 8, ped_h, fill=1, stroke=0)
    pdf.restoreState()

    _txt(pdf, "PED:", ped_x + ped_label_w / 2, ped_y + ped_h / 2 - 6,
         12.5, C_WHITE, bold=True, align="center")
    _txt(pdf, _fmt_ped(ped),
         ped_x + ped_label_w + (ped_w - ped_label_w) / 2,
         ped_y + ped_h / 2 - 7,
         17.5, C_RED, bold=True, align="center",
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

    cells = [
        ("\U0001f4c5", "PRAZO DE ENTREGA", _fmt_date(req.get("delivery_date")),  0.28, C_TEXT),
        ("\U0001f69a", "RETIRADA",         _fmt_yes_no(req.get("retirada")),     0.20, C_BRAND),
        ("\U0001f69a", "ENTREGA",          _fmt_yes_no(req.get("entrega")),      0.20, C_BRAND),
        ("\U0001f4f1", vendor_phone,       "",                                   0.32, C_GREEN),
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


def _draw_info_bar_with_icons(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    req: dict,
    client: dict | None,
    items: list[dict],
    vendor_phone: str = "--",
) -> None:
    """Barra de informações usando arquivos de ícone externos."""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    cells = [
        ("PRAZO DE ENTREGA", "PRAZO DE ENTREGA", _fmt_date(req.get("delivery_date")), 0.28, C_TEXT),
        ("RETIRADA", "RETIRADA", _fmt_yes_no(req.get("retirada")), 0.20, C_BRAND),
        ("ENTREGA", "ENTREGA", _fmt_yes_no(req.get("entrega")), 0.20, C_BRAND),
        ("TELEFONE DO VENDEDOR", "CONTATO DO VENDEDOR", vendor_phone, 0.32, C_GREEN),
    ]

    cx = x
    for idx, (icon_name, label, value, ratio, val_color) in enumerate(cells):
        cw = w * ratio
        cy_center = y + h / 2

        if idx > 0:
            _line(pdf, cx, y + 4, cx, y + h - 4, C_BORDER, lw=0.5)

        icon_path = _resolve_info_icon_path(
            icon_name,
            icon_name.replace(" ", "_"),
            label,
            label.replace(":", ""),
            label.replace(":", "").replace(" ", "_"),
        )
        icon_size = min(12.0, max(9.5, h * 0.28))
        icon_gap = 4.0
        label_size = 7.1
        value_size = 9.5
        phone_size = 9.8
        label_y = cy_center + 5
        value_y = cy_center - 7
        phone_y = value_y

        has_icon = bool(icon_path)

        if value:
            if has_icon:
                max_label_w = max(12.0, cw - icon_size - icon_gap - 8)
                fitted_label = _fit(label, PDF_FONT_REGULAR, label_size, max_label_w)
                label_w = pdfmetrics.stringWidth(fitted_label, PDF_FONT_REGULAR, label_size)
                inline_w = min(cw - 8, icon_size + icon_gap + label_w)
                inline_x = cx + (cw - inline_w) / 2
                icon_y = label_y - icon_size * 0.30
                has_icon = _draw_image_fit(pdf, icon_path, inline_x, icon_y, icon_size, icon_size)
                if has_icon:
                    _txt(pdf, label, inline_x + icon_size + icon_gap, label_y, label_size,
                         C_TEXT_SOFT, align="left", max_w=max_label_w)
                else:
                    _txt(pdf, label, cx + cw / 2, label_y, label_size,
                         C_TEXT_SOFT, align="center", max_w=cw - 8)
            else:
                _txt(pdf, label, cx + cw / 2, label_y, label_size,
                     C_TEXT_SOFT, align="center", max_w=cw - 8)

            _txt(pdf, value, cx + cw / 2, value_y, value_size,
                 val_color, bold=True, align="center", max_w=cw - 8)
        else:
            if has_icon:
                max_phone_w = max(12.0, cw - icon_size - icon_gap - 8)
                fitted_phone = _fit(label, PDF_FONT_BOLD, phone_size, max_phone_w)
                phone_w = pdfmetrics.stringWidth(fitted_phone, PDF_FONT_BOLD, phone_size)
                inline_w = min(cw - 8, icon_size + icon_gap + phone_w)
                inline_x = cx + (cw - inline_w) / 2
                icon_y = phone_y - icon_size * 0.30
                has_icon = _draw_image_fit(pdf, icon_path, inline_x, icon_y, icon_size, icon_size)
                if has_icon:
                    _txt(pdf, label, inline_x + icon_size + icon_gap, phone_y, phone_size,
                         val_color, bold=True, align="left", max_w=max_phone_w)
                else:
                    _txt(pdf, label, cx + cw / 2, phone_y, phone_size,
                         val_color, bold=True, align="center", max_w=cw - 8)
            else:
                _txt(pdf, label, cx + cw / 2, phone_y, phone_size,
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

    lbl_size  = 8
    val_size  = 8
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
        _txt(pdf, val, lx + pad + pdfmetrics.stringWidth(lbl, PDF_FONT_BOLD, lbl_size) + 5,
             ly + lh - 10, val_size, val_color,
             max_w=lw - pad - pdfmetrics.stringWidth(lbl, PDF_FONT_BOLD, lbl_size) - 12)

    _label_val(x, split_y, obra_x - x, h / 2, "CLIENTE:", client_name)
    _label_val(obra_x, split_y, x + w - obra_x, h / 2, "OBRA:", obra)

    # linha inferior: FONE | ENDEREÇO
    _label_val(x, y, fone_end - x, h / 2, "FONE:", phone_display)
    _label_val(fone_end, y, x + w - fone_end, h / 2,
               "ENDERE\u00c7O A ENTREGAR:", address)


def _is_complete_item(item: dict) -> bool:
    for key in ("product_name", "quantity"):
        if str(item.get(key) or "").strip() == "":
            return False
    return True


def _prepare_rows(items: list[dict]) -> list[dict]:
    prepared: list[tuple[int, int, dict]] = []
    for original_idx, item in enumerate(items):
        if not isinstance(item, dict) or not _is_complete_item(item):
            continue
        pos = _safe(item.get("position"), "").upper()
        sort_idx = ITEM_POSITIONS.index(pos) if pos in ITEM_POSITIONS else len(ITEM_POSITIONS) + original_idx
        prepared.append((sort_idx, original_idx, item))

    prepared.sort(key=lambda entry: (entry[0], entry[1]))

    rows: list[dict] = []
    for _, _, item in prepared[:len(ITEM_POSITIONS)]:
        pos = _safe(item.get("position"), "").upper()
        rows.append({
            "position":     pos or "-",
            "product_code": _safe(item.get("product_code"), ""),
            "product_name": _safe(item.get("product_name"), ""),
            "quantity":     _fmt_qty(item.get("quantity")),
            "comp":         _fmt_qty(item.get("comp")),
            "desenv":       _fmt_qty(item.get("desenv")),
            "chapa":        _safe(item.get("chapa"), ""),
            "tipo":         _safe(item.get("tipo"), ""),
        })
    return rows


def _items_table_height(items: list[dict]) -> float:
    row_count = max(1, len(_prepare_rows(items)))
    return 22 + row_count * 20


def _draw_items_table(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    items: list[dict],
) -> None:
    """Tabela de itens POSIÇÃO / QUANT. / COMP. / DESENV. / CHAPA / TIPO. / PESO"""
    _box(pdf, x, y, w, h, radius=8, fill=C_WHITE, stroke=C_BORDER)

    rows = _prepare_rows(items)
    row_count = max(1, len(rows))
    header_h = 22
    row_h    = (h - header_h) / row_count
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
    for ri in range(1, row_count):
        ry = y + h - header_h - ri * row_h
        pdf.line(x, ry, x + w, ry)
    pdf.restoreState()

    if not rows:
        _txt(pdf, "Nenhum item completo para exibir",
             x + w / 2, y + (h - header_h) / 2 - 4,
             8, C_TEXT_SOFT, align="center")
        return

    # Dados das linhas
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
        ]
        for ci, val in enumerate(values):
            cx = edges[ci]
            cw = edges[ci + 1] - edges[ci]
            # NOME alinhado à esquerda; demais centrado
            align = "left" if ci == 2 else "center"
            pad   = 4 if ci == 2 else 0
            font_size = 7.5
            if ci == 2:
                font_size = 7.3
                while font_size > 5.8 and pdfmetrics.stringWidth(str(val or ""), PDF_FONT_REGULAR, font_size) > cw - 8:
                    font_size -= 0.2
            _txt(pdf, val, cx + pad + (cw - pad) / 2 if align == "center" else cx + pad + 2,
                 base_y, font_size, C_TEXT,
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

    # fundo interno liso para o PDF
    _box(pdf, inner_x, inner_y, inner_w, inner_h,
         radius=5, fill=C_WHITE, stroke=C_BORDER, lw=0.5)

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


def _decode_signature_payload(value) -> bytes | None:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value) if value else None
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    if raw.lower().startswith("data:image"):
        parts = raw.split(",", 1)
        raw = parts[1] if len(parts) > 1 else ""

    raw = raw.replace("\n", "").replace("\r", "")
    if not raw:
        return None

    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception:
        return None
    return decoded or None


def _extract_signature_png_bytes(req: dict | None) -> bytes | None:
    if not isinstance(req, dict):
        return None

    candidates = [
        req.get("signature_png"),
        req.get("signature_png_b64"),
        req.get("signature_base64"),
        req.get("client_signature"),
        req.get("client_signature_b64"),
    ]

    nested = req.get("signature")
    if isinstance(nested, dict):
        candidates.extend(
            [
                nested.get("png"),
                nested.get("png_b64"),
                nested.get("base64"),
            ]
        )
    elif nested is not None:
        candidates.append(nested)

    for candidate in candidates:
        decoded = _decode_signature_payload(candidate)
        if decoded:
            return decoded
    return None


def _draw_footer(
    pdf: pdfcanvas.Canvas,
    x: float, y: float, w: float, h: float,
    obs: str,
    vendor_phone: str = "--",
    signature_png_bytes: bytes | None = None,
) -> None:
    """Rodap? em tr?s caixas: observa??o, assinatura e QR code."""

    gap = 6
    obs_w = w * 0.29
    qr_box_w = max(20 * mm, h - 2)
    sig_w = w - obs_w - gap * 2 - qr_box_w

    _box(pdf, x, y, obs_w, h, radius=6, fill=C_WHITE, stroke=C_BORDER)
    lbl = "OBSERVA\u00c7\u00c3O:"
    obs_label_y = y + h - 14
    obs_text_x = x + 6
    obs_text_y = obs_label_y - 11
    obs_text_w = obs_w - 12
    obs_text_size = 7.4
    obs_leading = 8.6
    max_obs_lines = max(1, int((h - 24) / obs_leading))
    obs_lines = _wrap_text(
        _safe(obs, ""),
        PDF_FONT_REGULAR,
        obs_text_size,
        obs_text_w,
        max_lines=max_obs_lines,
    )

    _txt(pdf, lbl, obs_text_x, obs_label_y, 8, C_TEXT, bold=True)
    current_y = obs_text_y
    for line in obs_lines:
        _txt(pdf, line, obs_text_x, current_y, obs_text_size, C_TEXT_SOFT)
        current_y -= obs_leading

    sig_x = x + obs_w + gap
    _box(pdf, sig_x, y, sig_w, h, radius=6, fill=C_WHITE, stroke=C_BORDER)
    sig_line_y = y + 12
    sig_text_y = y + h - 15
    sig_lbl = "ASSINATURA DO CLIENTE:"
    _txt(pdf, sig_lbl, sig_x + sig_w / 2, sig_text_y, 7.5, C_TEXT_SOFT,
         bold=False, align="center")
    sig_img_x = sig_x + 10
    sig_img_y = sig_line_y + 3
    sig_img_w = max(1.0, sig_w - 20)
    sig_img_h = max(1.0, (sig_text_y - 5) - sig_img_y)

    if signature_png_bytes:
        try:
            signature_reader = ImageReader(io.BytesIO(signature_png_bytes))
            img_w, img_h = signature_reader.getSize()
            if img_w > 0 and img_h > 0:
                scale = min(sig_img_w / img_w, sig_img_h / img_h)
                draw_w = img_w * scale
                draw_h = img_h * scale
                draw_x = sig_x + (sig_w - draw_w) / 2
                draw_y = sig_img_y + (sig_img_h - draw_h) / 2
                pdf.drawImage(
                    signature_reader,
                    draw_x,
                    draw_y,
                    width=draw_w,
                    height=draw_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
        except Exception:
            pass
    else:
        _txt(
            pdf,
            "Imprimir e assinar",
            sig_x + sig_w / 2,
            y + h / 2 - 2,
            7.2,
            C_TEXT_SOFT,
            bold=False,
            align="center",
        )
    _line(pdf, sig_x + 12, sig_line_y,
          sig_x + sig_w - 12, sig_line_y, C_TEXT, lw=0.8)

    qr_x = sig_x + sig_w + gap
    _box(pdf, qr_x, y, qr_box_w, h, radius=6, fill=C_WHITE, stroke=C_BORDER)
    digits = "".join(c for c in vendor_phone if c.isdigit())
    wa_url = f"https://wa.me/55{digits}" if digits else "https://wa.me/"
    qr_bytes = _make_qr_bytes(wa_url)
    if qr_bytes:
        qr_size = min(qr_box_w, h) - 8
        pdf.drawImage(
            ImageReader(io.BytesIO(qr_bytes)),
            qr_x + (qr_box_w - qr_size) / 2,
            y + (h - qr_size) / 2,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )


def _build_canvas_item(data: dict):
    try:
        from PySide6.QtCore import QPointF, Qt, QByteArray
        from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainterPath, QPen, QPixmap
        from PySide6.QtWidgets import (
            QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
            QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem,
        )
        global _QT_FONT_READY
        if not _QT_FONT_READY:
            for font_path in (FONT_REGULAR_TTF, FONT_BOLD_TTF):
                if _path_exists(font_path):
                    QFontDatabase.addApplicationFont(font_path)
            _QT_FONT_READY = True

        t = data.get("type")
        pen_d = data.get("pen", {})
        _PEN_STYLES = {
            "solid":   Qt.PenStyle.SolidLine,
            "dash":    Qt.PenStyle.DashLine,
            "dot":     Qt.PenStyle.DotLine,
            "dashdot": Qt.PenStyle.DashDotLine,
        }
        pen = QPen(QColor(pen_d.get("color", "#000000")), pen_d.get("width", 2))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setStyle(_PEN_STYLES.get(pen_d.get("style", "solid"), Qt.PenStyle.SolidLine))
        rotation = float(data.get("rotation", 0) or 0)
        pos = QPointF(float(data.get("pos_x", 0) or 0), float(data.get("pos_y", 0) or 0))

        # "ruler_measure_line" e "manual_dimension_line" têm a mesma estrutura
        # que "line" — apenas o campo "type" difere.
        if t in ("line", "ruler_measure_line", "manual_dimension_line"):
            it = QGraphicsLineItem(data["x1"], data["y1"], data["x2"], data["y2"])
            it.setPen(pen)
            it.setPos(pos)
            if rotation:
                it.setTransformOriginPoint(it.boundingRect().center())
                it.setRotation(rotation)
            return it
        if t == "rect":
            it = QGraphicsRectItem(data["x"], data["y"], data["w"], data["h"])
            it.setPen(pen)
            it.setPos(pos)
            if rotation:
                it.setTransformOriginPoint(it.boundingRect().center())
                it.setRotation(rotation)
            return it
        if t == "ellipse":
            it = QGraphicsEllipseItem(data["x"], data["y"], data["w"], data["h"])
            it.setPen(pen)
            it.setPos(pos)
            if rotation:
                it.setTransformOriginPoint(it.boundingRect().center())
                it.setRotation(rotation)
            return it
        if t == "path":
            path = QPainterPath()
            # Preferir "segments" (M/L/C explicitos) sobre "points" — segments
            # preserva multiplos sub-paths (moveTo + lineTo), curvas e caracteres
            # de presets 3D (cubos, cilindros etc). Quando so usamos "points"
            # como polilinha, tudo conecta em UMA linha continua e o desenho
            # fica torto no PDF. Mesma logica do _deserialize_path em
            # canvas_widget.py — manter os dois em sincronia.
            segments = data.get("segments", [])
            has_segments = False
            if isinstance(segments, list) and segments:
                has_current = False
                for seg in segments:
                    if not isinstance(seg, dict):
                        continue
                    cmd = str(seg.get("cmd", "")).upper()
                    if cmd == "M":
                        path.moveTo(QPointF(float(seg.get("x", 0.0)), float(seg.get("y", 0.0))))
                        has_current = True
                        has_segments = True
                    elif cmd == "L" and has_current:
                        path.lineTo(QPointF(float(seg.get("x", 0.0)), float(seg.get("y", 0.0))))
                        has_segments = True
                    elif cmd == "C" and has_current:
                        c1 = seg.get("c1", [0.0, 0.0])
                        c2 = seg.get("c2", [0.0, 0.0])
                        end = seg.get("end", [0.0, 0.0])
                        if (
                            isinstance(c1, (list, tuple)) and len(c1) == 2
                            and isinstance(c2, (list, tuple)) and len(c2) == 2
                            and isinstance(end, (list, tuple)) and len(end) == 2
                        ):
                            path.cubicTo(
                                QPointF(float(c1[0]), float(c1[1])),
                                QPointF(float(c2[0]), float(c2[1])),
                                QPointF(float(end[0]), float(end[1])),
                            )
                            has_segments = True
            if not has_segments:
                # Fallback retrocompativel — payloads antigos sem segments.
                pts = data.get("points", [])
                if pts:
                    path.moveTo(QPointF(pts[0][0], pts[0][1]))
                    for p in pts[1:]:
                        path.lineTo(QPointF(p[0], p[1]))
            it = QGraphicsPathItem(path)
            it.setPen(pen)
            it.setPos(pos)
            if rotation:
                it.setTransformOriginPoint(it.boundingRect().center())
                it.setRotation(rotation)
            return it
        # "ruler_measure_text" e "manual_dimension_text" têm a mesma estrutura
        # que "text" — posição em "x"/"y", campo "text", "color" e "font_size".
        if t in ("text", "ruler_measure_text", "manual_dimension_text"):
            it = QGraphicsTextItem(data.get("text", ""))
            it.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
            it.setDefaultTextColor(QColor(data.get("color", "#000000")))
            it.setFont(QFont(QT_PDF_FONT, data.get("font_size", 12)))
            if rotation:
                it.setTransformOriginPoint(it.boundingRect().center())
                it.setRotation(rotation)
            return it
        if t == "image":
            path = data.get("path", "")
            image_data = data.get("image_data", "")
            pixmap = QPixmap()
            if path and _path_exists(path):
                pixmap = QPixmap(path)
            elif image_data:
                pixmap.loadFromData(QByteArray.fromBase64(image_data.encode("ascii")), "PNG")
            if not pixmap.isNull():
                display_w = int(data.get("display_w", 0) or 0)
                display_h = int(data.get("display_h", 0) or 0)
                if display_w > 0 and display_h > 0 and (
                    pixmap.width() != display_w or pixmap.height() != display_h
                ):
                    pixmap = pixmap.scaled(
                        display_w,
                        display_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                it = QGraphicsPixmapItem(pixmap)
                it.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                if rotation:
                    it.setTransformOriginPoint(it.boundingRect().center())
                    it.setRotation(rotation)
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
    _txt(pdf, local_now().strftime("%d/%m/%Y %H:%M"),
         mx + cw - 10, hdr_y + 11, 8, C_WHITE, align="right")

    body_h = ph - 2 * my - 32 - 8
    _draw_drawing_box(pdf, mx, my, cw, body_h, canvas_result=canvas_result, title="")


# ── Ponto de entrada público ─────────────────────────────────────────────────

class PdfPublishError(Exception):
    """O PDF foi gerado localmente, mas não pôde ser publicado na pasta de rede.

    Carrega o caminho da cópia local preservada, para o usuário poder recuperá-la.
    """
    def __init__(self, message: str, local_path: str):
        super().__init__(message)
        self.local_path = local_path


def _publish_pdf_atomic(local_path: str, dest_dir: str, filename: str) -> str:
    """Publica o PDF do ``local_path`` em ``dest_dir`` (pasta de rede) de forma
    atômica: copia para um nome temporário no destino e renomeia. Assim nunca
    aparece um PDF pela metade no diretório, mesmo se a rede cair no meio.
    Retorna o caminho final publicado."""
    _safe_makedirs(dest_dir)
    final_path = os.path.join(dest_dir, filename)
    tmp_dest = os.path.join(dest_dir, f".{filename}.part")
    try:
        shutil.copyfile(local_path, tmp_dest)
        os.replace(tmp_dest, final_path)  # rename no mesmo volume = atômico
    except Exception:
        try:
            if os.path.exists(tmp_dest):
                os.remove(tmp_dest)
        except Exception:
            pass
        raise
    return final_path


def _safe_makedirs(path: str) -> None:
    """Cria o diretório ``path`` com tratamento específico de erros de rede Windows.

    Lança :class:`RuntimeError` com mensagem em português para os erros mais comuns
    ao acessar pastas UNC (``\\\\servidor\\compartilhamento``), evitando que o usuário
    veja rastreamentos técnicos confusos.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        winerr = getattr(exc, "winerror", None)

        _is_unc = path.startswith("\\\\") or path.startswith("//")

        if winerr == 1326:
            # ERROR_LOGON_FAILURE — credenciais não aceitas pelo servidor
            raise RuntimeError(
                "Não foi possível acessar a pasta de rede para salvar o PDF.\n\n"
                "O Windows recusou o acesso porque as credenciais de rede não foram "
                "reconhecidas (erro 1326).\n\n"
                "Soluções:\n"
                "  • Abra o Explorador de Arquivos, acesse a pasta de rede manualmente "
                "e faça login quando solicitado.\n"
                "  • Verifique com o TI se o seu usuário tem permissão de escrita em:\n"
                f"    {path}"
            ) from exc

        if winerr == 5:
            # ERROR_ACCESS_DENIED
            raise RuntimeError(
                "Acesso negado à pasta de rede.\n\n"
                "O seu usuário Windows não tem permissão de escrita na pasta de destino "
                "(erro 5 — acesso negado).\n\n"
                f"Pasta: {path}\n\n"
                "Solicite ao TI que conceda permissão de escrita para o seu usuário."
            ) from exc

        if winerr in (53, 67, 1231, 1232):
            # ERROR_BAD_NETPATH / ERROR_BAD_NET_NAME / caminho de rede inacessível
            raise RuntimeError(
                "O caminho de rede não foi encontrado.\n\n"
                "Verifique se:\n"
                "  • O servidor de arquivos está ligado e acessível.\n"
                "  • O seu computador está conectado à rede da empresa.\n\n"
                f"Caminho: {path}"
            ) from exc

        if winerr == 1219:
            # ERROR_SESSION_CREDENTIAL_CONFLICT
            raise RuntimeError(
                "Conflito de credenciais de rede (erro 1219).\n\n"
                "Já existe uma sessão de rede aberta para o mesmo servidor com "
                "credenciais diferentes.\n\n"
                "Desconecte e reconecte a pasta de rede no Explorador de Arquivos, "
                "ou reinicie o serviço de rede, e tente novamente."
            ) from exc

        if _is_unc:
            # Erro genérico em caminho UNC — inclui detalhes úteis
            raise RuntimeError(
                f"Não foi possível criar ou acessar a pasta de rede.\n\n"
                f"Pasta: {path}\n"
                f"Erro: {exc}"
            ) from exc

        # Caminho local — relança sem alteração
        raise

    # Diretório existe (ou foi criado): verifica permissão de escrita com um arquivo temporário.
    # Necessário porque makedirs(exist_ok=True) não garante que temos permissão de escrita.
    try:
        fd, _tmp = tempfile.mkstemp(dir=path, prefix=".perm_check_", suffix=".tmp")
        os.close(fd)
        os.remove(_tmp)
    except OSError as exc:
        winerr = getattr(exc, "winerror", None)
        _is_unc = path.startswith("\\\\") or path.startswith("//")

        if winerr == 5 or winerr == 1326:
            raise RuntimeError(
                "A pasta de destino existe, mas não é possível gravar arquivos nela.\n\n"
                f"Pasta: {path}\n\n"
                "Verifique com o TI se o seu usuário tem permissão de escrita."
            ) from exc
        raise RuntimeError(
            f"A pasta de destino não está acessível para gravação.\n\n"
            f"Pasta: {path}\n"
            f"Erro: {exc}"
        ) from exc


def generate_pdf(
    req: dict,
    client: dict | None,
    obs: str,
    folder: str,
    canvas_json: str = "{}",
    signature_png_bytes: bytes | None = None,
) -> str:
    if not HAS_REPORTLAB:
        raise ImportError("reportlab não instalado. Execute: pip install reportlab>=4.0.0")

    _register_pdf_fonts()

    ped_raw      = str(req.get("ped_number") or "0")
    ped_file     = ped_raw.zfill(6)
    client_name  = (client or {}).get("name", "") or f"ID{req.get('client_id', '')}"
    date_str     = local_now().strftime("%Y%m%d")
    filename     = _clean_filename(f"REQ-{ped_file}-{date_str}-{client_name}") + ".pdf"

    # Renderiza primeiro num arquivo LOCAL (sem depender da rede durante o
    # desenho); só depois publica no diretório configurado. Garante que sempre
    # existe uma cópia local mesmo se o share estiver fora.
    local_dir = os.path.join(tempfile.gettempdir(), "requisicoes_pdf")
    os.makedirs(local_dir, exist_ok=True)
    filepath = os.path.join(local_dir, filename)

    from ..core.session import session as _session

    pw, ph = landscape(A4)
    mx, my = 10 * mm, 10 * mm
    cw     = pw - 2 * mx

    pdf = pdfcanvas.Canvas(filepath, pagesize=landscape(A4))
    pdf.setTitle(f"Requisicao {ped_file} - Ferragens Pinheiro")
    pdf.setAuthor("Ferragens Pinheiro")
    pdf.setFillColor(C_WHITE)
    pdf.rect(0, 0, pw, ph, fill=1, stroke=0)

    vendor_name = _safe(req.get("vendor_name"), _session.user_name or "--")
    vendor_raw = (
        _session.whatsapp
        or (req.get("vendor") or {}).get("whatsapp")
        or req.get("vendor_whatsapp")
        or req.get("vendor_phone")
        or ""
    )
    vendor_phone = _format_phone(vendor_raw, "--")
    items_list = req.get("items") or []
    if not isinstance(items_list, list):
        items_list = []

    top = ph - my

    hdr_h = 76
    hdr_y = top - hdr_h
    _draw_header(pdf, mx, hdr_y, cw, hdr_h, req, client, ped_raw, vendor_name)
    top = hdr_y - GAP

    bar_h = 42
    bar_y = top - bar_h
    _draw_info_bar_with_icons(pdf, mx, bar_y, cw, bar_h, req, client, items_list, vendor_phone=vendor_phone)
    top = bar_y - GAP

    cli_h = 46
    cli_y = top - cli_h
    _draw_client_section(pdf, mx, cli_y, cw, cli_h, req, client)
    top = cli_y - GAP

    canvas_result = _render_canvas(canvas_json)
    footer_h = 60
    foot_y = my
    table_h = _items_table_height(items_list)
    table_y = top - table_h
    _draw_items_table(pdf, mx, table_y, cw, table_h, items_list)

    draw_y = foot_y + footer_h + 2
    draw_h = max(table_y - GAP - draw_y, 70)
    _draw_drawing_box(
        pdf,
        mx,
        draw_y,
        cw,
        draw_h,
        canvas_result=canvas_result,
        title="DESENHO TECNICO",
    )

    observation = obs or req.get("obs") or ""
    resolved_signature = signature_png_bytes or _extract_signature_png_bytes(req)
    _draw_footer(
        pdf,
        mx,
        foot_y,
        cw,
        footer_h,
        observation,
        vendor_phone=vendor_phone,
        signature_png_bytes=resolved_signature,
    )

    if canvas_result:
        pdf.showPage()
        _draw_second_page(pdf, _safe(ped_raw, "0"), canvas_result)

    pdf.save()

    # Publica no diretório configurado (share) de forma atômica. Se falhar,
    # mantém a cópia local e sinaliza onde ela está.
    try:
        final_path = _publish_pdf_atomic(filepath, folder, filename)
    except Exception as exc:
        raise PdfPublishError(
            f"O PDF foi gerado, mas não pôde ser salvo na pasta de rede "
            f"({folder}).\nUma cópia local foi mantida em:\n{filepath}\n\nDetalhe: {exc}",
            local_path=filepath,
        ) from exc

    # Publicado com sucesso — remove a cópia local temporária.
    try:
        os.remove(filepath)
    except Exception:
        pass
    return final_path
