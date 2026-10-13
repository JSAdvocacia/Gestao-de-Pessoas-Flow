import csv
import datetime
from datetime import date
from models import (
    SessionLocal, init_db, Usuario, CertameAbertura, CertameFaseOficial, ParecerOficial,
    Concurso, Cargo, Candidato, Lotacionograma, ConcursoVaga
)
from seed import seed_database
from audit_engine import AuditEngine

def parse_date(d_str):
    if not d_str or not d_str.strip():
        return None
    d_str = d_str.strip()
    if d_str == '18/011/2024':
        return datetime.date(2024, 11, 18)
    if d_str == '057/2024':
        return datetime.date(2024, 10, 2)
    try:
        return datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
    except Exception:
        try:
            return datetime.datetime.strptime(d_str, '%d/%m/%Y').date()
        except Exception:
            return None

print("=" * 70)
print("     RESTAURANDO BASE DE DADOS INTEGRAL DO SISTEMA (SIAP)")
print("=" * 70)

# 1. Re-inicializar tabelas do banco
seed_database()

db = SessionLocal()

# 2. Criar Usuário Mestre
master = db.query(Usuario).filter_by(email="prof.jan100@gmail.com").first()
if not master:
    master = Usuario(
        email="prof.jan100@gmail.com",
        nome="Prof. Jansen Pinho",
        senha_hash=None,
        perfil="ADMIN_MASTER",
        primeiro_acesso=False
    )
    db.add(master)
    db.commit()

# 3. Criar Certame Principal (Concurso Público 001/2022 - Pontes e Lacerda - MT)
certame = db.query(CertameAbertura).first()
if not certame:
    certame = CertameAbertura(
        modalidade="CONCURSO_PUBLICO",
        numero_certame="001/2022",
        ano=2022,
        municipio="Pontes e Lacerda - MT",
        orgao_solicitante="Prefeitura Municipal de Pontes e Lacerda - MT",
        prefeito_ordenador="Alcino Pereira Barcelos",
        secretario_solicitante="Anderson da Silva Lima",
        contador_responsavel="Márcio Henrique Tosti – CRC nº 7815/O",
        banca_examinadora="IMPÉRIO ASSESSORIA E CONCURSOS LTDA",
        lei_autorizadora="Lei Municipal nº 1.948 de 22/10/2018",
        leis_carreira="Lei Complementar nº 63/2008 e Lei Complementar nº 92/2010"
    )
    db.add(certame)
    db.commit()
    db.refresh(certame)

# 4. Criar Fase Oficial
fase_oficial = certame.fase_oficial
if not fase_oficial:
    fase_oficial = CertameFaseOficial(
        id_certame=certame.id_certame,
        data_publicacao_edital=date(2022, 5, 10),
        numero_diario_oficial_edital="AMM nº 3.982/2022",
        data_homologacao_inscricoes=date(2022, 6, 15),
        total_inscritos=759,
        total_isencoes_deferidas=42,
        data_realizacao_provas=date(2022, 7, 20),
        data_homologacao_resultado_final=date(2022, 10, 14),
        numero_decreto_homologacao="Decreto Municipal nº 148/2022",
        status_fase_oficial="HOMOLOGADO_FINAL"
    )
    db.add(fase_oficial)
    db.commit()

# 5. Importar Matriz de Provimentos de attached_provimento.csv
concurso = db.query(Concurso).filter_by(id_certame=certame.id_certame).first()
if not concurso:
    concurso = Concurso(
        id_certame=certame.id_certame,
        numero_edital="001/2022",
        ano_edital=2022,
        data_homologacao=date(2022, 10, 14),
        data_validade_final=date(2024, 10, 14),
        status="VIGENTE"
    )
    db.add(concurso)
    db.commit()
    db.refresh(concurso)

cargos_dict = {}
candidatos_to_add = []

