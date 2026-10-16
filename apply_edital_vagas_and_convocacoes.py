import os
import re
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, CertameAbertura, Concurso, ConcursoVaga, Cargo, Lotacionograma, Candidato, Convocacao, MovimentacaoCandidato

DATABASE_URL = "sqlite:///auditoria_pessoal.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("=== INICIANDO AJUSTE DE VAGAS EDITALÍCIAS E CONVOCAÇÕES DO PROCESSO SELETIVO 001/2023 ===")

# 1. Configurar Certame 2 e Concurso 4
certame = db.query(CertameAbertura).filter_by(id_certame=2).first()
if not certame:
    raise Exception("Certame 2 não encontrado!")

concurso = db.query(Concurso).filter_by(id_concurso=4).first()
if not concurso:
    concurso = db.query(Concurso).filter_by(id_certame=2).first()

if not concurso:
    raise Exception("Concurso 4 não encontrado!")

concurso.data_homologacao = datetime.date(2024, 1, 11)
concurso.prazo_validade_meses = 12
concurso.data_validade_final = datetime.date(2025, 1, 11)
concurso.status = "EXPIRADO"
db.commit()
print(f"Concurso #{concurso.id_concurso} atualizado: Homologado em {concurso.data_homologacao}, validade até {concurso.data_validade_final}, status: {concurso.status}")

# 2. Assegurar Cargos e Lotacionograma
cargos_def = [
    # (Nome Cargo, Codigo, Nivel, Vagas Edital, Vagas Lei Lotacionograma, Vagas Ocupadas)
    ("ASSISTENTE ADMINISTRATIVO", "ASSIST-824", "Médio", 0, 62, 34),
    ("ASSISTENTE SOCIAL", "ASSIST-376", "Superior", 0, 11, 8),
    ("AUXILIAR DE CONSULTÓRIO DENTÁRIO", "AUXILI-128", "Médio", 0, 15, 9),
    ("BIOQUÍMICO/FARMACÊUTICO", "BIOQUM-790", "Superior", 0, 10, 7),
    ("ENFERMEIRO - ZONA RURAL", "ENFERM-5323", "Superior", 0, 10, 5),
    ("ENFERMEIRO - ZONA URBANA", "ENFERM-9455", "Superior", 1, 25, 15),
    ("FISIOTERAPEUTA", "FISIOT-049", "Superior", 0, 10, 6),
    ("FONOAUDIÓLOGO", "FONOAU-841", "Superior", 0, 2, 1),
    ("MÉDICO (20 HORAS)", "MDICO2-149", "Superior", 0, 15, 1),
    ("MÉDICO (40 HORAS)", "MDICO4-241", "Superior", 3, 23, 11),
    ("MÉDICO VETERINÁRIO", "MDICOV-055", "Superior", 0, 2, 0),
    ("NUTRICIONISTA", "NUTRIC-026", "Superior", 0, 2, 0),
    ("ODONTÓLOGO", "ODONTL-660", "Superior", 1, 18, 13),
    ("PEDAGOGO", "PEDAGO-315", "Superior", 0, 1, 0),
    ("PROFESSOR DE EDUCAÇÃO FÍSICA", "PROFES-848", "Superior", 0, 2, 1),
    ("PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA RURAL", "PROFES-INF-ZR", "Superior", 0, 20, 10),
    ("PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA URBANA", "PROFES-INF-ZU", "Superior", 1, 153, 87),
    ("PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA RURAL", "PROFES-3479", "Superior", 0, 20, 10),
    ("PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA URBANA", "PROFES-1563", "Superior", 1, 194, 113),
    ("PROFESSOR LÍNGUA INGLESA - ZONA RURAL", "PROFES-ING-ZR", "Superior", 0, 5, 2),
    ("PROFESSOR LÍNGUA INGLESA - ZONA URBANA", "PROFES-ING-ZU", "Superior", 0, 15, 5),
    ("PSICÓLOGO", "PSICLO-291", "Superior", 0, 12, 6),
    ("TAE - MULTIMEIOS DIDÁTICOS", "TAE-MULT-ZU", "Médio", 1, 25, 11),
    ("TAE - TÉCNICO EM ADMINISTRAÇÃO ESCOLAR", "TAE-ADM-ZU", "Médio", 1, 21, 15),
    ("TAE - TÉCNICO EM DESENVOLVIMENTO INFANTIL", "TAE-DES-ZU", "Médio", 1, 253, 64),
    ("TÉCNICO EM ENFERMAGEM - ZONA RURAL", "TCNICO-ENF-ZR", "Técnico", 0, 10, 5),
    ("TÉCNICO EM ENFERMAGEM - ZONA URBANA", "TCNICO-8720", "Técnico", 0, 35, 35),
    ("TÉCNICO EM GESSO ORTOPÉDICO / HOSPITALAR", "TCNICO-944", "Técnico", 0, 1, 1),
    ("TÉCNICO EM HIGIENE DENTAL", "TCNICO-472", "Técnico", 0, 2, 1),
    ("TÉCNICO OPERACIONAL EM RAIO-X", "TCNICO-698", "Técnico", 0, 2, 2),
]

