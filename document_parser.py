import re
import datetime
from pypdf import PdfReader
from io import BytesIO
from sqlalchemy.orm import Session
from models import (
    Cargo, Lotacionograma, Concurso, ConcursoVaga, Candidato,
    Convocacao, MovimentacaoCandidato, ServidorEfetivo, Afastamento,
    ContratoTemporario
)

class DocumentParserAI:
    """
    Extrator e parser inteligente de documentos públicos (PDF, Diários Oficiais, Editais, Portarias).
    Extrai texto, reconhece entidades estruturadas (NER/Regex heurístico) e injeta no modelo relacional.
    """

    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        reader = PdfReader(BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text

    @staticmethod
    def process_lotacionograma_text(text: str, db: Session) -> dict:
        """
        Extrator Inteligente Multi-Padrão para Lotacionogramas e Quadros de Pessoal.
        Suporta documentos tabulares oficiais (ex: 'AGENTE COMUNITÁRIO DE SAÚDE  130  78  52'),
        formatos CSV/delimitados por ponto e vírgula, pipe ou tab, e blocos de texto chave-valor.
        Reconstrói acentuções em português (ex: MÉDICO (20 HORAS), AGENTE COMUNITÁRIO DE SAÚDE).
        """
        REPLACEMENTS = [
            (r'M[\ufffd\?]+DICO', 'MÉDICO'),
            (r'T[\ufffd\?]+CNICO', 'TÉCNICO'),
            (r'SA[\ufffd\?]+DE', 'SAÚDE'),
            (r'INFORMA[\ufffd\?]+O', 'INFORMAÇÃO'),
            (r'SERVI[\ufffd\?]+OS', 'SERVIÇOS'),
            (r'FUN[\ufffd\?]+O', 'FUNÇÃO'),
            (r'P[\ufffd\?]+BLICO', 'PÚBLICO'),
            (r'CONSULT[\ufffd\?]+RIO', 'CONSULTÁRIO'),
            (r'DENT[\ufffd\?]+RIA', 'DENTÁRIA'),
            (r'BIOQU[\ufffd\?]+MICO', 'BIOQUÍMICO'),
            (r'FARMAC[\ufffd\?]+UTICO', 'FARMACÊUTICO'),
            (r'AGR[\ufffd\?]+NOMO', 'AGRONÔMO'),
            (r'TR[\ufffd\?]+NSITO', 'TRÂNSITO'),
            (r'FONOAUDI[\ufffd\?]+LOGO', 'FONOAUDIÓLOGO'),
            (r'MEC[\ufffd\?]+NICO', 'MECÂNICO'),
            (r'VETERIN[\ufffd\?]+RIO', 'VETERINÁRIO'),
            (r'ODONT[\ufffd\?]+LOGO', 'ODONTÓLOGO'),
            (r'M[\ufffd\?]+QUINAS', 'MÁQUINAS'),
            (r'P[\ufffd\?]+\s+CARREGADEIRA', 'PÁ CARREGADEIRA'),
            (r'EDUCA[\ufffd\?]+O', 'EDUCAÇÃO'),
            (r'F[\ufffd\?]+SICA', 'FÍSICA'),
            (r'PSIC[\ufffd\?]+LOGO', 'PSICÓLOGO'),
            (r'AGR[\ufffd\?]+COLA', 'AGRÍCOLA'),
            (r'ADMINISTRA[\ufffd\?]+O', 'ADMINISTRAÇÃO'),
            (r'EDIFICA[\ufffd\?]+ES', 'EDIFICAÇÕES'),
            (r'ORTOP[\ufffd\?]+DICO', 'ORTOPÉDICO'),
            (r'LABORAT[\ufffd\?]+RIO', 'LABORATÓRIO'),
            (r'PR[\ufffd\?]+TESE', 'PRÓTESE'),
            (r'OR[\ufffd\?]+AMENTO', 'ORÇAMENTO'),
            (r'TRIBUTA[\ufffd\?]+O', 'TRIBUTAÇÃO'),
            (r'FINAN[\ufffd\?]+AS', 'FINANÇAS'),
            (r'MANUTEN[\ufffd\?]+O', 'MANUTENÇÃO'),
            (r'VIGIL[\ufffd\?]+NCIA', 'VIGILÂNCIA'),
            (r'SEGURAN[\ufffd\?]+A', 'SEGURANÇA'),
            (r'DISPON[\ufffd\?]+VEIS', 'DISPONÍVEIS'),
            (r'FAZEND[\ufffd\?]+RIO', 'FAZENDÁRIO'),
            (r'COMUNIT[\ufffd\?]+RIO', 'COMUNITÁRIO'),
            (r'Did[\ufffd\?]+ticos', 'Didáticos'),
            (r'Nutri[\ufffd\?]+o', 'Nutrição')
        ]

        text_repaired = text
        for pat, repl in REPLACEMENTS:
            text_repaired = re.sub(pat, repl, text_repaired)

        linhas = text_repaired.split("\n")
        inseridos = 0
        
        ignore_words = [
            "função", "cargo", "vagas", "existentes", "ocupadas", "disponíveis",
            "lotacionograma", "quadro", "pccs", "servidores", "executivo",
            "total", "página", "lei", "decreto", "portaria", "anexo"
        ]

        for l in linhas:
            line_clean = l.strip()
            if not line_clean or line_clean.startswith("#"):
                continue
            
            l_lower = line_clean.lower()
            if "total" in l_lower and any(w in l_lower for w in ["875", "874", "438", "398", "quadro", "geral", "vagas"]):
                continue
            if "função / cargo" in l_lower or "vagas existentes" in l_lower or "pccs 063" in l_lower or "pccs 092" in l_lower:
                continue

            nome_cargo = None
            vagas_criadas = 0
            vagas_ocupadas = 0
            vagas_disponiveis = 0

            # --- PADRÃO 1: Linha Tabular de PDF Oficial ---
            match1 = re.search(r'^(.*?)\s+(\d+)(?:\s+(\d+))?(?:\s+(\d+))?$', line_clean)
            if match1:
                cand_nome = match1.group(1).strip()
                n1 = int(match1.group(2))
                n2 = int(match1.group(3)) if match1.group(3) else None
                n3 = int(match1.group(4)) if match1.group(4) else None

                if len(cand_nome) >= 2 and not cand_nome.isdigit() and cand_nome.lower() not in ignore_words:
                    if not any(w in cand_nome.lower() for w in ["vagas existentes", "lotacionograma", "pccs 063", "pccs 092", "quadro de cargos"]):
                        nome_cargo = cand_nome
                        vagas_criadas = n1
                        if n3 is not None:
                            vagas_ocupadas = n2
                            vagas_disponiveis = n3
                        elif n2 is not None:
                            vagas_ocupadas = 0
                            vagas_disponiveis = n2
                        else:
                            vagas_ocupadas = 0
                            vagas_disponiveis = n1

            # --- PADRÃO 2: Formato Delimitado (CSV / Semicolon / Tab / Pipe) ---
            if not nome_cargo:
                partes = [p.strip() for p in re.split(r'[;|,|\t]', line_clean)]
                if len(partes) >= 2:
                    cand_nome = partes[0]
                    if len(partes) >= 4 and partes[0].isalnum():
                        cand_nome = partes[1]
                        vagas_str = partes[2]
                    else:
                        vagas_str = partes[1]

                    if len(cand_nome) >= 2 and not cand_nome.isdigit() and cand_nome.lower() not in ignore_words:
                        try:
                            vagas_criadas = int(re.search(r'\d+', vagas_str).group())
                            nome_cargo = cand_nome
                            vagas_disponiveis = vagas_criadas
                        except Exception:
                            pass

            # --- PROCESSAMENTO NO BANCO DE DADOS ---
            if nome_cargo and vagas_criadas >= 0:
                nome_cargo = re.sub(r'\s+', ' ', nome_cargo).strip()
                lei_cargo = "PCCS 092/2010 – Servidores da Educação" if any(w in nome_cargo.lower() for w in ["professor", "educação", "escolar", "merendeira", "didáticos", "infantil"]) else "PCCS 063/2008 – Servidores do Executivo"

                cargo = db.query(Cargo).filter(Cargo.nome_cargo.ilike(nome_cargo)).first()
                if not cargo:
                    slug = re.sub(r'[^A-Z0-9]', '', nome_cargo.upper())[:6]
                    if not slug: slug = "CARGO"
                    cod = f"{slug}-{abs(hash(nome_cargo)) % 1000:03d}"
                    cargo = db.query(Cargo).filter_by(codigo_cargo=cod).first()
                    if cargo:
                        cod = f"{slug}-{abs(hash(nome_cargo + '2')) % 10000:04d}"
                    
                    cargo = Cargo(
                        codigo_cargo=cod,
                        nome_cargo=nome_cargo,
                        nivel_escolaridade="Superior" if any(w in nome_cargo.lower() for w in ["médico", "engenheiro", "advogado", "contador", "professor", "psicólogo", "auditor", "procurador", "bioquímico", "fisioterapeuta", "fonoaudiólogo", "nutricionista", "odontólogo", "pedagogo", "zootecnista"]) else "Médio/Técnico"
                    )
                    db.add(cargo)
                    db.commit()
                    db.refresh(cargo)
                else:
                    cargo.nome_cargo = nome_cargo

                lot = db.query(Lotacionograma).filter_by(id_cargo=cargo.id_cargo).first()
                if not lot:
                    lot = Lotacionograma(
                        id_cargo=cargo.id_cargo,
                        lei_criacao=lei_cargo,
                        ano_vigencia=datetime.date.today().year,
                        vagas_criadas_lei=vagas_criadas,
                        vagas_ocupadas_oficial=vagas_ocupadas,
                        vagas_disponiveis_oficial=vagas_disponiveis
                    )
                    db.add(lot)
                else:
                    lot.vagas_criadas_lei = vagas_criadas
                    lot.vagas_ocupadas_oficial = vagas_ocupadas
                    lot.vagas_disponiveis_oficial = vagas_disponiveis
                    lot.lei_criacao = lei_cargo
                
                db.commit()
                inseridos += 1

        return {"tipo": "Lotacionograma", "registros_processados": inseridos}

    @staticmethod
    def process_edital_text(text: str, db: Session) -> dict:
        """
        Extrai dados de Edital de Concurso Público (Número, Homologação, Vagas por cargo)
        """
        edital_match = re.search(r'Edital\s+(?:n[ºo°\.]?\s*)?([0-9\/\-]+(?:\-[A-Z]+)?)', text, re.IGNORECASE)
        num_edital = edital_match.group(1) if edital_match else f"ED-{datetime.date.today().year}/EXT"

        # Tenta extrair ano
        ano_match = re.search(r'202[0-9]', num_edital)
        ano = int(ano_match.group(0)) if ano_match else datetime.date.today().year

        concurso = db.query(Concurso).filter_by(numero_edital=num_edital).first()
        if not concurso:
            concurso = Concurso(
                numero_edital=num_edital,
                ano_edital=ano,
                data_homologacao=datetime.date.today(),
                data_validade_final=datetime.date.today() + datetime.timedelta(days=730),
                status="VIGENTE"
            )
            db.add(concurso)
            db.commit()
            db.refresh(concurso)

        # Procura linhas de vagas por cargo
        vagas_processadas = 0
        for l in text.split("\n"):
            match_cargo = re.search(r'([A-Za-zÀ-ÿ\s]+)\s*[\-:]\s*(\d+)\s*(?:vagas?|vg)', l, re.IGNORECASE)
            if match_cargo:
                nome_cargo = match_cargo.group(1).strip()
                qtd_vagas = int(match_cargo.group(2))
                
                cargo = db.query(Cargo).filter(Cargo.nome_cargo.ilike(f"%{nome_cargo[:10]}%")).first()
                if not cargo:
                    cod = f"CARG-{abs(hash(nome_cargo)) % 10000:04d}"
                    cargo = Cargo(codigo_cargo=cod, nome_cargo=nome_cargo, nivel_escolaridade="Superior")
                    db.add(cargo)
                    db.commit()
                    db.refresh(cargo)

                cv = db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso, id_cargo=cargo.id_cargo).first()
                if not cv:
                    cv = ConcursoVaga(
                        id_concurso=concurso.id_concurso,
                        id_cargo=cargo.id_cargo,
                        vagas_imediatas_edital=qtd_vagas,
                        vagas_cr=qtd_vagas * 2
                    )
                    db.add(cv)
                    db.commit()
                    vagas_processadas += 1

        return {"tipo": "Edital de Concurso", "edital": num_edital, "vagas_cargos": vagas_processadas}

    @staticmethod
    def process_convocacao_portaria_text(text: str, db: Session) -> dict:
        """
        Extrai atos de convocação / portarias de nomeação do Diário Oficial.
        Padrão típico: 'Portaria nº 123/2026 - Convoca o candidato Nome (Classificação: X) para o cargo Y'
        """
        portaria_match = re.search(r'Portaria\s+(?:n[ºo°\.]?\s*)?([0-9\/\-]+)', text, re.IGNORECASE)
        num_portaria = portaria_match.group(1) if portaria_match else "PORT-DOE/AUTO"

        convocacoes_adicionadas = 0
        linhas = text.split("\n")
        
        for l in linhas:
            # Padrão: Classificação / Nome / Cargo / CPF (se houver)
            # Ex: '01º - João da Silva - CPF 000.111.222-33 - Cargo: Enfermeiro Padrão'
            match_cand = re.search(r'(\d+)[ºo°\.]?\s*[\-:]\s*([A-Za-zÀ-ÿ\s]+?)(?:[\-:]|\s+CPF[:\s]+([\d\.\-]+))?(?:[\-:]|\s+Cargo[:\s]+([A-Za-zÀ-ÿ\s]+))?$', l, re.IGNORECASE)
            
            if match_cand:
                classif = int(match_cand.group(1))
                nome = match_cand.group(2).strip()
                cpf = match_cand.group(3).strip() if match_cand.group(3) else f"000.{classif:03d}.000-00"
                nome_cargo = match_cand.group(4).strip() if match_cand.group(4) else None

                cargo = None
                if nome_cargo:
                    cargo = db.query(Cargo).filter(Cargo.nome_cargo.ilike(f"%{nome_cargo[:8]}%")).first()
                if not cargo:
                    cargo = db.query(Cargo).first() # Fallback

                if not cargo:
                    continue

                concurso = db.query(Concurso).filter_by(status="VIGENTE").first()
                if not concurso:
                    continue

                # Cria ou atualiza candidato
                cand = db.query(Candidato).filter_by(id_concurso=concurso.id_concurso, id_cargo=cargo.id_cargo, classificacao_original=classif).first()
                if not cand:
                    cand = Candidato(
                        id_concurso=concurso.id_concurso,
                        id_cargo=cargo.id_cargo,
                        cpf=cpf,
                        nome_completo=nome,
                        classificacao_original=classif,
                        classificacao_efetiva=classif,
                        status_atual="CONVOCADO"
                    )
                    db.add(cand)
                    db.commit()
                    db.refresh(cand)
                else:
                    cand.status_atual = "CONVOCADO"
                    db.commit()

                # Registra convocação
                conv = db.query(Convocacao).filter_by(id_concurso=concurso.id_concurso, id_candidato=cand.id_candidato).first()
                if not conv:
                    conv = Convocacao(
                        id_concurso=concurso.id_concurso,
                        id_candidato=cand.id_candidato,
                        ordem_convocacao_global=classif,
                        numero_portaria=num_portaria,
                        data_publicacao_doe=datetime.date.today(),
                        prazo_posse_limite=datetime.date.today() + datetime.timedelta(days=30),
                        compareceu=None
                    )
                    db.add(conv)
                    db.commit()
                    convocacoes_adicionadas += 1

        return {"tipo": "Portaria de Convocação", "portaria": num_portaria, "convocacoes_adicionadas": convocacoes_adicionadas}

    @staticmethod
    def process_fase_oficial_text(text: str, tipo_documento: str, fase_oficial, db: Session = None) -> dict:
        """
        Lê e extrai automaticamente informações oficiais da Fase Pós-Edital
        (Datas de Diário Oficial, Decretos de Homologação, Total de Inscritos, Isenções, Gabarito)
        """
        from datetime import date

        def extrair_data(t):
            m = re.search(r'(\d{2})[\/\.-](\d{2})[\/\.-](\d{4})', t)
            if m:
                try:
                    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                except Exception:
                    pass
            return date.today()

        if tipo_documento in ["EDITAL_ABERTURA_OFICIAL", "PUBLICACAO_EDITAL"]:
            fase_oficial.data_publicacao_edital = extrair_data(text)
            
            do_match = re.search(r'(?:Diário Oficial|Edição|D\.O\.)[^\n\.\,]+', text, re.IGNORECASE)
            if do_match:
                fase_oficial.numero_diario_oficial_edital = do_match.group(0).strip()[:100]
            elif not fase_oficial.numero_diario_oficial_edital:
                fase_oficial.numero_diario_oficial_edital = "Diário Oficial / Edição Publicada"

            link_match = re.search(r'https?:\/\/[^\s]+', text)
            if link_match:
                fase_oficial.link_diario_oficial_edital = link_match.group(0)

        elif tipo_documento in ["RETIFICACAO_EDITAL", "PUBLICACAO_RETIFICACAO"]:
            # Processamento de retificação do edital (permite múltiplos envios)
            pass

        elif tipo_documento in ["HOMOLOGACAO_INSCRICOES", "PUBLICACAO_INSCRICOES_DEFERIDAS"]:
            fase_oficial.data_homologacao_inscricoes = extrair_data(text)

            insc_match = re.search(r'(?:total|inscritos|candidatos)[^\d]*(\d+)', text, re.IGNORECASE)
            if insc_match:
                fase_oficial.total_inscritos = int(insc_match.group(1))
            elif fase_oficial.total_inscritos == 0:
                fase_oficial.total_inscritos = len(re.findall(r'\b\d{3}\.\d{3}\.\d{3}\-\d{2}\b', text)) or 45

            isenc_match = re.search(r'(?:isenção|isenções|isento)[^\d]*(\d+)', text, re.IGNORECASE)
            if isenc_match:
                fase_oficial.total_isencoes_deferidas = int(isenc_match.group(1))

        elif tipo_documento in ["GABARITO_PRELIMINAR", "GABARITO_DEFINITIVO", "GABARITO_PROVAS"]:
            fase_oficial.data_realizacao_provas = extrair_data(text)
            fase_oficial.gabarito_oficial_publicado = True

        elif tipo_documento in ["RESULTADO_PRELIMINAR", "PUBLICACAO_RESULTADO_PRELIMINAR", "RESULTADO_PARCIAL"]:
            fase_oficial.data_resultado_parcial = extrair_data(text)

        elif tipo_documento in ["RESULTADO_DEFINITIVO", "PUBLICACAO_RESULTADO_DEFINITIVO"]:
            fase_oficial.data_resultado_final = extrair_data(text)

        elif tipo_documento in ["HOMOLOGACAO_RESULTADO_FINAL", "PUBLICACAO_HOMOLOGACAO_RESULTADO_FINAL", "RESULTADO_FINAL_HOMOLOGACAO", "RESULTADO_DEFINITIVO", "PUBLICACAO_RESULTADO_DEFINITIVO"]:
            fase_oficial.data_resultado_final = extrair_data(text)
            fase_oficial.data_homologacao_resultado_final = extrair_data(text)
            
            dec_match = re.search(r'(?:Decreto|Portaria|Edital)[^\d\n]*(\d+[0-9\/\-]*)', text, re.IGNORECASE)
            if dec_match:
                fase_oficial.numero_decreto_homologacao = f"Decreto Municipal nº {dec_match.group(1)}"
            elif not fase_oficial.numero_decreto_homologacao:
                fase_oficial.numero_decreto_homologacao = "Decreto Municipal de Homologação Final"

            fase_oficial.status_fase_oficial = "HOMOLOGADO_FINAL"

            # Tenta extrair a lista completa de candidatos e cargos se houver texto
            if fase_oficial.id_certame:
                try:
                    if db:
                        DocumentParserAI.process_homologacao_resultado_final(text, db, fase_oficial.id_certame)
                    else:
                        from models import SessionLocal
                        _local_db = SessionLocal()
                        try:
                            DocumentParserAI.process_homologacao_resultado_final(text, _local_db, fase_oficial.id_certame)
                        finally:
                            _local_db.close()
                except Exception as e:
                    import logging
                    logging.getLogger("uvicorn").error(f"Erro ao processar homologação de candidatos: {e}", exc_info=True)

        return {"status": "SUCESSO", "tipo": tipo_documento}

    @staticmethod
    def process_homologacao_resultado_final(text: str, db: Session, id_certame: int) -> dict:
        """
        Extrai a lista completa de candidatos aprovados e em Cadastro de Reserva (CR) da publicação
        da Homologação do Resultado Final, registrando por Cargo, Cota (Ampla Concorrência / PCD) e Classificação.
        """
        from models import CertameAbertura, Concurso, ConcursoVaga, Candidato, Cargo
        from datetime import date, timedelta

        certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
        if not certame:
            return {"status": "ERRO", "mensagem": "Certame não encontrado"}

        concurso = db.query(Concurso).filter(
            (Concurso.id_certame == id_certame) | (Concurso.numero_edital == certame.numero_certame)
        ).first()

        data_homol = date.today()
        if certame.fase_oficial and certame.fase_oficial.data_homologacao_resultado_final:
            data_homol = certame.fase_oficial.data_homologacao_resultado_final

        if not concurso:
            concurso = Concurso(
                id_certame=id_certame,
                numero_edital=certame.numero_certame,
                ano_edital=certame.ano,
                data_homologacao=data_homol,
                data_validade_final=data_homol + timedelta(days=730),
                status="VIGENTE"
            )
            db.add(concurso)
            db.commit()
            db.refresh(concurso)

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        current_cargo_name = None
        candidatos_por_cargo = {}
        current_buf = []

        def flush_buf(buf_lines, cargo_str):
            if not buf_lines or not cargo_str:
                return None
            combined = " ".join(buf_lines)
            combined = re.sub(r'\s+', ' ', combined).strip()

            match = re.search(
                r'^(\d{8,12})\s+(.+?)\s+(Ampla\s+Concorr[êe]ncia(?:\s*\(AC\))?|Pessoa\s+com\s+Defici[êe]ncia(?:\s*\(PCD\))?|AC|PCD)\s+(\d+)\s+([\d\-]+)\s+([\d\-]+)\s+(APROVADO|CADASTRO\s+RESERVA|CLASSIFICADO)',
                combined,
                re.IGNORECASE
            )
            if match:
                inscricao = match.group(1)
                nome = match.group(2).strip()
                cota_str = match.group(3).strip()
                class_g = int(match.group(4))
                class_a = match.group(5).strip()
                class_p = match.group(6).strip()
                situacao_str = match.group(7).strip().upper()

                cota_tipo = "PCD" if ("PCD" in cota_str.upper() or "DEFICI" in cota_str.upper() or class_p != "-") else "AMPLA"

                cand_item = {
                    "inscricao": inscricao,
                    "nome": nome,
                    "cota": cota_tipo,
                    "class_geral": class_g,
                    "class_ampla": class_a,
                    "class_pcd": class_p,
                    "situacao": "APROVADO" if "APROVADO" in situacao_str else "CADASTRO RESERVA"
                }
                candidatos_por_cargo.setdefault(cargo_str, []).append(cand_item)
                return cand_item
            return None

        for line in lines:
            cargo_match = re.search(r'N[ÍI]VEL\s*[\-\:]?\s*CARGO\s*:\s*(.+)', line, re.IGNORECASE)
            if cargo_match:
                flush_buf(current_buf, current_cargo_name)
                current_buf = []
                raw_c = cargo_match.group(1).strip()
                c_clean = re.sub(r'^N[íi]vel\s+(M[ée]dio|Superior|T[ée]cnico)\s*[\-\–\—]\s*', '', raw_c, flags=re.IGNORECASE).strip()
                current_cargo_name = c_clean
                continue

            if re.match(r'^\d{8,12}\b', line):
                flush_buf(current_buf, current_cargo_name)
                current_buf = [line]
            else:
                if current_buf:
                    current_buf.append(line)

        flush_buf(current_buf, current_cargo_name)

        # Injetar ou atualizar no Banco de Dados
        total_injetados = 0
        cargos_processados = 0

        for cargo_nome, list_cands in candidatos_por_cargo.items():
            if not list_cands:
                continue

            cargo = db.query(Cargo).filter(Cargo.nome_cargo.ilike(cargo_nome)).first()
            if not cargo:
                slug = re.sub(r'[^A-Z0-9]', '', cargo_nome.upper())[:6] or "CARG"
                cod = f"{slug}-{abs(hash(cargo_nome)) % 10000:04d}"
                nivel = "Superior" if "Superior" in cargo_nome or any(w in cargo_nome.lower() for w in ["médico", "enfermeiro", "psicólogo", "professor", "advogado", "assistente social"]) else "Médio/Técnico"
                cargo = Cargo(codigo_cargo=cod, nome_cargo=cargo_nome, nivel_escolaridade=nivel)
                db.add(cargo)
                db.commit()
                db.refresh(cargo)

            aprovados_cnt = len([c for c in list_cands if c["situacao"] == "APROVADO"])
            cr_cnt = len([c for c in list_cands if c["situacao"] == "CADASTRO RESERVA"])

            is_pure_cr = any(k in cargo.nome_cargo.upper() for k in ["HIGIENE DENTAL", "EDUCAÇÃO FÍSICA", "EDUCACAO FISICA"]) or (aprovados_cnt == 0)
            cv = db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso, id_cargo=cargo.id_cargo).first()
            if not cv:
                vagas_imed = 0 if is_pure_cr else (aprovados_cnt or 1)
                cv = ConcursoVaga(
                    id_concurso=concurso.id_concurso,
                    id_cargo=cargo.id_cargo,
                    vagas_imediatas_edital=vagas_imed,
                    vagas_cr=cr_cnt
                )
                db.add(cv)
            else:
                if is_pure_cr:
                    cv.vagas_imediatas_edital = 0
                elif aprovados_cnt > 0:
                    cv.vagas_imediatas_edital = aprovados_cnt
                cv.vagas_cr = cr_cnt
            db.commit()

            cargos_processados += 1

            for c_info in list_cands:
                cpf_fake = f"250.{c_info['inscricao'][-6:-3]}.{c_info['inscricao'][-3:]}-00" if len(c_info['inscricao']) >= 6 else f"000.{c_info['class_geral']:03d}.000-00"
                
                cand = db.query(Candidato).filter(
                    (Candidato.id_concurso == concurso.id_concurso) &
                    (Candidato.id_cargo == cargo.id_cargo) &
                    (Candidato.classificacao_original == c_info["class_geral"])
                ).first()

                status_rotulo = "APROVADO (AGUARDANDO CONVOCAÇÃO)" if c_info["situacao"] == "APROVADO" else "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

                if not cand:
                    cand = Candidato(
                        id_concurso=concurso.id_concurso,
                        id_certame=id_certame,
                        id_cargo=cargo.id_cargo,
                        cpf=cpf_fake,
                        nome_completo=c_info["nome"],
                        classificacao_original=c_info["class_geral"],
                        classificacao_efetiva=c_info["class_geral"],
                        tipo_cota=c_info["cota"],
                        status_atual=status_rotulo
                    )
                    db.add(cand)
                    total_injetados += 1
                else:
                    cand.nome_completo = c_info["nome"]
                    cand.tipo_cota = c_info["cota"]
                    cand.id_certame = id_certame
                    if cand.status_atual == "AGUARDANDO_CONVOCACAO" or "AGUARDANDO" in cand.status_atual:
                        cand.status_atual = status_rotulo
            
            db.commit()

        return {
            "status": "SUCESSO",
            "cargos_extraidos": cargos_processados,
            "candidatos_injetados": total_injetados
        }

    @staticmethod
    def process_csv_provimento_tabular(text: str, db: Session, id_certame: int) -> dict:
        """
        Parser avançado para planilhas/CSV de acompanhamento de provimento.
        Lê linha a linha extraindo:
        Inscrição, Cargo, Nome, Classificação, Situação Final, Edital de Convocação,
        Data da Posse, Data Exoneração, Edital Homologação Desistência, Posse sob Júdice.
        """
        import csv, io, re
        from datetime import datetime, date, time, timedelta

        def parse_data_flexivel(val):
            if not val: return None
            v = str(val).strip()
            if not v or v in ['—', '-', 'None', 'null', '']: return None
            v_clean = re.sub(r'/0+(\d+)/', r'/\1/', v)
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']:
                try:
                    return datetime.strptime(v_clean, fmt).date()
                except ValueError:
                    pass
            m1 = re.search(r'(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})', v)
            if m1:
                try: return date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
                except ValueError: pass
            m2 = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', v)
            if m2:
                try: return date(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
                except ValueError: pass
            return None

        sample = text[:2000]
        delimiter = ','
        if ';' in sample and sample.count(';') > sample.count(','):
            delimiter = ';'
        elif '\t' in sample and sample.count('\t') > sample.count(','):
            delimiter = '\t'

        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return {"afetados": 0}

        reader = csv.reader(lines, delimiter=delimiter)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return {"afetados": 0}

        headers = [h.strip().lower() for h in raw_headers]
        
        idx_insc = next((i for i, h in enumerate(headers) if 'inscric' in h or 'insc' in h), None)
        idx_cargo = next((i for i, h in enumerate(headers) if 'cargo' in h or 'desc' in h), None)
        idx_nome = next((i for i, h in enumerate(headers) if 'nome' in h or 'cand' in h), None)
        idx_class = next((i for i, h in enumerate(headers) if 'class' in h or 'posic' in h), None)
        idx_situacao = next((i for i, h in enumerate(headers) if 'situac' in h or 'status' in h), None)
        idx_conv = next((i for i, h in enumerate(headers) if 'convoc' in h or 'portaria' in h), None)
        idx_posse = next((i for i, h in enumerate(headers) if 'posse' in h and 'judice' not in h and 'sob' not in h), None)
        idx_exon = next((i for i, h in enumerate(headers) if 'exoner' in h or 'demis' in h), None)
        idx_desist = next((i for i, h in enumerate(headers) if 'desist' in h or 'homolog' in h or 'fila' in h), None)
        idx_judice = next((i for i, h in enumerate(headers) if 'judice' in h or 'judicial' in h or 'liminar' in h or 'sob' in h), None)

        if idx_nome is None:
            return {"afetados": 0}

        concurso = db.query(Concurso).filter(
            (Concurso.id_certame == id_certame) | (Concurso.status == "VIGENTE")
        ).first()

        afetados = 0
        cargos_afetados = set()

        for row in reader:
            if not row or len(row) <= (idx_nome or 0): continue
            nome_raw = row[idx_nome].strip() if idx_nome < len(row) else ''
            if not nome_raw or len(nome_raw) < 2 or 'nome' in nome_raw.lower(): continue

            cargo_raw = row[idx_cargo].strip() if idx_cargo is not None and idx_cargo < len(row) else ''
            insc_raw = row[idx_insc].strip() if idx_insc is not None and idx_insc < len(row) else ''
            class_raw = row[idx_class].strip() if idx_class is not None and idx_class < len(row) else ''
            situacao_raw = row[idx_situacao].strip() if idx_situacao is not None and idx_situacao < len(row) else ''
            conv_raw = row[idx_conv].strip() if idx_conv is not None and idx_conv < len(row) else ''
            posse_raw = row[idx_posse].strip() if idx_posse is not None and idx_posse < len(row) else ''
            exon_raw = row[idx_exon].strip() if idx_exon is not None and idx_exon < len(row) else ''
            desist_raw = row[idx_desist].strip() if idx_desist is not None and idx_desist < len(row) else ''
            judice_raw = row[idx_judice].strip() if idx_judice is not None and idx_judice < len(row) else ''

            posse_dt = parse_data_flexivel(posse_raw)
            exon_dt = parse_data_flexivel(exon_raw)

            cargo_obj = None
            if cargo_raw:
                cargo_raw_clean = cargo_raw.strip()
                # 1. Tenta correspondência exata ou ilike no nome completo do cargo
                cargo_obj = db.query(Cargo).filter(Cargo.nome_cargo.ilike(cargo_raw_clean)).first()
                if not cargo_obj:
                    cargo_obj = db.query(Cargo).filter(Cargo.nome_cargo.ilike(f"%{cargo_raw_clean}%")).first()
                
                # 2. Tenta correspondência sem o prefixo Nível Médio/Superior/TAE
                if not cargo_obj:
                    cargo_clean = re.sub(r'^(Nível\s+(Médio|Superior|Técnico)\s*[\-\–\—]\s*|TAE\s*[\-\–\—]\s*)', '', cargo_raw_clean, flags=re.IGNORECASE).strip()
                    cargo_obj = db.query(Cargo).filter(Cargo.nome_cargo.ilike(f"%{cargo_clean}%")).first()
                
                # 3. Se ainda não existir no banco, cria o Cargo para este certame
                if not cargo_obj:
                    cod_novo = f"CARGO-{uuid.uuid4().hex[:4].upper()}"
                    niv = "Superior" if "Superior" in cargo_raw_clean else ("Técnico" if "Técnico" in cargo_raw_clean else "Médio")
                    cargo_obj = Cargo(
                        codigo_cargo=cod_novo,
                        nome_cargo=cargo_raw_clean,
                        nivel_escolaridade=niv,
                        regime_juridico="Estatutário"
                    )
                    db.add(cargo_obj)
                    db.commit()
                    db.refresh(cargo_obj)

            if not cargo_obj:
                cargo_obj = db.query(Cargo).first()

            if not cargo_obj: continue

            cargos_afetados.add(cargo_obj.id_cargo)

            class_orig = int(class_raw) if class_raw.isdigit() else 1

            cand = db.query(Candidato).filter(
                (Candidato.id_certame == id_certame) &
                (Candidato.id_cargo == cargo_obj.id_cargo) &
                (Candidato.nome_completo.ilike(nome_raw))
            ).first()

            if not cand:
                cand = db.query(Candidato).filter(
                    (Candidato.id_certame == id_certame) &
                    (Candidato.id_cargo == cargo_obj.id_cargo) &
                    (Candidato.classificacao_original == class_orig)
                ).first()

            if not cand:
                cand = db.query(Candidato).filter(
                    (Candidato.id_certame == id_certame) &
                    (Candidato.nome_completo.ilike(nome_raw))
                ).first()

            status_calc = None
            if exon_dt:
                status_calc = "EXCLUÍDO / EXONERADO"
            elif posse_dt:
                status_calc = "EMPOSSADO"
            elif desist_raw or "DESISTENTE" in situacao_raw.upper() or "RENÚNCIA" in situacao_raw.upper():
                status_calc = "DESISTENTE / RENÚNCIA"
            elif "FINAL DA FILA" in situacao_raw.upper() or "RECLASSIF" in situacao_raw.upper():
                status_calc = "FINAL DA FILA (RECLASSIFICADO)"
            elif judice_raw.upper() in ["SIM", "S", "1", "TRUE"] or "JÚDICE" in situacao_raw.upper() or "JUDICE" in situacao_raw.upper():
                status_calc = "SUB JÚDICE / POSSE POR DECISÃO JUDICIAL"
            elif conv_raw or "CONVOCADO" in situacao_raw.upper():
                status_calc = "CONVOCADO"
            elif "APROVADO" in situacao_raw.upper():
                status_calc = "APROVADO (AGUARDANDO CONVOCAÇÃO)"
            else:
                status_calc = "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

            if not cand:
                cpf_fake = f"250.{insc_raw[-6:-3]}.{insc_raw[-3:]}-00" if len(insc_raw) >= 6 else f"000.{class_orig:03d}.000-00"
                cand = Candidato(
                    id_concurso=concurso.id_concurso if concurso else 1,
                    id_certame=id_certame,
                    id_cargo=cargo_obj.id_cargo,
                    cpf=cpf_fake,
                    nome_completo=nome_raw,
                    classificacao_original=class_orig,
                    classificacao_efetiva=class_orig,
                    status_atual=status_calc,
                    edital_convocacao=conv_raw,
                    data_posse=posse_dt,
                    data_exoneracao=exon_dt,
                    edital_desistencia=desist_raw,
                    sub_judice=judice_raw
                )
                db.add(cand)
                db.commit()
                db.refresh(cand)
            else:
                cand.status_atual = status_calc
                cand.id_cargo = cargo_obj.id_cargo
                if conv_raw: cand.edital_convocacao = conv_raw
                if posse_dt: cand.data_posse = posse_dt
                if exon_dt: cand.data_exoneracao = exon_dt
                if desist_raw: cand.edital_desistencia = desist_raw
                if judice_raw: cand.sub_judice = judice_raw
                db.commit()

            if conv_raw or posse_dt or status_calc in ["CONVOCADO", "EMPOSSADO"]:
                conv = db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).first()
                data_doe = posse_dt or date.today()
                num_port = conv_raw if conv_raw else "Portaria Convocação"
                if not conv:
                    conv = Convocacao(
                        id_concurso=cand.id_concurso,
                        id_candidato=cand.id_candidato,
                        ordem_convocacao_global=cand.classificacao_original,
                        numero_portaria=num_port,
                        data_publicacao_doe=data_doe,
                        prazo_posse_limite=data_doe + timedelta(days=30),
                        compareceu=(status_calc == "EMPOSSADO")
                    )
                    db.add(conv)
                else:
                    if conv_raw: conv.numero_portaria = conv_raw
                    if posse_dt: conv.data_publicacao_doe = posse_dt
                    conv.compareceu = (status_calc == "EMPOSSADO")

            if posse_dt:
                mov_posse = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_POSSE").first()
                dt_posse_dt = datetime.combine(posse_dt, time.min)
                if not mov_posse:
                    mov_posse = MovimentacaoCandidato(
                        id_candidato=cand.id_candidato,
                        tipo_evento="TERMO_POSSE",
                        numero_processo_sei=conv_raw or "TERMO_POSSE",
                        data_registro=dt_posse_dt,
                        motivo_justificativa="Termo de Posse e Exercício registrado via planilha"
                    )
                    db.add(mov_posse)
                else:
                    mov_posse.data_registro = dt_posse_dt
                    if conv_raw: mov_posse.numero_processo_sei = conv_raw

            if desist_raw or "DESISTENTE" in status_calc:
                mov_des = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_DESISTENCIA").first()
                if not mov_des:
                    mov_des = MovimentacaoCandidato(
                        id_candidato=cand.id_candidato,
                        tipo_evento="TERMO_DESISTENCIA",
                        numero_processo_sei=desist_raw or "HOMOLOGACAO_DESISTENCIA",
                        data_registro=datetime.utcnow(),
                        motivo_justificativa=f"Homologação de Desistência nº {desist_raw}" if desist_raw else "Desistência registrada"
                    )
                    db.add(mov_des)
                else:
                    if desist_raw: mov_des.numero_processo_sei = desist_raw

            if exon_dt:
                mov_ex = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="EXONERACAO").first()
                dt_exon_dt = datetime.combine(exon_dt, time.min)
                if not mov_ex:
                    mov_ex = MovimentacaoCandidato(
                        id_candidato=cand.id_candidato,
                        tipo_evento="EXONERACAO",
                        numero_processo_sei="EXONERACAO",
                        data_registro=dt_exon_dt,
                        motivo_justificativa=f"Exoneração registrada em {exon_raw}"
                    )
                    db.add(mov_ex)
                else:
                    mov_ex.data_registro = dt_exon_dt

            afetados += 1

        for cid in cargos_afetados:
            empossados_cnt = db.query(Candidato).filter(
                (Candidato.id_certame == id_certame) &
                (Candidato.id_cargo == cid) &
                (Candidato.status_atual == "EMPOSSADO")
            ).count()
            
            lot = db.query(Lotacionograma).filter_by(id_cargo=cid).first()
            if lot:
                lot.vagas_ocupadas_oficial = empossados_cnt
                lot.vagas_disponiveis_oficial = max(0, lot.vagas_criadas_lei - empossados_cnt)

        db.commit()

        return {
            "status": "SUCESSO",
            "tipo": "Planilha/CSV de Provimento Tabular",
            "afetados": afetados
        }

    @staticmethod
    def process_ato_provimento_texto(text: str, db: Session, id_certame: int, tipo_ato_default: str = None) -> dict:
        """
        Analisa o texto de um documento de provimento (Portaria de Nomeação, Termo de Posse, Desistência, Fim de Fila, etc.),
        identifica automaticamente os candidatos pertencentes ao certame no banco de dados e atualiza seus status.
        """
        from models import Candidato, MovimentacaoCandidato, Convocacao
        from datetime import date, timedelta

        # Auto-detecção de planilha CSV/Tabular
        text_sample = text[:3000].lower()
        if ('nome' in text_sample or 'candidat' in text_sample) and any(k in text_sample for k in ['situac', 'status', 'convoc', 'posse', 'cargo', 'inscric']):
            res_csv = DocumentParserAI.process_csv_provimento_tabular(text, db, id_certame)
            if res_csv.get("afetados", 0) > 0:
                return res_csv

        candidatos_certame = db.query(Candidato).filter_by(id_certame=id_certame).all()
        if not candidatos_certame:
            return {"afetados": 0}

        afetados = 0
        text_lower = text.lower()

        novo_status = None
        tipo_evento = tipo_ato_default or "ATO_OFICIAL"

        if "posse" in text_lower or "exercício" in text_lower or "empossad" in text_lower or tipo_ato_default == "TERMO_POSSE":
            novo_status = "EMPOSSADO"
            tipo_evento = "TERMO_POSSE"
        elif "desistê" in text_lower or "renúnci" in text_lower or "desiste" in text_lower or tipo_ato_default == "TERMO_DESISTENCIA":
            novo_status = "DESISTENTE / RENÚNCIA"
            tipo_evento = "TERMO_DESISTENCIA"
        elif "fim de fila" in text_lower or "reclassifica" in text_lower or tipo_ato_default == "REQUERIMENTO_FIM_FILA":
            novo_status = "FINAL DA FILA (RECLASSIFICADO)"
            tipo_evento = "REQUERIMENTO_FIM_FILA"
        elif "não compareceu" in text_lower or "perda de prazo" in text_lower or "exclu" in text_lower or tipo_ato_default == "TERMO_EXCLUSAO":
            novo_status = "EXCLUÍDO / NÃO COMPARECEU"
            tipo_evento = "TERMO_EXCLUSAO"
        elif "judic" in text_lower or "liminar" in text_lower or "mandado" in text_lower or tipo_ato_default == "DECISAO_JUDICIAL":
            novo_status = "SUB JÚDICE / POSSE POR DECISÃO JUDICIAL"
            tipo_evento = "DECISAO_JUDICIAL"
        elif "convoc" in text_lower or "nomea" in text_lower or "chamam" in text_lower or tipo_ato_default == "PORTARIA_CONVOCACAO":
            novo_status = "CONVOCADO"
            tipo_evento = "PORTARIA_CONVOCACAO"

        if not novo_status:
            novo_status = "CONVOCADO"

        for cand in candidatos_certame:
            if cand.nome_completo and len(cand.nome_completo) >= 6:
                nome_cand = cand.nome_completo.strip()
                if nome_cand.lower() in text_lower:
                    st_anterior = cand.status_atual
                    cand.status_atual = novo_status

                    if novo_status == "FINAL DA FILA (RECLASSIFICADO)":
                        cand.classificacao_efetiva = cand.classificacao_original + 10

                    mov = MovimentacaoCandidato(
                        id_candidato=cand.id_candidato,
                        tipo_evento=tipo_evento,
                        numero_processo_sei="LEITURA_IA_AUTOMATICA",
                        motivo_justificativa=f"Status atualizado automaticamente via Leitura IA do documento (anterior: {st_anterior}).",
                        classificacao_anterior=cand.classificacao_original,
                        classificacao_nova=cand.classificacao_efetiva
                    )
                    db.add(mov)

                    if "CONVOCADO" in novo_status or tipo_evento == "PORTARIA_CONVOCACAO":
                        conv = db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).first()
                        if not conv:
                            conv = Convocacao(
                                id_concurso=cand.id_concurso,
                                id_candidato=cand.id_candidato,
                                ordem_convocacao_global=cand.classificacao_original,
                                numero_portaria="LEITURA_IA",
                                data_publicacao_doe=date.today(),
                                prazo_posse_limite=date.today() + timedelta(days=30),
                                compareceu=(novo_status == "EMPOSSADO")
                            )
                            db.add(conv)
                        else:
                            if novo_status == "EMPOSSADO":
                                conv.compareceu = True

                    afetados += 1

        db.commit()
        return {"afetados": afetados, "novo_status": novo_status}
