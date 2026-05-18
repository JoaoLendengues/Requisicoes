"""Dashboard — acesso restrito a gerente e admin."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QColor

from ..core import theme
from ..core.resolution import res
from ..api import client as api


class DashWorker(QObject):
    result   = Signal(list)
    error    = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.list_requisitions(limit=200))
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


def _card(color: str, title: str, value: str, scale: float) -> QFrame:
    card = QFrame()
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(12)
    shadow.setOffset(0, 3)
    shadow.setColor(QColor(0, 0, 0, 25))
    card.setGraphicsEffect(shadow)
    card.setStyleSheet(
        f"background:{color}; border-radius:10px;"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(max(14,int(18*scale)), max(12,int(16*scale)),
                               max(14,int(18*scale)), max(12,int(16*scale)))

    lbl_title = QLabel(title.upper())
    lbl_title.setStyleSheet(
        f"color:rgba(255,255,255,0.85); font-size:{max(8,int(9*scale))}pt;"
        f"font-weight:bold; border:none; background:transparent;"
    )
    lbl_val = QLabel(value)
    lbl_val.setStyleSheet(
        f"color:#fff; font-size:{max(20,int(26*scale))}pt;"
        f"font-weight:bold; border:none; background:transparent;"
    )
    layout.addWidget(lbl_title)
    layout.addWidget(lbl_val)
    return card


class DashboardView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12,int(16*s)), max(12,int(16*s)),
                                   max(12,int(16*s)), max(12,int(16*s)))
        layout.setSpacing(max(12,int(16*s)))

        title = QLabel("📊 DASHBOARD")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(14,int(17*s))}pt; font-weight:bold;"
        )
        layout.addWidget(title)

        # Cards de contagem
        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(max(10,int(12*s)))
        layout.addLayout(self.cards_layout)

        self._stat_cards: dict[str, QLabel] = {}
        card_defs = [
            ("total",         theme.PRIMARY,                       "Total de Requisições"),
            ("em_andamento",  theme.STATUS_COLORS["em_andamento"], "Em Andamento"),
            ("aguardando_recebimento", theme.STATUS_COLORS["aguardando_recebimento"], "Aguardando Recebimento"),
            ("em_producao",   theme.STATUS_COLORS["em_producao"],  "Em Produção"),
            ("cancelada",     theme.STATUS_COLORS["cancelada"],    "Canceladas"),
        ]

        for i, (key, color, label) in enumerate(card_defs):
            card = QFrame()
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(12)
            shadow.setOffset(0, 3)
            shadow.setColor(QColor(0, 0, 0, 25))
            card.setGraphicsEffect(shadow)
            card.setStyleSheet(f"background:{color}; border-radius:10px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(max(14,int(18*s)), max(12,int(16*s)),
                                   max(14,int(18*s)), max(12,int(16*s)))
            lbl_t = QLabel(label.upper())
            lbl_t.setStyleSheet(
                f"color:rgba(255,255,255,0.85); font-size:{max(7,int(9*s))}pt;"
                f"font-weight:bold; border:none; background:transparent;"
            )
            lbl_v = QLabel("—")
            lbl_v.setStyleSheet(
                f"color:#fff; font-size:{max(18,int(24*s))}pt;"
                f"font-weight:bold; border:none; background:transparent;"
            )
            cl.addWidget(lbl_t)
            cl.addWidget(lbl_v)
            self._stat_cards[key] = lbl_v
            self.cards_layout.addWidget(card, 0, i)   # 4 cards numa linha só

        # Tabela de requisições recentes
        lbl_rec = QLabel("🧾 Requisições Recentes")
        lbl_rec.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(11,int(13*s))}pt; font-weight:bold;"
        )
        layout.addWidget(lbl_rec)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["PED", "OBRA", "DATA", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(
            f"QTableWidget {{ border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"font-size:{max(9,int(10*s))}pt; }}"
            f"QHeaderView::section {{ background:{theme.TABLE_HEADER_BG}; color:#fff;"
            f"padding:6px; font-weight:bold; border:none; border-right:1px solid {theme.TABLE_BORDER}; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )
        layout.addWidget(self.table)

    def refresh(self):
        worker = DashWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.finished.connect(thread.quit)
        thread.start()
        self._threads.append((thread, worker))

    def _populate(self, reqs: list):
        # Contagens
        counts: dict[str, int] = {}
        for r in reqs:
            s = r.get("status", "")
            counts[s] = counts.get(s, 0) + 1

        self._stat_cards["total"].setText(str(len(reqs)))
        for key, lbl in self._stat_cards.items():
            if key != "total":
                lbl.setText(str(counts.get(key, 0)))

        # Tabela — 20 mais recentes
        self.table.setRowCount(0)
        for req in reqs[:20]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vals = [
                req.get("ped_number", ""),
                req.get("obra") or "—",
                str(req.get("emission_date", ""))[:10],
                req.get("status", ""),
            ]
            for col, val in enumerate(vals):
                if col == 3:
                    lbl = QLabel(theme.STATUS_LABELS.get(val, val))
                    color = theme.STATUS_COLORS.get(val, "#6B7280")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl.setStyleSheet(
                        f"background:{color}; color:#fff; border-radius:4px;"
                        f"font-weight:bold; padding:2px 6px; font-size:{max(8,int(9*self.scale))}pt;"
                    )
                    self.table.setCellWidget(row, col, lbl)
                else:
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, item)
