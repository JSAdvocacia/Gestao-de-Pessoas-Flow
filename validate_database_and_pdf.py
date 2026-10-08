import sys
from models import SessionLocal, CertameAbertura, CertameFaseOficial, ParecerOficial, Concurso, Cargo, Candidato, CertameAcompanhamentoAto, Lotacionograma, AuditoriaAchado, CertameVigenciaAto
from pdf_generator import PDFTextGenerator
import os

db = SessionLocal()

print("=" * 70)
print("     AUDITORIA DE BANCO DE DADOS E GERAÇÃO DE DOSSIÊS / PDFS")
print("=" * 70)

certames = db.query(CertameAbertura).all()
print(f"[BD] Total de Certames Cadastrados: {len(certames)}")
for c in certames:
    candidatos_cnt = db.query(Candidato).count()
    cargos_cnt = db.query(Cargo).count()
    achados_cnt = db.query(AuditoriaAchado).count()
    vigencia_cnt = db.query(CertameVigenciaAto).filter_by(id_certame=c.id_certame).count()
    print(f"  • Certame #{c.id_certame} - {c.numero_certame} ({c.municipio}): {cargos_cnt} cargos, {candidatos_cnt} candidatos, {achados_cnt} achados, {vigencia_cnt} atos de vigência.")

# Test PDF Generation
certame = certames[0]
parecer_oficial = certame.parecer_oficial

if certame and parecer_oficial:
    pasta = os.path.join("uploads", "certames", f"certame_{certame.id_certame}")
    os.makedirs(pasta, exist_ok=True)
    res_pdf = PDFTextGenerator.gerar_pdf_parecer_fase_oficial(certame, parecer_oficial, pasta)
    print(f"[PDF] Parecer Técnico da Fase Oficial PDF gerado com sucesso: {res_pdf['nome_arquivo']} ({res_pdf['tamanho_bytes']} bytes)")

db.close()
print("=" * 70)
print("     AUDITORIA DE BANCO DE DADOS E PDF CONCLUÍDA COM SUCESSO!")
print("=" * 70)