with open('attached_provimento.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cargo_nome = row.get('Descricao Cargo', '').strip()
        if not cargo_nome:
            continue
        
        if cargo_nome not in cargos_dict:
            cg = db.query(Cargo).filter_by(nome_cargo=cargo_nome).first()
            if not cg:
                cg = Cargo(
                    codigo_cargo=f"CARGO-{len(cargos_dict)+1:03d}",
                    nome_cargo=cargo_nome,
                    nivel_escolaridade="Superior" if "Nível Superior" in cargo_nome else ("Técnico" if "Técnico" in cargo_nome else "Médio"),
                    regime_juridico="Estatutário"
                )
                db.add(cg)
                db.commit()
                db.refresh(cg)
                
                lot = Lotacionograma(
                    id_cargo=cg.id_cargo,
                    lei_criacao="Lei Municipal nº 1.948/2018",
                    ano_vigencia=2026,
                    vagas_criadas_lei=10,
                    vagas_ocupadas_oficial=5,
                    vagas_disponiveis_oficial=5
                )
                db.add(lot)

                v_conc = ConcursoVaga(
                    id_concurso=concurso.id_concurso,
                    id_cargo=cg.id_cargo,
                    vagas_imediatas_edital=1,
                    vagas_cr=10
                )
                db.add(v_conc)
                db.commit()
            cargos_dict[cargo_nome] = cg.id_cargo

        cg_id = cargos_dict[cargo_nome]

        inscricao = row.get('Inscricao', '').strip()
        nome = row.get('Nome', '').strip()
        class_geral = int(row.get('ClassGeral', 0)) if row.get('ClassGeral', '').strip().isdigit() else 1
        situacao = row.get('SituacaoFinal', '').strip().upper()
        edital_conv = row.get('Edital deConvocação', '').strip()
        dt_posse = parse_date(row.get('Data da Posse', ''))
        dt_exonera = parse_date(row.get('Data Exoneração', ''))
        edital_desist = row.get('Edital Homologação Desistencia ', '').strip() or row.get('Edital Homologação Desistencia', '').strip()
        sub_judice = row.get('Posse sob Júdice', '').strip().upper()

        if dt_exonera or row.get('Data Exoneração', '').strip():
            status_atual = "EXCLUÍDO / EXONERADO"
        elif edital_desist:
            status_atual = "DESISTENTE / RENÚNCIA"
        elif dt_posse or row.get('Data da Posse', '').strip():
            status_atual = "EMPOSSADO (EXERCÍCIO)"
        elif edital_conv:
            status_atual = "CONVOCADO"
        elif situacao == "APROVADO":
            status_atual = "APROVADO (AGUARDANDO CONVOCAÇÃO)"
        else:
            status_atual = "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

        cand = Candidato(
            id_certame=certame.id_certame,
            id_concurso=concurso.id_concurso,
            id_cargo=cg_id,
            cpf=f"000.{inscricao[:3] if len(inscricao)>=3 else '000'}.{inscricao[3:6] if len(inscricao)>=6 else '000'}-00",
            nome_completo=nome,
            classificacao_original=class_geral,
            classificacao_efetiva=class_geral,
            status_atual=status_atual,
            edital_convocacao=edital_conv,
            data_posse=dt_posse,
            data_exoneracao=dt_exonera,
            edital_desistencia=edital_desist,
            sub_judice=sub_judice
        )
        candidatos_to_add.append(cand)

    db.add_all(candidatos_to_add)
    db.commit()

# 6. Executar motor de auditoria e IA
engine = AuditEngine(db)
engine.importar_dados_fase_oficial_para_acompanhamento(certame.id_certame)
engine.gerar_relatorio_ia_completo(certame.id_certame)
engine.executar_auditoria_completa()

db.close()

print("=" * 70)
print(f"     SUCESSO: BASE INTEGRAL RESTAURADA COM {len(cargos_dict)} CARGOS E {len(candidatos_to_add)} CANDIDATOS!")
print("=" * 70)
