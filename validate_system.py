import requests
import sys

BASE_URL = "http://127.0.0.1:8000"
session = requests.Session()
session.cookies.set("user_session", "prof.jan100@gmail.com")

routes_to_test = [
    ("/", "Dashboard Geral"),
    ("/certames", "Lista de Certames"),
    ("/certames/novo", "Novo Certame"),
    ("/certames/1/wizard", "Fase Pré-Edital (Wizard)"),
    ("/certames/1/fase-oficial", "Fase Oficial (Dashboard)"),
    ("/certames/1/fase-oficial/parecer", "Parecer Técnico — Fase Oficial"),
    ("/certames/1/fase-oficial/gerar-relatorio-ia", "Gerar Relatório com IA"),
    ("/certames/1/acompanhamento", "Acompanhamento do Certame (Dashboard)"),
    ("/certames/1/vigencia", "Vigência do Certame"),
    ("/certames/1/expirado", "Concurso Expirado (Dossiê Consolidado)"),
    ("/certames/1/dossie", "Dossiê Pré-Edital"),
    ("/certames/1/dossie-fase-oficial", "Dossiê Fase Oficial"),
    ("/certames/1/dossie-geral", "Dossiê Geral do Certame"),
    ("/modulo/lotacionograma", "Módulo Lotacionograma Legal"),
    ("/modulo/concursos", "Módulo Ordem de Classificação"),
    ("/modulo/temporarios", "Módulo Contratos Temporários"),
    ("/modulo/afastamentos", "Módulo Afastamentos & Licenças"),
    ("/achados", "Matriz de Achados"),
    ("/normativos", "Normativos & Jurisprudência"),
    ("/usuarios", "Gestão de Acesso"),
    ("/repositorio", "Repositório Documental"),
    ("/importar", "Ingestão & Leitura IA"),
]

print("=" * 70)
print("     SUÍTE COMPLETA DE AUDITORIA E VALIDAÇÃO DO SISTEMA (SIAP)")
print("=" * 70)

sucessos = 0
falhas = 0

for path, label in routes_to_test:
    url = f"{BASE_URL}{path}"
    try:
        res = session.get(url, timeout=10)
        if res.status_code == 200:
            print(f"[OK 200]  - {label:<40} ({path})")
            sucessos += 1
        else:
            print(f"[ERRO {res.status_code}] - {label:<40} ({path})")
            falhas += 1
    except Exception as e:
        print(f"[FALHA REQUISIÇÃO] - {label:<40} ({path}): {e}")
        falhas += 1

print("-" * 70)
print(f"Resultado Final da Validação: {sucessos} Rotas Aprovadas / {falhas} Falhas")
print("=" * 70)

if falhas > 0:
    sys.exit(1)
