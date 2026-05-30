class UserSession:
    """Singleton com dados do usuario autenticado."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._reset()
        return cls._instance

    def _reset(self):
        self.token: str = ""
        self.user_id: int = 0
        self.user_name: str = ""
        self.user_code: str = ""
        self.role: str = ""
        self.whatsapp: str = ""

    def login(self, data: dict):
        self.token = data["access_token"]
        self.update_profile(data)

    def update_profile(self, data: dict):
        if not isinstance(data, dict):
            return
        self.user_id = int(data.get("user_id") or data.get("id") or self.user_id or 0)
        self.user_name = str(data.get("user_name") or data.get("name") or self.user_name or "")
        self.user_code = str(data.get("user_code") or data.get("code") or self.user_code or "")
        self.role = str(data.get("role") or self.role or "")
        self.whatsapp = str(
            data.get("whatsapp")
            or data.get("contact")
            or data.get("phone")
            or self.whatsapp
            or ""
        )

    def logout(self):
        self._reset()

    # ── Estado de autenticação ────────────────────────────────────────────────

    @property
    def is_logged_in(self) -> bool:
        return bool(self.token)

    # ── Grupos de role ────────────────────────────────────────────────────────

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_manager_or_admin(self) -> bool:
        return self.role in ("admin", "gerente")

    @property
    def is_view_only(self) -> bool:
        """A&R e Indústria sempre abrem formulários em modo somente leitura."""
        return self.role in ("producao", "industria", "entrega")

    @property
    def is_production_team(self) -> bool:
        return self.role in ("producao", "industria", "entrega")

    # ── Acesso às telas ───────────────────────────────────────────────────────

    @property
    def can_access_dashboard(self) -> bool:
        return self.role in ("admin", "gerente")

    @property
    def can_access_technical_panel(self) -> bool:
        return self.role == "admin"

    @property
    def can_access_order_center(self) -> bool:
        """Todos os roles acessam a Central de Pedidos."""
        return self.role in ("admin", "gerente", "vendedor", "producao", "industria", "entrega")

    @property
    def can_access_ar(self) -> bool:
        """Tela da A&R: admin, gerente e role A&R (producao)."""
        return self.role in ("admin", "gerente", "producao", "entrega")

    @property
    def can_access_industria(self) -> bool:
        """Tela da Pinheiro Indústria: admin, gerente e role Indústria."""
        return self.role in ("admin", "gerente", "industria")

    @property
    def can_access_settings(self) -> bool:
        """Todos acessam configurações (com seções diferentes por role)."""
        return True

    @property
    def can_manage_users(self) -> bool:
        return self.role == "admin"

    @property
    def filters_own_requisitions(self) -> bool:
        """Todos os perfis veem todas as requisições."""
        return False

    # ── Ações sobre requisições ───────────────────────────────────────────────

    @property
    def can_create(self) -> bool:
        return True  # Todos acessam o formulário; A&R e Indústria em modo leitura

    @property
    def can_update_status(self) -> bool:
        return self.role in ("admin", "gerente", "vendedor")

    # ── Destinos de produção visíveis ─────────────────────────────────────────

    @property
    def visible_production_destinations(self) -> tuple[str, ...]:
        if self.role in ("producao", "entrega"):
            return ("A&R",)
        if self.role == "industria":
            return ("Pinheiro Indústria",)
        if self.role in ("admin", "gerente"):
            return ("A&R", "Pinheiro Indústria")
        return ()  # vendedor não acessa telas de produção

    # ── Modo de abertura do formulário ────────────────────────────────────────

    def should_open_requisition_read_only(self, source: str = "") -> bool:
        """A&R e Indústria têm acesso total na Central de Pedidos;
        em qualquer outra origem (histórico, sidebar) abrem em leitura."""
        if source == "order_center":
            return False
        return self.is_view_only

    # ── Seções visíveis nas Configurações ─────────────────────────────────────

    @property
    def settings_show_connection(self) -> bool:
        """Conexão com servidor: somente admin."""
        return self.role == "admin"

    @property
    def settings_show_billing(self) -> bool:
        """Alertas de faturamento: admin e gerente."""
        return self.role in ("admin", "gerente")

    @property
    def settings_show_appearance(self) -> bool:
        """Aparência (escala): todos."""
        return True

    @property
    def settings_show_updates(self) -> bool:
        """Atualizações: todos."""
        return True

    @property
    def settings_show_login_backgrounds(self) -> bool:
        """Fundo da tela de login: somente admin."""
        return self.role == "admin"

    @property
    def settings_show_backup(self) -> bool:
        """Backup do banco de dados: somente admin."""
        return self.role == "admin"


session = UserSession()
