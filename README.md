# 🛡️ SIAP / AUDIT-FLOW — Sistema Integrado de Auditoria de Pessoal & Controle Interno Municipal

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-00965e)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.0-38bdf8)
![Chart.js](https://img.shields.io/badge/Chart.js-4.0-ff6384)
![License](https://img.shields.io/badge/License-Proprietary-emerald)

> **Sistema de Automação de Auditoria de Provimentos, Vinculação Editalícia, Lotacionograma Legal e Inteligência Artificial para Emissão de Pareceres Técnicos do Controle Interno Municipal (Conforme Normas do TCE-MT e CF/88 Art. 37).**

---

## 📌 Funcionalidades Principais

- **📊 Dashboard Executivo de Acompanhamento do Certame:**
  - Gráficos dinâmicos em Chart.js: **Status Global de Vagas (Rosca)** e **Curva de Preenchimento por Cargo (Linha/Barras)**.
  - Indicadores em tempo real (Vagas Edital, Convocados, Empossados, Em Trâmite, Desistências/Fim de Fila, Saldo Livre).
  - Badge de **Taxa Global de Posse (%)**.

- **🤖 Emissão de Relatório Técnico com Inteligência Artificial:**
  - Botão *"Gerar relatório com IA"* que lê o banco de dados, compila todas as métricas do Dashboard de Provimentos, audita ativamente inconformidades e gera um parecer técnico fundamentado.

- **⚖️ Módulo de Auditoria & Achados de Controle Interno:**
  - Verificação de ordem de convocação e vacâncias.
  - Alerta automatizado para **posses realizadas após a expiração da vigência do certame**.
  - Validação de prazo legal para posse e perdas de vaga.

- **📁 Dossiês Probatórios Regulamentares (TCE-MT):**
  - Geração automatizada dos Dossiês Pré-Edital, Fase Oficial e Dossiê Geral em formato impresso/PDF.

- **🏛️ Gestão de Lotacionograma & Provimentos:**
  - Confronto direto de vagas por lei vs. vagas oferecidas no edital vs. provimentos efetivos.

---

## 🛠️ Tecnologias Utilizadas

- **Backend:** Python 3, FastAPI, SQLAlchemy, Uvicorn, Jinja2.
- **Frontend:** HTML5, TailwindCSS (CDN), FontAwesome 6, Chart.js.
- **Banco de Dados:** SQLite (ORM via SQLAlchemy).
- **Geração de Documentos:** ReportLab / PDFGenerator.

---

## 🚀 Como Executar o Projeto Localmente

### 1. Clonar o repositório
```bash
git clone https://github.com/SEU_USUARIO/sistema-auditoria-pessoal.git
cd sistema-auditoria-pessoal
```

### 2. Criar e ativar o ambiente virtual
```bash
python -m venv venv
# No Windows:
.venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install -r requirements.txt
```

### 4. Inicializar o Banco de Dados (Seed)
```bash
python seed.py
```

### 5. Iniciar o Servidor
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse no navegador: **`http://127.0.0.1:8000`**

- **Credenciais de Acesso Mestre:**
  - **Email:** `prof.jan100@gmail.com`
  - **Senha:** `123`

---

## 🧪 Suíte de Testes e Validação

Para rodar a validação automatizada de todas as 21 rotas do sistema:
```bash
python validate_system.py
```

---

## 📝 Licença

Desenvolvido para auditoria e controle interno de pessoal. Todos os direitos reservados.
