"""
PDF generator for requisitions in landscape A4 format.
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


if HAS_REPORTLAB:
    C_PAGE_BG = colors.white
    C_CARD_BG = colors.white
    C_BRAND = colors.HexColor("#0E3A70")
    C_BRAND_DARK = colors.HexColor("#0A2E59")
    C_RED = colors.HexColor("#D90F1C")
    C_GREEN = colors.HexColor("#16A34A")
    C_TEXT = colors.HexColor("#17324F")
    C_TEXT_SOFT = colors.HexColor("#6D7B8C")
    C_BORDER = colors.HexColor("#D7DFEA")
    C_GRID = colors.HexColor("#E7ECF4")
    C_MUTED_BG = colors.HexColor("#F8FAFD")


COMPANY_PHONES = ("(61) 3354-8181", "(61) 3012-8181")
COMPANY_SITE = "www.pinheiroferragens.com.br"
COMPANY_LOCATION = "SIA E TAGUATINGA"
TOP_PHONE_FALLBACK = "(61) 99932-5256"
ITEM_POSITIONS = list("ABCDEFGHIJ")


def _clean_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip()[:80]


def _fmt_qty(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}".replace(".", ",")


def _fmt_kg(value: object) -> str:
    if value in (None, ""):
        return "0,00"
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def _fmt_date(value: object, fallback: str = "-") -> str:
    if not value:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    try:
        if "T" in text:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(text[:10])
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return text[:10] or fallback


def _fmt_datetime(value: object, fallback: str = "-") -> str:
    if not value:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text or fallback


def _fmt_yes_no(value: object) -> str:
    return "SIM" if bool(value) else "NAO"


def _format_phone(value: object, fallback: str = "-") -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return raw or fallback


def _safe_text(value: object, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text or fallback


def _fit_text(text: str, font_name: str, font_size: float, max_width: float) -> str:
    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return text
    trimmed = text
    while trimmed:
        candidate = trimmed.rstrip() + "..."
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            return candidate
        trimmed = trimmed[:-1]
    return "..."


def _file_display_name(path: object, fallback: str = "-") -> str:
    text = str(path or "").strip()
    if not text:
        return fallback
    return os.path.basename(text) or fallback


def _draw_round_box(
    pdf: pdfcanvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float = 10,
    fill_color=None,
    stroke_color=None,
    line_width: float = 0.8,
) -> None:
    pdf.saveState()
    pdf.setLineWidth(line_width)
    pdf.setStrokeColor(stroke_color or C_BORDER)
    pdf.setFillColor(fill_color or C_CARD_BG)
    pdf.roundRect(x, y, width, height, radius, fill=1, stroke=1)
    pdf.restoreState()


def _draw_text(
    pdf: pdfcanvas.Canvas,
    text: str,
    x: float,
    y: float,
    size: float,
    color,
    *,
    bold: bool = False,
    align: str = "left",
    max_width: float | None = None,
) -> None:
    font_name = "Helvetica-Bold" if bold else "Helvetica"
    content = str(text or "")
    if max_width is not None:
        content = _fit_text(content, font_name, size, max_width)
    pdf.saveState()
    pdf.setFont(font_name, size)
    pdf.setFillColor(color)
    if align == "center":
        pdf.drawCentredString(x, y, content)
    elif align == "right":
        pdf.drawRightString(x, y, content)
    else:
        pdf.drawString(x, y, content)
    pdf.restoreState()


def _draw_label_value(
    pdf: pdfcanvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    value: str,
    *,
    align: str = "center",
    value_color=None,
    label_color=None,
    value_size: float = 9.5,
) -> None:
    label_color = label_color or C_TEXT_SOFT
    value_color = value_color or C_TEXT

    if align == "left":
        text_x = x + 10
        label_align = "left"
    elif align == "right":
        text_x = x + width - 10
        label_align = "right"
    else:
        text_x = x + width / 2
        label_align = "center"

    _draw_text(pdf, label, text_x, y + height - 14, 7.2, label_color, bold=False, align=label_align, max_width=width - 14)
    _draw_text(pdf, value, text_x, y + 10, value_size, value_color, bold=True, align=label_align, max_width=width - 14)


def _draw_grid(
    pdf: pdfcanvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    step_x: float = 18,
    step_y: float = 18,
) -> None:
    pdf.saveState()
    pdf.setStrokeColor(C_GRID)
    pdf.setLineWidth(0.45)
    pdf.setDash(1.2, 2.4)

    current_x = x + step_x
    while current_x < x + width - 1:
        pdf.line(current_x, y, current_x, y + height)
        current_x += step_x

    current_y = y + step_y
    while current_y < y + height - 1:
        pdf.line(x, current_y, x + width, current_y)
        current_y += step_y

    pdf.restoreState()


def _draw_logo_area(pdf: pdfcanvas.Canvas, x: float, y: float, width: float, height: float) -> None:
    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png"))
    logo_area_w = width * 0.56

    if os.path.exists(logo_path):
        try:
            image = ImageReader(logo_path)
            img_w, img_h = image.getSize()
            max_w = logo_area_w - 12
            max_h = height - 12
            scale = min(max_w / img_w, max_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            draw_x = x + (logo_area_w - draw_w) / 2
            draw_y = y + (height - draw_h) / 2
            pdf.drawImage(image, draw_x, draw_y, width=draw_w, height=draw_h, mask="auto")
        except Exception:
            _draw_text(pdf, "pinheiro", x + logo_area_w / 2, y + height / 2 + 4, 24, C_BRAND, bold=True, align="center")
    else:
        _draw_text(pdf, "pinheiro", x + logo_area_w / 2, y + height / 2 + 4, 24, C_BRAND, bold=True, align="center")

    separator_x = x + logo_area_w + 4
    pdf.saveState()
    pdf.setStrokeColor(C_BORDER)
    pdf.setLineWidth(1)
    pdf.line(separator_x, y + 4, separator_x, y + height - 4)
    pdf.restoreState()

    text_x = separator_x + 14
    line_y = y + height - 12
    lines = (
        COMPANY_PHONES[0],
        COMPANY_PHONES[1],
        COMPANY_SITE,
        COMPANY_LOCATION,
    )
    for line in lines:
        _draw_text(pdf, line, text_x, line_y, 8.5, C_TEXT, bold=False, align="left", max_width=width - (text_x - x) - 4)
        line_y -= 14


def _draw_ped_box(pdf: pdfcanvas.Canvas, x: float, y: float, width: float, height: float, ped: str) -> None:
    _draw_round_box(pdf, x, y, width, height, radius=9, fill_color=C_CARD_BG, stroke_color=C_BORDER)
    label_width = width * 0.39
    pdf.saveState()
    pdf.setFillColor(C_BRAND)
    pdf.roundRect(x, y, label_width, height, 9, fill=1, stroke=0)
    pdf.rect(x + label_width - 9, y, 9, height, fill=1, stroke=0)
    pdf.restoreState()

    _draw_text(pdf, "PED:", x + label_width / 2, y + height / 2 - 8, 18, colors.white, bold=True, align="center")
    _draw_text(pdf, ped, x + label_width + (width - label_width) / 2, y + height / 2 - 10, 26, C_RED, bold=False, align="center", max_width=width - label_width - 12)


def _prepare_item_rows(items: list[dict]) -> list[dict]:
    rows: list[dict | None] = [None] * len(ITEM_POSITIONS)
    used_slots: set[int] = set()

    def next_free_slot() -> int | None:
        for index in range(len(rows)):
            if index not in used_slots and rows[index] is None:
                return index
        return None

    for item in items[: len(ITEM_POSITIONS)]:
        if not isinstance(item, dict):
            continue
        position = _safe_text(item.get("position"), "").upper()
        if position in ITEM_POSITIONS:
            slot = ITEM_POSITIONS.index(position)
            if rows[slot] is None:
                rows[slot] = item
                used_slots.add(slot)
                continue
        fallback_slot = next_free_slot()
        if fallback_slot is not None:
            rows[fallback_slot] = item
            used_slots.add(fallback_slot)

    prepared = []
    for index, position in enumerate(ITEM_POSITIONS):
        item = rows[index] or {}
        prepared.append(
            {
                "position": position,
                "quantity": _fmt_qty(item.get("quantity")),
                "comp": _safe_text(item.get("comp"), ""),
                "desenv": _safe_text(item.get("desenv"), ""),
                "chapa": _safe_text(item.get("chapa"), ""),
                "tipo": _safe_text(item.get("tipo"), ""),
                "weight": _fmt_kg(item.get("weight")) if item else "",
            }
        )
    return prepared


def _draw_items_table(pdf: pdfcanvas.Canvas, x: float, y: float, width: float, height: float, items: list[dict]) -> None:
    _draw_round_box(pdf, x, y, width, height, radius=10, fill_color=C_CARD_BG, stroke_color=C_BORDER)

    columns = [
        ("POSICAO", 0.13),
        ("QUANT.", 0.14),
        ("COMP.", 0.15),
        ("DESENV.", 0.15),
        ("CHAPA", 0.15),
        ("TIPO.", 0.14),
        ("PESO", 0.14),
    ]

    header_h = 22
    row_h = (height - header_h) / len(ITEM_POSITIONS)
    column_edges = [x]
    for _, ratio in columns:
        column_edges.append(column_edges[-1] + width * ratio)

    pdf.saveState()
    pdf.setFillColor(C_BRAND)
    pdf.roundRect(x, y + height - header_h, width, header_h, 10, fill=1, stroke=0)
    pdf.rect(x, y + height - header_h, width, header_h - 10, fill=1, stroke=0)
    pdf.restoreState()

    for index, (label, _) in enumerate(columns):
        col_x = column_edges[index]
        col_w = column_edges[index + 1] - column_edges[index]
        _draw_text(pdf, label, col_x + col_w / 2, y + height - 15, 8, colors.white, bold=True, align="center", max_width=col_w - 6)

    pdf.saveState()
    pdf.setStrokeColor(C_BORDER)
    pdf.setLineWidth(0.6)

    for edge in column_edges[1:-1]:
        pdf.line(edge, y, edge, y + height)

    pdf.line(x, y + height - header_h, x + width, y + height - header_h)
    for row_index in range(1, len(ITEM_POSITIONS)):
        row_y = y + height - header_h - row_index * row_h
        pdf.line(x, row_y, x + width, row_y)
    pdf.restoreState()

    prepared_rows = _prepare_item_rows(items)
    for row_index, row in enumerate(prepared_rows):
        base_y = y + height - header_h - (row_index + 1) * row_h
        values = [
            row["position"],
            row["quantity"],
            row["comp"],
            row["desenv"],
            row["chapa"],
            row["tipo"],
            row["weight"],
        ]
        for col_index, value in enumerate(values):
            col_x = column_edges[col_index]
            col_w = column_edges[col_index + 1] - column_edges[col_index]
            _draw_text(
                pdf,
                value,
                col_x + col_w / 2,
                base_y + row_h / 2 - 4,
                8.5,
                C_TEXT,
                bold=(col_index == 0),
                align="center",
                max_width=col_w - 6,
            )


def _draw_preview_box(
    pdf: pdfcanvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    title: str | None = None,
    canvas_result: tuple[bytes, int, int] | None = None,
) -> None:
    _draw_round_box(pdf, x, y, width, height, radius=10, fill_color=C_CARD_BG, stroke_color=C_BORDER)

    title_space = 18 if title else 0
    if title:
        _draw_text(pdf, title, x + width / 2, y + height - 16, 10, C_BRAND, bold=True, align="center")

    inner_x = x + 8
    inner_y = y + 8
    inner_w = width - 16
    inner_h = height - 16 - title_space

    _draw_round_box(pdf, inner_x, inner_y, inner_w, inner_h, radius=8, fill_color=C_MUTED_BG, stroke_color=C_GRID, line_width=0.7)
    _draw_grid(pdf, inner_x + 3, inner_y + 3, inner_w - 6, inner_h - 6)

    if not canvas_result:
        return

    png_bytes, img_w, img_h = canvas_result
    if img_w <= 0 or img_h <= 0:
        return

    usable_w = inner_w - 14
    usable_h = inner_h - 14
    scale = min(usable_w / img_w, usable_h / img_h)
    draw_w = img_w * scale
    draw_h = img_h * scale
    draw_x = inner_x + (inner_w - draw_w) / 2
    draw_y = inner_y + (inner_h - draw_h) / 2
    pdf.drawImage(ImageReader(io.BytesIO(png_bytes)), draw_x, draw_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")


def _draw_signature_and_obs(pdf: pdfcanvas.Canvas, x: float, y: float, width: float, obs: str) -> None:
    start_x = x + width * 0.53
    label_y = y + 35
    line_y = y + 31

    _draw_text(pdf, "ASSINATURA DO CLIENTE:", start_x, label_y, 9, C_TEXT, bold=False, align="left")
    pdf.saveState()
    pdf.setStrokeColor(C_TEXT)
    pdf.setLineWidth(0.8)
    pdf.line(start_x + 108, line_y, x + width - 4, line_y)
    pdf.restoreState()

    obs_x = start_x
    obs_y = y + 2
    obs_w = width - (obs_x - x)
    obs_h = 22
    _draw_round_box(pdf, obs_x, obs_y, obs_w, obs_h, radius=8, fill_color=C_CARD_BG, stroke_color=C_BORDER)
    _draw_text(pdf, "OBSERVACAO:", obs_x + 10, obs_y + obs_h / 2 - 4, 8.5, C_TEXT, bold=False, align="left")
    observation = _safe_text(obs, "0")
    _draw_text(pdf, observation, obs_x + obs_w - 10, obs_y + obs_h / 2 - 4, 8.5, C_TEXT_SOFT, bold=False, align="right", max_width=obs_w - 95)


def _draw_second_page(pdf: pdfcanvas.Canvas, ped: str, canvas_result: tuple[bytes, int, int]) -> None:
    page_w, page_h = landscape(A4)
    margin_x = 12 * mm
    margin_y = 12 * mm
    content_w = page_w - (2 * margin_x)
    content_h = page_h - (2 * margin_y)

    pdf.setFillColor(C_PAGE_BG)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    header_y = page_h - margin_y - 36
    _draw_round_box(pdf, margin_x, header_y, content_w, 36, radius=10, fill_color=C_BRAND, stroke_color=C_BRAND)
    _draw_text(pdf, f"DESENHO TECNICO - REQUISICAO {ped}", margin_x + 14, header_y + 13, 13, colors.white, bold=True, align="left", max_width=content_w - 120)
    _draw_text(pdf, datetime.now().strftime("%d/%m/%Y %H:%M"), margin_x + content_w - 14, header_y + 13, 9, colors.white, bold=False, align="right")

    body_y = margin_y
    body_h = content_h - 48
    _draw_preview_box(
        pdf,
        margin_x,
        body_y,
        content_w,
        body_h,
        title=None,
        canvas_result=canvas_result,
    )


def _build_canvas_item(data: dict):
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QPixmap
        from PySide6.QtWidgets import (
            QGraphicsEllipseItem,
            QGraphicsLineItem,
            QGraphicsPathItem,
            QGraphicsPixmapItem,
            QGraphicsRectItem,
            QGraphicsTextItem,
        )

        item_type = data.get("type")
        pen_data = data.get("pen", {})
        pen = QPen(QColor(pen_data.get("color", "#000000")), pen_data.get("width", 2))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        if item_type == "line":
            item = QGraphicsLineItem(data["x1"], data["y1"], data["x2"], data["y2"])
            item.setPen(pen)
            return item
        if item_type == "rect":
            item = QGraphicsRectItem(data["x"], data["y"], data["w"], data["h"])
            item.setPen(pen)
            return item
        if item_type == "ellipse":
            item = QGraphicsEllipseItem(data["x"], data["y"], data["w"], data["h"])
            item.setPen(pen)
            return item
        if item_type == "path":
            path = QPainterPath()
            points = data.get("points", [])
            if points:
                path.moveTo(QPointF(points[0][0], points[0][1]))
                for point in points[1:]:
                    path.lineTo(QPointF(point[0], point[1]))
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            return item
        if item_type == "text":
            item = QGraphicsTextItem(data.get("text", ""))
            item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
            item.setDefaultTextColor(QColor(data.get("color", "#000000")))
            item.setFont(QFont("Segoe UI", data.get("font_size", 12)))
            return item
        if item_type == "image":
            path = data.get("path", "")
            if path and os.path.exists(path):
                pixmap = QPixmap(path)
                item = QGraphicsPixmapItem(pixmap)
                item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                return item
    except Exception:
        pass
    return None


def _render_canvas_to_png(canvas_json: str, max_w: int = 2400) -> tuple[bytes, int, int] | None:
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QRectF
        from PySide6.QtGui import QBrush, QColor, QImage, QPainter
        from PySide6.QtWidgets import QGraphicsScene

        payload = json.loads(canvas_json or "{}")
        items_data = payload.get("items", [])
        if not items_data:
            return None

        scene = QGraphicsScene()
        scene.setBackgroundBrush(QBrush(QColor("#FFFFFF")))

        for item_data in items_data:
            item = _build_canvas_item(item_data)
            if item:
                scene.addItem(item)

        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty() or bounds.width() <= 0:
            return None

        bounds = bounds.adjusted(-30, -30, 30, 30)
        scale = min(1.0, max_w / bounds.width())
        img_w = max(1, int(bounds.width() * scale))
        img_h = max(1, int(bounds.height() * scale))

        image = QImage(img_w, img_h, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFF)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, img_w, img_h), bounds)
        painter.end()

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        return bytes(data), img_w, img_h
    except Exception:
        return None


def generate_pdf(req: dict, client: dict | None, obs: str, folder: str, canvas_json: str = "{}") -> str:
    if not HAS_REPORTLAB:
        raise ImportError("reportlab nao instalado. Execute: pip install reportlab>=4.0.0")

    os.makedirs(folder, exist_ok=True)

    ped_raw = str(req.get("ped_number") or "0")
    ped_file = ped_raw.zfill(6)
    client_name = (client or {}).get("name", "") or f"ID{req.get('client_id', '')}"
    date_str = datetime.now().strftime("%Y%m%d")
    filename = _clean_filename(f"REQ-{ped_file}-{date_str}-{client_name}") + ".pdf"
    filepath = os.path.join(folder, filename)

    pdf = pdfcanvas.Canvas(filepath, pagesize=landscape(A4))
    page_w, page_h = landscape(A4)
    margin_x = 10 * mm
    margin_y = 10 * mm
    content_w = page_w - (2 * margin_x)

    pdf.setTitle(f"Requisicao {ped_file} - Ferragens Pinheiro")
    pdf.setAuthor("Ferragens Pinheiro")
    pdf.setFillColor(C_PAGE_BG)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    client_data = client or {}
    current_top = page_h - margin_y
    gap_small = 6
    gap_medium = 8

    header_h = 78
    header_y = current_top - header_h
    brand_w = content_w * 0.40
    ped_w = content_w * 0.22
    middle_w = content_w - brand_w - ped_w - 12
    base_x = margin_x

    _draw_logo_area(pdf, base_x, header_y, brand_w, header_h)

    title_x = base_x + brand_w + 10
    _draw_text(pdf, "REQUISICAO", title_x + middle_w / 2, header_y + header_h - 20, 27, C_BRAND, bold=True, align="center")

    emission_value = req.get("emission_date") or datetime.now().isoformat()
    vendor_value = _safe_text(req.get("vendor_name"), "-")
    date_group_w = middle_w * 0.42
    vendor_group_w = middle_w * 0.58
    _draw_label_value(
        pdf,
        title_x,
        header_y + 8,
        date_group_w,
        28,
        "Data",
        _fmt_date(emission_value, datetime.now().strftime("%d/%m/%Y")),
        align="center",
        value_size=10.5,
    )
    _draw_label_value(
        pdf,
        title_x + date_group_w,
        header_y + 8,
        vendor_group_w,
        28,
        "Vendedor",
        vendor_value,
        align="center",
        value_size=10.5,
    )

    _draw_ped_box(pdf, base_x + brand_w + middle_w + 12, header_y + 14, ped_w, 42, _safe_text(ped_raw, "0"))

    current_top = header_y - gap_medium

    info_h = 42
    info_y = current_top - info_h
    _draw_round_box(pdf, margin_x, info_y, content_w, info_h, radius=10, fill_color=C_CARD_BG, stroke_color=C_BORDER)

    info_cells = [
        ("O.S No", _safe_text(req.get("os_number"), "-"), 0.16, C_TEXT),
        ("Prazo de Entrega", _fmt_date(req.get("delivery_date")), 0.17, C_TEXT),
        ("Retirada", _fmt_yes_no(req.get("retirada")), 0.13, C_BRAND),
        ("Entrega", _fmt_yes_no(req.get("entrega")), 0.13, C_BRAND),
        ("NF", _file_display_name(req.get("nf_attachment")), 0.13, C_TEXT),
        ("Contato", _format_phone(req.get("phone"), TOP_PHONE_FALLBACK), 0.17, C_GREEN if req.get("phone") else C_TEXT),
        ("Peso", _fmt_kg(req.get("weight")), 0.11, C_TEXT),
    ]
    cursor_x = margin_x
    pdf.saveState()
    pdf.setStrokeColor(C_BORDER)
    pdf.setLineWidth(0.7)
    for index, (_, _, ratio, _) in enumerate(info_cells):
        cell_w = content_w * ratio
        if index > 0:
            pdf.line(cursor_x, info_y, cursor_x, info_y + info_h)
        label, value, _, color = info_cells[index]
        _draw_label_value(pdf, cursor_x, info_y, cell_w, info_h, label, value, align="center", value_color=color, value_size=10)
        cursor_x += cell_w
    pdf.restoreState()

    current_top = info_y - gap_medium

    client_h = 48
    client_y = current_top - client_h
    _draw_round_box(pdf, margin_x, client_y, content_w, client_h, radius=10, fill_color=C_CARD_BG, stroke_color=C_BORDER)
    row_split_y = client_y + (client_h / 2)
    top_right_split_x = margin_x + (content_w * 0.58)
    bottom_left_split_x = margin_x + (content_w * 0.29)

    pdf.saveState()
    pdf.setStrokeColor(C_BORDER)
    pdf.setLineWidth(0.7)
    pdf.line(margin_x, row_split_y, margin_x + content_w, row_split_y)
    pdf.line(top_right_split_x, row_split_y, top_right_split_x, client_y + client_h)
    pdf.line(bottom_left_split_x, client_y, bottom_left_split_x, row_split_y)
    pdf.restoreState()

    client_display = _safe_text(client_data.get("name") or req.get("client_name"), "0")
    obra_display = _safe_text(req.get("obra"), "0")
    phone_display = _format_phone(req.get("phone") or client_data.get("phone"), "0")
    address_display = _safe_text(req.get("delivery_address"), "0")

    _draw_label_value(pdf, margin_x, row_split_y, top_right_split_x - margin_x, client_h / 2, "Cliente", client_display, align="left", value_size=10)
    _draw_label_value(pdf, top_right_split_x, row_split_y, margin_x + content_w - top_right_split_x, client_h / 2, "Obra", obra_display, align="left", value_size=10)
    _draw_label_value(pdf, margin_x, client_y, bottom_left_split_x - margin_x, client_h / 2, "Fone", phone_display, align="left", value_size=10)
    _draw_label_value(pdf, bottom_left_split_x, client_y, margin_x + content_w - bottom_left_split_x, client_h / 2, "Endereco a Entregar", address_display, align="left", value_size=10)

    current_top = client_y - gap_medium

    middle_h = 184
    middle_y = current_top - middle_h
    items_w = content_w * 0.47
    draw_w = content_w - items_w - 10
    items_x = margin_x
    draw_x = items_x + items_w + 10

    items_list = req.get("items") or []
    if not isinstance(items_list, list):
        items_list = []
    _draw_items_table(pdf, items_x, middle_y, items_w, middle_h, items_list)

    canvas_result = _render_canvas_to_png(canvas_json)
    _draw_preview_box(
        pdf,
        draw_x,
        middle_y,
        draw_w,
        middle_h,
        title="DESENHO",
        canvas_result=canvas_result,
    )

    current_top = middle_y - gap_medium

    bottom_h = 118
    bottom_y = current_top - bottom_h
    _draw_preview_box(pdf, margin_x, bottom_y, content_w, bottom_h, title=None, canvas_result=None)

    current_top = bottom_y - gap_small

    footer_h = 42
    footer_y = current_top - footer_h
    observation = obs or req.get("obs") or ""
    _draw_signature_and_obs(pdf, margin_x, footer_y, content_w, observation)

    if canvas_result:
        pdf.showPage()
        _draw_second_page(pdf, _safe_text(ped_raw, "0"), canvas_result)

    pdf.save()
    return filepath