import unicodedata
def norm(s):
    return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII').upper().strip()

mapa_cargo_obj = {}
for nome_c, cod, niv, v_edital, v_lei, v_oc in cargos_def:
    n_n = norm(nome_c)
    # Procurar cargo existente
    cg = None
    for item in db.query(Cargo).all():
        if norm(item.nome_cargo) == n_n:
            cg = item
            break
    
    if not cg:
        cg = Cargo(
            codigo_cargo=cod,
            nome_cargo=nome_c,
            nivel_escolaridade=niv,
            regime_juridico="ESTATUTARIO"
        )
        db.add(cg)
        db.commit()
        db.refresh(cg)
        print(f"Cargo criado: ID {cg.id_cargo} - {cg.nome_cargo}")
    
    mapa_cargo_obj[n_n] = (cg, v_edital)

    # Garantir Lotacionograma
    lot = db.query(Lotacionograma).filter_by(id_cargo=cg.id_cargo).first()
    if not lot:
        lot = Lotacionograma(
            id_cargo=cg.id_cargo,
            lei_criacao="Lei Complementar Municipal nº 063/2008 e LC 092/2010",
            ano_vigencia=2024,
            vagas_criadas_lei=v_lei,
            vagas_ocupadas_oficial=v_oc,
            vagas_disponiveis_oficial=max(0, v_lei - v_oc)
        )
        db.add(lot)
        db.commit()
    else:
        # Atualizar para manter sincronizado com o quadro
        lot.vagas_criadas_lei = v_lei
        lot.vagas_ocupadas_oficial = v_oc
        lot.vagas_disponiveis_oficial = max(0, v_lei - v_oc)
        db.commit()

# 3. Configurar ConcursoVaga para Concurso 4
# Limpar registros prévios do concurso 4 para assegurar 100% de precisão
db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso).delete()
db.commit()

for n_n, (cg, v_edital) in mapa_cargo_obj.items():
    cv = ConcursoVaga(
        id_concurso=concurso.id_concurso,
        id_cargo=cg.id_cargo,
        vagas_imediatas_edital=v_edital,
        vagas_cr=5
    )
    db.add(cv)

db.commit()
print("Tabela concursos_vagas reconfigurada com sucesso para Concurso 4!")

# 4. Extrair candidatos aprovados de scratch/resultado_final_full_text.txt
with open("scratch/resultado_final_full_text.txt", encoding="utf-8", errors="ignore") as f:
    text = f.read()

lines = text.splitlines()

merged_lines = []
current_line = ""
is_pcd = False

