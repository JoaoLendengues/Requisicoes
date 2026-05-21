from .database import SessionLocal
from .models.user import User, Role
from .models.production_machine import ProductionMachine, MachineOperationalStatus
from .services.auth_service import hash_password


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
)


def _machine_display_name(index: int, name: str) -> str:
    return f"{index:02d} - {name}"


def seed_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.code == "1").first():
            return
        db.add(User(
            code="1",
            name="Administrador",
            email="admin@pinheiroferragens.com.br",
            hashed_password=hash_password("admin123"),
            role=Role.ADMIN,
            is_active=True,
        ))
        db.commit()
        print("[seed] Admin criado — código: 1 / senha: admin123")
    finally:
        db.close()


def seed_production_machines() -> None:
    db = SessionLocal()
    try:
        catalogs = {
            "Pinheiro Indústria": PINHEIRO_MACHINES,
            "A&R": AR_MACHINES,
        }
        machines = db.query(ProductionMachine).all()
        existing_by_order = {
            (machine.destination, int(machine.sort_order or 0)): machine
            for machine in machines
        }
        existing_by_name = {
            (machine.destination, machine.name): machine
            for machine in machines
        }
        changed = False
        for destination, names in catalogs.items():
            for index, name in enumerate(names, start=1):
                display_name = _machine_display_name(index, name)
                machine = existing_by_order.get((destination, index))
                if machine is None:
                    machine = existing_by_name.get((destination, display_name))

                if machine is not None:
                    if machine.name != display_name:
                        machine.name = display_name
                        changed = True
                    if int(machine.sort_order or 0) != index:
                        machine.sort_order = index
                        changed = True
                    if machine.status is None:
                        machine.status = MachineOperationalStatus.FUNCIONANDO
                        changed = True
                    continue

                machine = ProductionMachine(
                    destination=destination,
                    name=display_name,
                    sort_order=index,
                    status=MachineOperationalStatus.FUNCIONANDO,
                )
                db.add(machine)
                existing_by_order[(destination, index)] = machine
                existing_by_name[(destination, display_name)] = machine
                changed = True

        if changed:
            db.commit()
    finally:
        db.close()
