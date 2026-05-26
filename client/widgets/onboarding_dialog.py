"""
Guia rápido de boas-vindas — exibido no primeiro login por perfil.

Estrutura:
  OnboardingDialog(role, scale, parent)
    - Série de slides com ícone, título e descrição por role.
    - Navegação: Anterior / Próximo / Concluir.
    - Checkbox "Não mostrar novamente" (pré-marcado).
    - Salva o estado em settings.json via res.mark_guide_shown(role).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import theme
from ..core.resolution import res


# ── Conteúdo dos slides por perfil ───────────────────────────────────────────

_SLIDES: dict[str, list[dict]] = {
    "admin": [
        {
            "icon": "👋",
            "title": "Bem-vindo, Administrador!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil. Use os botões abaixo para navegar."
            ),
        },
        {
            "icon": "📋",
            "title": "Nova Requisição",
            "body": (
                "Clique em <b>Nova Requisição</b> na barra lateral para criar pedidos. "
                "Preencha PED, cliente, itens, prazo e observações. "
                "O PDF é gerado automaticamente ao salvar."
            ),
        },
        {
            "icon": "👥",
            "title": "Central de Usuários",
            "body": (
                "Em <b>Usuários</b>, cadastre, edite ou desative membros da equipe. "
                "Defina o nível de acesso de cada um: Vendedor, Gerente, Produção, "
                "Indústria ou Entrega."
            ),
        },
        {
            "icon": "⚙️",
            "title": "Configurações",
            "body": (
                "Em <b>Configurações</b> você gerencia o backup automático do banco, "
                "os fundos da tela de login, alertas de faturamento, "
                "alteração de senha e a aparência do sistema."
            ),
        },
        {
            "icon": "🖥️",
            "title": "Painel Técnico",
            "body": (
                "O <b>Painel Técnico</b> exibe indicadores de saúde do servidor: "
                "tempo de resposta, conexões ativas e histórico de erros. "
                "Use para monitorar a performance em tempo real."
            ),
        },
    ],
    "gerente": [
        {
            "icon": "👋",
            "title": "Bem-vindo, Gerente!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil."
            ),
        },
        {
            "icon": "📊",
            "title": "Dashboard",
            "body": (
                "O <b>Dashboard</b> reúne os principais indicadores: volume de requisições, "
                "prazos de entrega, status de produção e faturamentos pendentes. "
                "Visão geral rápida da operação."
            ),
        },
        {
            "icon": "📋",
            "title": "Nova Requisição",
            "body": (
                "Crie requisições em <b>Nova Requisição</b>. "
                "Como gerente, você também pode acompanhar e editar "
                "requisições de qualquer vendedor da equipe."
            ),
        },
        {
            "icon": "🔍",
            "title": "Histórico / Busca",
            "body": (
                "Em <b>Histórico</b>, filtre e pesquise todas as requisições por "
                "status, vendedor, cliente e período. "
                "Clique duas vezes em qualquer linha para abrir os detalhes completos."
            ),
        },
        {
            "icon": "⚙️",
            "title": "Configurações",
            "body": (
                "Em <b>Configurações</b>, ajuste o prazo de alerta de faturamento "
                "e personalize a escala e o tema da interface."
            ),
        },
    ],
    "vendedor": [
        {
            "icon": "👋",
            "title": "Bem-vindo ao Sistema de Requisições!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil de <b>Vendedor</b>."
            ),
        },
        {
            "icon": "📋",
            "title": "Nova Requisição",
            "body": (
                "Clique em <b>Nova Requisição</b> para criar um pedido. "
                "Preencha o PED, selecione o cliente, adicione os itens e defina o prazo. "
                "O PDF é salvo automaticamente na pasta da rede."
            ),
        },
        {
            "icon": "🔍",
            "title": "Histórico / Busca",
            "body": (
                "Em <b>Histórico</b> você encontra todas as suas requisições. "
                "Filtre por status, data ou cliente. "
                "Clique duas vezes em qualquer linha para abrir os detalhes."
            ),
        },
        {
            "icon": "🔔",
            "title": "Notificações",
            "body": (
                "O sino na barra lateral exibe alertas em tempo real: "
                "quando sua requisição entra em produção, é finalizada ou faturada. "
                "Um ponto vermelho indica notificações não lidas."
            ),
        },
    ],
    "producao": [
        {
            "icon": "👋",
            "title": "Bem-vindo — Produção A&R!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil de <b>Produção</b>."
            ),
        },
        {
            "icon": "🏭",
            "title": "Fila da A&R",
            "body": (
                "A tela <b>A&R</b> exibe todas as requisições encaminhadas para produção. "
                "Use as abas para ver pedidos aguardando recebimento, em produção, "
                "aguardando faturamento e já faturados."
            ),
        },
        {
            "icon": "✏️",
            "title": "Atualizar Status",
            "body": (
                "Dê um <b>duplo clique</b> em qualquer requisição para abri-la. "
                "Registre o recebimento, inicie a produção e finalize o pedido "
                "diretamente pela interface."
            ),
        },
        {
            "icon": "🔔",
            "title": "Notificações",
            "body": (
                "O sino na barra lateral envia alertas em tempo real "
                "quando novos pedidos chegam à fila da A&R "
                "ou quando há atualizações importantes."
            ),
        },
    ],
    "industria": [
        {
            "icon": "👋",
            "title": "Bem-vindo — Pinheiro Indústria!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil de <b>Indústria</b>."
            ),
        },
        {
            "icon": "🏭",
            "title": "Fila da Pinheiro Indústria",
            "body": (
                "A tela <b>Pinheiro Indústria</b> exibe todas as requisições "
                "destinadas à indústria. Acompanhe em tempo real os pedidos "
                "em cada etapa do processo."
            ),
        },
        {
            "icon": "✏️",
            "title": "Atualizar Status",
            "body": (
                "Dê um <b>duplo clique</b> em qualquer requisição para abri-la. "
                "Registre o recebimento, o andamento da produção e a finalização "
                "direto pela interface."
            ),
        },
        {
            "icon": "🔔",
            "title": "Notificações",
            "body": (
                "O sino na barra lateral avisa quando novos pedidos chegam à fila "
                "da Pinheiro Indústria. Mantenha o badge zerado "
                "lendo as notificações regularmente."
            ),
        },
    ],
    "entrega": [
        {
            "icon": "👋",
            "title": "Bem-vindo — Entrega A&R!",
            "body": (
                "Este guia rápido apresenta as principais seções disponíveis "
                "para o seu perfil de <b>Entrega</b>."
            ),
        },
        {
            "icon": "🏭",
            "title": "Fila de Recebimento",
            "body": (
                "A tela <b>A&R</b> exibe os pedidos aguardando recebimento e entrega. "
                "Use as abas para visualizar o status de cada pedido na fila."
            ),
        },
        {
            "icon": "✏️",
            "title": "Confirmar Recebimento",
            "body": (
                "Dê um <b>duplo clique</b> em um pedido para abri-lo e "
                "registrar o recebimento ou a entrega. "
                "Mantenha o status sempre atualizado para a equipe de vendas."
            ),
        },
        {
            "icon": "🔔",
            "title": "Notificações",
            "body": (
                "O sino na barra lateral envia alertas quando novos pedidos chegam à fila. "
                "Você também pode acompanhar o histórico completo em "
                "<b>Histórico / Busca</b>."
            ),
        },
    ],
}

# Fallback para roles desconhecidos
_SLIDES["default"] = _SLIDES["vendedor"]


# ── Helpers de estilo ─────────────────────────────────────────────────────────

def _rgba(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# ── Diálogo ───────────────────────────────────────────────────────────────────

class OnboardingDialog(QDialog):
    """
    Guia rápido de boas-vindas por perfil.

    Parâmetros
    ----------
    role : str
        Role do usuário logado (admin, gerente, vendedor, …).
    scale : float
        Fator de escala da interface.
    show_dont_show : bool
        Se True (padrão), exibe o checkbox "Não mostrar novamente".
        Passe False ao abrir manualmente via Configurações.
    parent : QWidget | None
        Janela pai para centralização.
    """

    def __init__(
        self,
        role: str,
        scale: float = 1.0,
        show_dont_show: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._role            = role
        self._scale           = scale
        self._show_dont_show  = show_dont_show
        self._slides          = _SLIDES.get(role) or _SLIDES["default"]
        self._current         = 0
        self._dot_labels: list[QLabel] = []
        self._setup_ui()
        self._go_to(0)

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        s = self._scale
        n = len(self._slides)

        self.setWindowTitle("Guia Rápido")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(True)
        self.setFixedWidth(max(520, int(660 * s)))
        self.setStyleSheet(f"background:{theme.CARD_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Cabeçalho ─────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(max(56, int(64 * s)))
        header.setStyleSheet(f"background:{theme.PRIMARY};")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(max(20, int(24 * s)), 0, max(20, int(24 * s)), 0)
        hlay.setSpacing(max(8, int(10 * s)))

        brand = QLabel("FERRAGENS PINHEIRO")
        brand.setStyleSheet(
            f"color:#FFFFFF; font-size:{max(10, int(11 * s))}pt;"
            f"font-weight:800; letter-spacing:1px; background:transparent;"
        )
        hlay.addWidget(brand)

        guide_lbl = QLabel("· Guia Rápido")
        guide_lbl.setStyleSheet(
            f"color:rgba(255,255,255,160); font-size:{max(9, int(10 * s))}pt;"
            f"font-weight:600; background:transparent;"
        )
        hlay.addWidget(guide_lbl)
        hlay.addStretch()

        self._counter_lbl = QLabel(f"1 de {n}")
        self._counter_lbl.setStyleSheet(
            f"color:rgba(255,255,255,180); font-size:{max(8, int(9 * s))}pt;"
            f"font-weight:600; background:transparent;"
        )
        hlay.addWidget(self._counter_lbl)

        root.addWidget(header)

        # ── Área de conteúdo ──────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background:{theme.CARD_BG};")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setMinimumHeight(max(220, int(260 * s)))
        clay = QVBoxLayout(content)
        clay.setContentsMargins(
            max(32, int(40 * s)), max(28, int(32 * s)),
            max(32, int(40 * s)), max(20, int(24 * s)),
        )
        clay.setSpacing(max(10, int(12 * s)))
        clay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"font-size:{max(32, int(40 * s))}pt; background:transparent;"
        )
        clay.addWidget(self._icon_lbl)

        self._title_lbl = QLabel()
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(13, int(15 * s))}pt;"
            f"font-weight:800; background:transparent;"
        )
        clay.addWidget(self._title_lbl)

        self._body_lbl = QLabel()
        self._body_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._body_lbl.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(10 * s))}pt;"
            f"font-weight:500; line-height:150%; background:transparent;"
        )
        clay.addWidget(self._body_lbl)

        root.addWidget(content)

        # ── Separador ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{theme.BORDER_COLOR}; border:none;")
        root.addWidget(sep)

        # ── Rodapé ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background:{theme.CONTENT_BG}; border-bottom-left-radius:12px;"
            f"border-bottom-right-radius:12px;"
        )
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        flay = QVBoxLayout(footer)
        flay.setContentsMargins(
            max(20, int(24 * s)), max(14, int(16 * s)),
            max(20, int(24 * s)), max(14, int(16 * s)),
        )
        flay.setSpacing(max(8, int(10 * s)))

        # Linha superior: dots + botões
        nav_row = QHBoxLayout()
        nav_row.setSpacing(max(6, int(8 * s)))

        # Dots de progresso
        dots_widget = QWidget()
        dots_widget.setStyleSheet("background:transparent;")
        dots_lay = QHBoxLayout(dots_widget)
        dots_lay.setContentsMargins(0, 0, 0, 0)
        dots_lay.setSpacing(max(5, int(6 * s)))
        dot_size = max(8, int(9 * s))
        for _ in range(n):
            dot = QLabel()
            dot.setFixedSize(dot_size, dot_size)
            dot.setStyleSheet(
                f"border-radius:{dot_size // 2}px;"
                f"background:{theme.BORDER_COLOR};"
            )
            dots_lay.addWidget(dot)
            self._dot_labels.append(dot)
        dots_lay.addStretch()
        nav_row.addWidget(dots_widget)
        nav_row.addStretch()

        # Botões de navegação
        btn_h = max(36, int(40 * s))
        btn_style_sec = (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
            f"  padding:0 {max(14, int(18 * s))}px;"
            f"  font-size:{max(9, int(10 * s))}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{theme.PRIMARY}; }}"
            f"QPushButton:disabled {{ background:#E5EAF2; color:#97A3B6; border-color:#E5EAF2; }}"
        )
        btn_style_pri = (
            f"QPushButton {{"
            f"  background:{theme.PRIMARY}; color:#FFFFFF; border:none; border-radius:10px;"
            f"  padding:0 {max(14, int(18 * s))}px;"
            f"  font-size:{max(9, int(10 * s))}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.PRIMARY_HOVER}; }}"
            f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
        )

        self._btn_prev = QPushButton("← Anterior")
        self._btn_prev.setFixedHeight(btn_h)
        self._btn_prev.setStyleSheet(btn_style_sec)
        self._btn_prev.clicked.connect(self._on_prev)
        nav_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Próximo →")
        self._btn_next.setFixedHeight(btn_h)
        self._btn_next.setStyleSheet(btn_style_pri)
        self._btn_next.clicked.connect(self._on_next)
        nav_row.addWidget(self._btn_next)

        flay.addLayout(nav_row)

        # Linha inferior: checkbox
        if self._show_dont_show:
            chk_style = (
                f"QCheckBox {{ font-size:{max(8, int(9 * s))}pt; color:{theme.TEXT_MEDIUM};"
                f"  spacing:6px; background:transparent; }}"
                f"QCheckBox::indicator {{"
                f"  width:{max(13, int(15 * s))}px; height:{max(13, int(15 * s))}px;"
                f"  border:1.5px solid {theme.BORDER_COLOR}; border-radius:3px;"
                f"  background:{theme.CARD_BG};"
                f"}}"
                f"QCheckBox::indicator:checked {{"
                f"  background:{theme.PRIMARY}; border-color:{theme.PRIMARY};"
                f"}}"
            )
            self._chk_dont_show = QCheckBox("Não mostrar novamente")
            self._chk_dont_show.setChecked(True)
            self._chk_dont_show.setStyleSheet(chk_style)
            flay.addWidget(self._chk_dont_show)
        else:
            self._chk_dont_show = None

        root.addWidget(footer)

    # ── Navegação ─────────────────────────────────────────────────────────────

    def _go_to(self, index: int) -> None:
        n = len(self._slides)
        self._current = max(0, min(index, n - 1))
        slide = self._slides[self._current]

        self._icon_lbl.setText(slide["icon"])
        self._title_lbl.setText(slide["title"])
        self._body_lbl.setText(slide["body"])
        self._counter_lbl.setText(f"{self._current + 1} de {n}")

        # Dots
        dot_size = self._dot_labels[0].width() if self._dot_labels else 8
        for i, dot in enumerate(self._dot_labels):
            if i == self._current:
                dot.setStyleSheet(
                    f"border-radius:{dot_size // 2}px; background:{theme.PRIMARY};"
                )
            else:
                dot.setStyleSheet(
                    f"border-radius:{dot_size // 2}px; background:{theme.BORDER_COLOR};"
                )

        # Botões
        self._btn_prev.setEnabled(self._current > 0)
        is_last = self._current == n - 1
        self._btn_next.setText("Concluir ✓" if is_last else "Próximo →")

    def _on_prev(self) -> None:
        self._go_to(self._current - 1)

    def _on_next(self) -> None:
        if self._current >= len(self._slides) - 1:
            self._finish()
        else:
            self._go_to(self._current + 1)

    def _finish(self) -> None:
        if self._chk_dont_show is not None and self._chk_dont_show.isChecked():
            res.mark_guide_shown(self._role)
        self.accept()

    def closeEvent(self, event):
        """Ao fechar pelo X: respeita o checkbox se marcado."""
        if self._chk_dont_show is not None and self._chk_dont_show.isChecked():
            res.mark_guide_shown(self._role)
        super().closeEvent(event)
