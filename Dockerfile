# Imagem oficial Python 3.12 leve
FROM python:3.12-slim

# Evitar criação de arquivos .pyc e garantir logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependências do sistema necessárias para compilação e fontes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o código-fonte, templates e a base de dados SQLite atual
COPY . /app/

# Criar pasta de uploads caso não exista
RUN mkdir -p /app/uploads

# Expor a porta padrão da aplicação
EXPOSE 8000

# Comando de inicialização do Uvicorn para produção
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
