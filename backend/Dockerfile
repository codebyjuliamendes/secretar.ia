# Imagem base leve do Python 3.12
FROM python:3.12-slim

# Configura variáveis do terminal
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define diretório de trabalho
WORKDIR /app

# Instala curl e dependências de build básicas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências do Python diretamente (sem travar em gerenciadores)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi==0.140.13 \
    uvicorn==0.51.0 \
    prisma==0.15.0 \
    pydantic==2.13.4 \
    python-dotenv==1.2.2 \
    httpx==0.28.1

# Copia todo o código do backend para o container
COPY . .

# Roda o gerador do Prisma Client Python na inicialização do container
# O gerador criará a pasta local 'generated_prisma' dentro de /app
RUN python -m prisma generate --schema=prisma/schema.prisma

# Expõe a porta do FastAPI
EXPOSE 8000

# Executa o uvicorn apontando para o app principal
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
