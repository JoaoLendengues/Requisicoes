from .database import SessionLocal
from .models.production_machine import MachineOperationalStatus, ProductionMachine
from .models.user import Role, User
from .services.auth_service import hash_password
from .services.text_normalizer import normalize_upper_required


PINHEIRO_MACHINES = (
    "MAQUINA DE TELA GALVANIZADA",
    "MAQUINA DE BOBINA",
    "PRENSA DE CUMEEIRA",
    "PERFILADEIRA TRAPEZIO",
    "SHEAR LINE",
    "DOBRADEIRA MECANICA",
    "ESTRIBADEIRA ACO 8",
    "ESTRIBADEIRA PRIMA 12R",
    "ESTRIBADEIRA EURA 16",
    "ESTRIBADEIRA EURA 20 V1",
)

AR_MACHINES = (
    "Guilhotina de 6000 newton modelo GHN 6013",
    "Guilhotina de 3000 newton modelo GHN 3010",
    "Guilhotina de 6000 newton modelo GHN 600611",
    "Dobradeira de 6000 newton modelo PDH 20060111",
    "Dobradeira de 6000 newton modelo PSH 60060",
    "Martelo de 3000 newton modelo PDM 100/125X3050MM",
    "Dobradeira de 3000 newton modelo PDM 60/75x3050mm",
    "Dobradeira de 3000 newton modelo PDM 60/75x3050",
    "Dobradeira de 3000 newton modelo PDM 60/75x3050",
    "Dobradeira de 3000 newton modelo PDM 60/75X3050",
    "PLASMA de 6000 quarks modelo QP 6030",
    "Laser de 3000 esab modelo FL 30.15",
    "Dobradeira Newton PSA 13530 (SIA)",
    "Dobradeira Newton PSA 13530 (SIA)",
    "Martelo Newton 17530 (SIA)",
    "Cortadeira Newton GHN 3010 (SIA)",
)


def _machine_display_name(index: int, name: str) -> str:
    return f"{index:02d} - {normalize_upper_required(name)}"


def seed_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.code == "1").first():
            return
        db.add(
            User(
                code="1",
                name="Administrador",
                email="admin@pinheiroferragens.com.br",
                hashed_password=hash_password("admin123"),
                role=Role.ADMIN,
                is_active=True,
            )
        )
        db.commit()
        print("[seed] Admin criado - codigo: 1 / senha: admin123")
    finally:
        db.close()


def seed_production_machines() -> None:
    db = SessionLocal()
    try:
        if db.query(ProductionMachine.id).first():
            return

        catalogs = {
            "Pinheiro Indústria": PINHEIRO_MACHINES,
            "A&R": AR_MACHINES,
        }
        for destination, names in catalogs.items():
            for index, name in enumerate(names, start=1):
                db.add(
                    ProductionMachine(
                        destination=destination,
                        name=_machine_display_name(index, name),
                        sort_order=index,
                        status=MachineOperationalStatus.FUNCIONANDO,
                    )
                )
        db.commit()
    finally:
        db.close()
