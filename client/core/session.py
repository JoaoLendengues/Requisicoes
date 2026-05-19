class UserSession:
    """Singleton com dados do usuário autenticado."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._reset()
        return cls._instance

    def _reset(self):
        self.token: str      = ""
        self.user_id: int    = 0
        self.user_name: str  = ""
        self.user_code: str  = ""
        self.role: str       = ""
        self.whatsapp: str   = ""

    def login(self, data: dict):
        self.token      = data["access_token"]
        self.user_id    = data["user_id"]
        self.user_name  = data["user_name"]
        self.user_code  = data["user_code"]
        self.role       = data["role"]
        self.whatsapp   = data.get("whatsapp") or ""

    def logout(self):
        self._reset()

    @property
    def is_logged_in(self) -> bool:
        return bool(self.token)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_manager_or_admin(self) -> bool:
        return self.role in ("admin", "gerente")

    @property
    def can_access_order_center(self) -> bool:
        return self.role in ("admin", "gerente", "producao")

    @property
    def can_manage_users(self) -> bool:
        return self.role == "admin"

    @property
    def can_create(self) -> bool:
        return self.role in ("admin", "vendedor", "gerente")

    @property
    def can_update_status(self) -> bool:
        return True  # todos os perfis podem atualizar status conforme permissão do backend


session = UserSession()
