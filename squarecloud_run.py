"""
Ponto de entrada para deploy na Square Cloud.
Substitui run.py (que tem lógica de venv Windows incompatível com Linux).
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port)
