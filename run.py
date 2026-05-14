"""
Ponto de entrada do servidor.
Execute: python run.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",   # acessível na rede local
        port=8000,
        reload=True,       # desativar em produção
    )