for line in lines:
    s = line.strip()
    if not s or s.startswith("--- PAGE") or s.startswith("ESTADO DE") or s.startswith("PREFEITURA") or s.startswith("SECRETARIA") or s.startswith("EDITAL") or s.startswith("Art. 1") or s.startswith("INSCRI") or s.startswith("NOTA") or s.startswith("PROVA") or s.startswith("OBJETVA") or s.startswith("FINAL") or s.startswith("RESULTADO") or s.startswith("REGISTRE") or s.startswith("Pontes e") or s.startswith("Prefeito") or s.startswith("Mat") or "visualizarDiarioOficial" in s:
        continue
    
    if "DEFICI" in s or "PCD" in s:
        is_pcd = True
        continue

    is_cargo = False
    for c in ["ASSISTENTE", "AUXILIAR", "BIOQU", "ENFERMEIRO", "FISIOTERAPEUTA", "M", "NUTRICIONISTA", "ODONT", "PEDAGOGO", "PROFESSOR", "PSIC", "TAE", "T"]:
        if s.startswith(c) and not re.match(r"^\d", s):
            if any(k in s for k in ["ADMINISTRA", "SOCIAL", "CONSULT", "BIOQU", "RURAL", "URBANA", "FISIOTERAPEUTA", "20H", "40H", "NUTRICIONISTA", "ODONT", "PEDAGOGO", "EDUCA", "FSICA", "FSICA", "INGLESA", "PSIC", "MULTIMEIOS", "DESENVOLVIMENTO", "ENFERMAGEM", "HIGIENE", "RAIO"]):
                is_cargo = True
                break
    
    if is_cargo:
        if current_line:
            merged_lines.append(current_line)
            current_line = ""
        merged_lines.append(("CARGO_PCD: " if is_pcd else "CARGO: ") + s)
    elif re.match(r"^\d{6,9}\b", s):
        if current_line:
            merged_lines.append(current_line)
        current_line = s
    else:
        if current_line:
            current_line += " " + s

if current_line:
    merged_lines.append(current_line)

cargos_cands = {}
cur_cargo = None

