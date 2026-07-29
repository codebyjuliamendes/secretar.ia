import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from prisma import Prisma

# Carrega variáveis de ambiente
load_dotenv()

from db import db
from core.queue import worker_loop
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Conecta no banco ao iniciar
    await db.connect()
    # Inicia o worker de fila em background
    app.state.worker_task = asyncio.create_task(worker_loop())
    yield
    # Finaliza o worker
    app.state.worker_task.cancel()
    # Desconecta ao finalizar
    if db.is_connected():
        await db.disconnect()

app = FastAPI(
    title="Secretar.ia API",
    description="Backend de Automação e Inteligência Artificial para Clínicas de Estética",
    version="1.0.0",
    lifespan=lifespan
)

# Configura CORS para permitir chamadas do Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Em prod, colocar o domínio da Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Importa e registra as rotas
from routes import n8n, billing, marketing, admin, clinic

app.include_router(n8n.router, prefix="/api/n8n", tags=["n8n"])
app.include_router(billing.router, prefix="/api/webhooks", tags=["billing"])
app.include_router(marketing.router, prefix="/api/marketing", tags=["marketing"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(clinic.router, prefix="/api/clinic", tags=["clinic"])

@app.get("/")
def read_root():
    return {"message": "Secretar.ia FastAPI Backend is running smoothly!"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
