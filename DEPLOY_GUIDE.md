# Guia de Publicação e Acesso do Sistema de Auditoria de Pessoal

Este guia apresenta as duas opções completas para disponibilizar o **Sistema de Auditoria de Pessoal** na internet para outros usuários, mantendo **100% da base de dados atualizada** (`auditoria_pessoal.db`).

---

## 🚀 Opção 1: Acesso Imediato pela Internet (Ativo Agora)

O sistema já está publicado e ativo em um link público seguro HTTPS:

- 🌐 **Link Público Ativo:** `https://navigate-seats-glen-niagara.trycloudflare.com`
- 📋 **Rol Nominal de Convocados (Certame 4):** `https://navigate-seats-glen-niagara.trycloudflare.com/modulo/relatorios/rol-convocados?id_certame=4`
- 📑 **Central de Relatórios:** `https://navigate-seats-glen-niagara.trycloudflare.com/modulo/relatorios?id_certame=4`
- 🔑 **Login:** `prof.jan100@gmail.com` | **Senha:** `123456`

### Como religar o acesso online no Windows com 1 clique:
Na pasta do projeto, basta dar um duplo clique no arquivo:
`iniciar_sistema_online.bat`

O script automaticamente:
1. Inicia o servidor local FastAPI (`uvicorn`) na porta 8000 se não estiver rodando.
2. Abre o túnel seguro Cloudflare HTTPS.
3. Salva o link no arquivo `LINK_ACESSO_INTERNET.txt` e abre o navegador automaticamente.

---

## 🐳 Opção 2: Publicação com Docker / Docker Compose

Para rodar em qualquer servidor VPS (Ubuntu, Debian, Windows Server, etc.) com persistência garantida:

```bash
# 1. Construir e subir o container em segundo plano
docker compose up -d --build

# 2. Verificar se está rodando
docker compose ps

# 3. Visualizar logs
docker compose logs -f
```

O arquivo `docker-compose.yml` já está configurado com os volumes:
- `./auditoria_pessoal.db:/app/auditoria_pessoal.db` (preserva todos os dados do banco)
- `./uploads:/app/uploads` (preserva todos os arquivos e PDFs enviados)

---

## ☁️ Opção 3: Publicação em Nuvem (Render / Railway / Fly.io)

### No Render.com (Gratuito):
1. Crie uma conta no [Render.com](https://render.com).
2. Conecte este repositório Git.
3. Escolha **Web Service**:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Em **Disks**, adicione um disco persistente (ou mantenha o arquivo `auditoria_pessoal.db` versionado no Git).
5. O Render publicará automaticamente um link definitivo `https://seu-sistema.onrender.com`.

### No Railway.app:
1. Suba o repositório no [Railway.app](https://railway.app).
2. O Railway detectará automaticamente o `Procfile` e o `requirements.txt` e disponibilizará o sistema online 24/7.