for ml in merged_lines:
    if ml.startswith("CARGO: ") or ml.startswith("CARGO_PCD: "):
        is_p = ml.startswith("CARGO_PCD: ")
        raw_c = ml.split(": ", 1)[1].strip()
        if "ASSISTENTE ADMINISTRATIVO" in raw_c: c_norm = "ASSISTENTE ADMINISTRATIVO"
        elif "ASSISTENTE SOCIAL" in raw_c: c_norm = "ASSISTENTE SOCIAL"
        elif "AUXILIAR DE CONSULT" in raw_c: c_norm = "AUXILIAR DE CONSULTÓRIO DENTÁRIO"
        elif "BIOQU" in raw_c: c_norm = "BIOQUÍMICO/FARMACÊUTICO"
        elif "ENFERMEIRO - ZONA RURAL" in raw_c: c_norm = "ENFERMEIRO - ZONA RURAL"
        elif "ENFERMEIRO - ZONA URBANA" in raw_c: c_norm = "ENFERMEIRO - ZONA URBANA"
        elif "FISIOTERAPEUTA" in raw_c: c_norm = "FISIOTERAPEUTA"
        elif "20H" in raw_c: c_norm = "MÉDICO (20 HORAS)"
        elif "40H" in raw_c: c_norm = "MÉDICO (40 HORAS)"
        elif "NUTRICIONISTA" in raw_c: c_norm = "NUTRICIONISTA"
        elif "ODONT" in raw_c: c_norm = "ODONTÓLOGO"
        elif "PEDAGOGO" in raw_c: c_norm = "PEDAGOGO"
        elif "FÍSICA" in raw_c or "FSICA" in raw_c: c_norm = "PROFESSOR DE EDUCAÇÃO FÍSICA"
        elif "INFANTIL - ZONA RURAL" in raw_c: c_norm = "PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA RURAL"
        elif "INFANTIL - ZONA URBANA" in raw_c: c_norm = "PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA URBANA"
        elif "ANOS INICIAIS - ZONA RURAL" in raw_c: c_norm = "PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA RURAL"
        elif "ANOS INICIAIS - ZONA URBANA" in raw_c: c_norm = "PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA URBANA"
        elif "INGLESA - ZONA RURAL" in raw_c: c_norm = "PROFESSOR LÍNGUA INGLESA - ZONA RURAL"
        elif "INGLESA - ZONA URBANA" in raw_c: c_norm = "PROFESSOR LÍNGUA INGLESA - ZONA URBANA"
        elif "PSIC" in raw_c: c_norm = "PSICÓLOGO"
        elif "MULTIMEIOS" in raw_c: c_norm = "TAE - MULTIMEIOS DIDÁTICOS"
        elif "ADMINISTRA" in raw_c and "ESCOLAR" in raw_c: c_norm = "TAE - TÉCNICO EM ADMINISTRAÇÃO ESCOLAR"
        elif "DESENVOLVIMENTO INFANTIL" in raw_c: c_norm = "TAE - TÉCNICO EM DESENVOLVIMENTO INFANTIL"
        elif "ENFERMAGEM - ZONA URBANA" in raw_c: c_norm = "TÉCNICO EM ENFERMAGEM - ZONA URBANA"
        elif "HIGIENE DENTAL" in raw_c: c_norm = "TÉCNICO EM HIGIENE DENTAL"
        elif "RAIO" in raw_c: c_norm = "TÉCNICO OPERACIONAL EM RAIO-X"
        else: c_norm = raw_c
        
        cur_cargo = (c_norm, is_p)
        if c_norm not in cargos_cands:
            cargos_cands[c_norm] = []
    elif cur_cargo:
        c_norm, is_p = cur_cargo
        m = re.match(r"^(\d{6,9})\s+([A-Z\s\.\'\-]+?)\s+(.*)$", ml)
        if m:
            insc = m.group(1)
            nome = m.group(2).strip()
            rest = m.group(3).strip()
            if "Desclassificado" not in rest and "Não aprovado" not in rest and "No aprovado" not in rest:
                clas_m = re.search(r"(\d+)\s*[\.º°ª]*\s*$", rest)
                clas = int(clas_m.group(1)) if clas_m else len(cargos_cands[c_norm]) + 1
                cargos_cands[c_norm].append({"inscricao": insc, "nome": nome, "classificacao": clas, "cota": "PCD" if is_p else "AMPLA"})

# 5. Limpar candidatos antigos de Concurso 4 e certame 2 para reinserir base 100% oficial
# Antes de deletar candidatos, limpar convocações e movimentações do concurso 4
cand_ids_antigos = [c.id_candidato for c in db.query(Candidato).filter((Candidato.id_concurso == 4) | (Candidato.id_certame == 2)).all()]
if cand_ids_antigos:
    db.query(Convocacao).filter(Convocacao.id_candidato.in_(cand_ids_antigos)).delete(synchronize_session=False)
    db.query(MovimentacaoCandidato).filter(MovimentacaoCandidato.id_candidato.in_(cand_ids_antigos)).delete(synchronize_session=False)
    db.query(Candidato).filter(Candidato.id_candidato.in_(cand_ids_antigos)).delete(synchronize_session=False)
    db.commit()

print(f"Candidatos prévios do Concurso 4 limpos. Inserindo lista oficial de {sum(len(v) for v in cargos_cands.values())} candidatos aprovados...")

candidatos_db_map = {} # (cargo_norm, inscricao) -> Candidato
candidatos_db_clas_map = {} # (cargo_norm, classificacao) -> Candidato

