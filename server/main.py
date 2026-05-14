from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, Base
from .models import user, client, requisition  # garante registro dos modelos no SQLAlchemy
from .routers import auth, users, clients, requisitions
from .seed import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_admin()
    yield


app = FastAPI(
    title="Ferragens Pinheiro — API de Requisições",
    version="1.0.0",
    description="API REST para gestão de requisições de obras. Compatível com clientes Java via endpoints padrão.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # restringir em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(requisitions.router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "service": "Ferragens Pinheiro API"}