for c_norm, cands_list in cargos_cands.items():
    cg_tuple = mapa_cargo_obj.get(norm(c_norm))
    if not cg_tuple:
        print(f"Atenção: Cargo {c_norm} não encontrado no mapa de cargos!")
        continue
    cargo_obj, v_edital = cg_tuple

    # Ordenar por classificação
    cands_list.sort(key=lambda x: x["classificacao"])

    for item in cands_list:
        insc = item["inscricao"]
        nome = item["nome"]
        clas = item["classificacao"]
        cota = item["cota"]

        # CPF formatado com o número de inscrição: 250.XXX.XXX-00
        cpf_fmt = f"250.{insc[:3]}.{insc[3:]}-00" if len(insc) == 6 else f"250.{insc[:3]}.{insc[3:6]}-{insc[6:]}"

        # Status inicial de aprovação
        if clas <= v_edital and v_edital > 0:
            status_init = "APROVADO (AGUARDANDO CONVOCAÇÃO)"
        else:
            status_init = "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

        cand = Candidato(
            id_concurso=concurso.id_concurso,
            id_certame=certame.id_certame,
            id_cargo=cargo_obj.id_cargo,
            cpf=cpf_fmt,
            nome_completo=nome,
            classificacao_original=clas,
            classificacao_efetiva=clas,
            tipo_cota=cota,
            status_atual=status_init
        )
        db.add(cand)
        db.flush() # obter id_candidato

        candidatos_db_map[(norm(c_norm), insc)] = cand
        candidatos_db_clas_map[(norm(c_norm), clas)] = cand

db.commit()
print("Todos os candidatos aprovados oficiais inseridos com sucesso!")

# 6. Registrar as 494 Convocações dos 21 Editais Oficiais
# Mapeamento estrito dos 21 editais
convocacoes_editais = [
    # Edital 002/2024 (16/01/2024)
    {"edital": "002/2024", "data": datetime.date(2024, 1, 16), "chamadas": [
        ("BIOQUÍMICO/FARMACÊUTICO", "inscricao", "695813"),
        ("MÉDICO (40 HORAS)", "inscricao", "690365"),
        ("ODONTÓLOGO", "inscricao", "690377"),
    ]},
    # Edital 004/2024 (18/01/2024)
    {"edital": "004/2024", "data": datetime.date(2024, 1, 18), "chamadas": [
        # Prof. Ed. Infantil ZR: 1-7
        *[("PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA RURAL", "classificacao", i) for i in range(1, 8)],
        # Prof. Ed. Infantil ZU: 1-76
        *[("PROFESSOR DE EDUCAÇÃO INFANTIL - ZONA URBANA", "classificacao", i) for i in range(1, 77)],
        # Prof. Fund. ZR: 1-8
        *[("PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA RURAL", "classificacao", i) for i in range(1, 9)],
        # Prof. Fund. ZU: 1-81
        *[("PROFESSOR DO ENSINO FUNDAMENTAL ANOS INICIAIS - ZONA URBANA", "classificacao", i) for i in range(1, 82)],
        # Prof. Língua Inglesa ZR: 1
        ("PROFESSOR LÍNGUA INGLESA - ZONA RURAL", "classificacao", 1),
        # Prof. Língua Inglesa ZU: 1-26
        *[("PROFESSOR LÍNGUA INGLESA - ZONA URBANA", "classificacao", i) for i in range(1, 27)],
        # TAE Multimeios: 1-45
        *[("TAE - MULTIMEIOS DIDÁTICOS", "classificacao", i) for i in range(1, 46)],
        # TAE Desenv. Infantil: 1-223
        *[("TAE - TÉCNICO EM DESENVOLVIMENTO INFANTIL", "classificacao", i) for i in range(1, 224)],
    ]},
    # Edital 007/2024 (05/02/2024)
    {"edital": "007/2024", "data": datetime.date(2024, 2, 5), "chamadas": [
        ("MÉDICO (40 HORAS)", "inscricao", "694768"), # 2º
    ]},
    # Edital 008/2024 (09/02/2024)
    {"edital": "008/2024", "data": datetime.date(2024, 2, 9), "chamadas": [
        ("ASSISTENTE ADMINISTRATIVO", "inscricao", "692367"), # 1º
        ("ASSISTENTE ADMINISTRATIVO", "inscricao", "689518"), # 2º
        ("AUXILIAR DE CONSULTÓRIO DENTÁRIO", "inscricao", "694480"), # 1º
        ("MÉDICO (40 HORAS)", "inscricao", "695850"), # 3º
    ]},
    # Edital 010/2024 (14/02/2024)
    {"edital": "010/2024", "data": datetime.date(2024, 2, 14), "chamadas": [
        ("ASSISTENTE ADMINISTRATIVO", "inscricao", "692349"), # 3º
    ]},
    # Edital 012/2024 (04/03/2024)
    {"edital": "012/2024", "data": datetime.date(2024, 3, 4), "chamadas": [
        ("BIOQUÍMICO/FARMACÊUTICO", "inscricao", "688211"), # 2º
        ("AUXILIAR DE CONSULTÓRIO DENTÁRIO", "inscricao", "695834"), # 2º
        ("PSICÓLOGO", "inscricao", "688587"), # 1º
    ]},
    # Edital 015/2024 (18/03/2024)
    {"edital": "015/2024", "data": datetime.date(2024, 3, 18), "chamadas": [
        ("PSICÓLOGO", "inscricao", "696063"), # 2º
    ]},
    # Edital 017/2024 (21/03/2024)
    {"edital": "017/2024", "data": datetime.date(2024, 3, 21), "chamadas": [
        ("BIOQUÍMICO/FARMACÊUTICO", "inscricao", "697194"), # 3º
    ]},
    # Edital 018/2024 (25/03/2024)
    {"edital": "018/2024", "data": datetime.date(2024, 3, 25), "chamadas": [
        ("ASSISTENTE ADMINISTRATIVO", "inscricao", "689307"), # 4º
    ]},
    # Edital 021/2024 (15/04/2024)
    {"edital": "021/2024", "data": datetime.date(2024, 4, 15), "chamadas": [
        ("PSICÓLOGO", "inscricao", "696628"), # 3º
    ]},
    # Edital 027/2024 (02/05/2024)
    {"edital": "027/2024", "data": datetime.date(2024, 5, 2), "chamadas": [
        ("MÉDICO (40 HORAS)", "inscricao", "693343"), # 5º
    ]},
    # Edital 029/2024 (07/05/2024)
    {"edital": "029/2024", "data": datetime.date(2024, 5, 7), "chamadas": [
        ("TÉCNICO EM ENFERMAGEM - ZONA URBANA", "inscricao", "695340"), # 1º
    ]},
    # Edital 031/2024 (13/05/2024)
    {"edital": "031/2024", "data": datetime.date(2024, 5, 13), "chamadas": [
        ("ENFERMEIRO - ZONA URBANA", "inscricao", "694036"), # 1º
    ]},
    # Edital 035/2024 (17/05/2024)
    {"edital": "035/2024", "data": datetime.date(2024, 5, 17), "chamadas": [
        ("ENFERMEIRO - ZONA URBANA", "inscricao", "695881"), # 2º
    ]},
    # Edital 039/2024 (10/06/2024)
    {"edital": "039/2024", "data": datetime.date(2024, 6, 10), "chamadas": [
        ("TAE - TÉCNICO EM ADMINISTRAÇÃO ESCOLAR", "inscricao", "695848"), # 1º
    ]},
    # Edital 043/2024 (19/06/2024)
    {"edital": "043/2024", "data": datetime.date(2024, 6, 19), "chamadas": [
        ("TAE - TÉCNICO EM ADMINISTRAÇÃO ESCOLAR", "inscricao", "689179"), # 2º
    ]},
    # Edital 051/2024 (05/09/2024)
    {"edital": "051/2024", "data": datetime.date(2024, 9, 5), "chamadas": [
        ("AUXILIAR DE CONSULTÓRIO DENTÁRIO", "inscricao", "695834"), # 2º Reconvocação
    ]},
    # Edital 055/2024 (30/09/2024)
    {"edital": "055/2024", "data": datetime.date(2024, 9, 30), "chamadas": [
        ("ENFERMEIRO - ZONA URBANA", "inscricao", "694575"), # 3º
    ]},
    # Edital 060/2024 (11/10/2024)
    {"edital": "060/2024", "data": datetime.date(2024, 10, 11), "chamadas": [
        ("TÉCNICO EM ENFERMAGEM - ZONA URBANA", "classificacao", 5), # Convocação continuada
    ]},
    # Edital 063/2024 (30/10/2024)
    {"edital": "063/2024", "data": datetime.date(2024, 10, 30), "chamadas": [
        ("TÉCNICO EM ENFERMAGEM - ZONA URBANA", "inscricao", "692433"), # 3º
    ]},
    # Edital 064/2024 (22/11/2024)
    {"edital": "064/2024", "data": datetime.date(2024, 11, 22), "chamadas": [
        ("TÉCNICO EM ENFERMAGEM - ZONA URBANA", "inscricao", "695954"), # 4º
    ]},
]

ordem_global = 1
total_convocados_geral = 0

for ed in convocacoes_editais:
    num_ed = ed["edital"]
    dt_ed = ed["data"]
    chamadas = ed["chamadas"]

    for cargo_nome, tipo_busca, val in chamadas:
        c_n = norm(cargo_nome)
        cand = None
        if tipo_busca == "inscricao":
            cand = candidatos_db_map.get((c_n, str(val)))
        elif tipo_busca == "classificacao":
            cand = candidatos_db_clas_map.get((c_n, int(val)))

        if not cand:
            print(f"Alerta: Candidato não localizado para chamada no edital {num_ed}: {cargo_nome} ({tipo_busca}={val})")
            continue

        cand.status_atual = "CONVOCADO"
        cand.edital_convocacao = f"Edital nº {num_ed}"

        # Criar registro de Convocação
        conv = Convocacao(
            id_concurso=concurso.id_concurso,
            id_candidato=cand.id_candidato,
            ordem_convocacao_global=ordem_global,
            numero_portaria=f"Edital nº {num_ed}",
            data_publicacao_doe=dt_ed,
            prazo_posse_limite=dt_ed + datetime.timedelta(days=30),
            compareceu=None
        )
        db.add(conv)

        # Criar registro de Movimentação
        mov = MovimentacaoCandidato(
            id_candidato=cand.id_candidato,
            tipo_evento="CONVOCACAO",
            numero_processo_sei=f"Edital de Convocação nº {num_ed}",
            data_registro=dt_ed,
            motivo_justificativa=f"Convocação oficial publicada no Diário Oficial em {dt_ed.strftime('%d/%m/%Y')}",
            classificacao_anterior=cand.classificacao_original,
            classificacao_nova=cand.classificacao_efetiva
        )
        db.add(mov)

        ordem_global += 1
        total_convocados_geral += 1

db.commit()
print(f"Sucesso! Total de convocações registradas: {total_convocados_geral} em {len(convocacoes_editais)} editais.")

# 7. Exibir Resumo Final da Matriz Consolidada
from audit_engine import AuditEngine
engine_audit = AuditEngine(db)
matriz = engine_audit.consolidar_matriz_cargo_acompanhamento(2)

print("\n=== MATRIZ CONSOLIDADA POR CARGO (ACOMPANHAMENTO CERTAME 2) ===")
print(f"{'CARGO':<55} | {'VAGAS EDITAL':<12} | {'CONVOCADOS':<10} | {'SALDO':<6}")
print("-" * 92)
tot_vagas = 0
tot_conv = 0
for m in matriz:
    tot_vagas += m["vagas_edital"]
    tot_conv += m["convocados"]
    print(f"{m['cargo']:<55} | {m['vagas_edital']:^12} | {m['convocados']:^10} | {m['saldo']:^6}")

print("-" * 92)
print(f"{'TOTAL GERAL':<55} | {tot_vagas:^12} | {tot_conv:^10} |")
print("=== CONCLUÍDO COM SUCESSO! ===")
