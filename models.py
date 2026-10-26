import enum
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Date, DateTime, 
    ForeignKey, Text, Numeric
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

class StatusFuncionalEnum(str, enum.Enum):
    ATIVO = "ATIVO"
    AFASTADO = "AFASTADO"
    APOSENTADO = "APOSENTADO"
    EXONERADO = "EXONERADO"

class StatusCandidatoEnum(str, enum.Enum):
    AGUARDANDO_CONVOCACAO = "AGUARDANDO_CONVOCACAO"
    CONVOCADO = "CONVOCADO"
    NOMEADO = "NOMEADO"
    DESISTENTE_FORMAL = "DESISTENTE_FORMAL"
    DESISTENTE_TACITO = "DESISTENTE_TACITO"
    FIM_DE_FILA = "FIM_DE_FILA"

class GravidadeAchadoEnum(str, enum.Enum):
    INFORMATIVO = "INFORMATIVO"
    ALERTA = "ALERTA"
    GRAVE = "GRAVE"
    IRREGULARIDADE_CRITICA = "IRREGULARIDADE_CRITICA"

class ModalidadeCertameEnum(str, enum.Enum):
    CONCURSO_PUBLICO = "CONCURSO_PUBLICO"
    PROCESSO_SELETIVO_PUBLICO = "PROCESSO_SELETIVO_PUBLICO"
    PROCESSO_SELETIVO_SIMPLIFICADO = "PROCESSO_SELETIVO_SIMPLIFICADO"

class Cargo(Base):
    __tablename__ = "cargos"

    id_cargo = Column(Integer, primary_key=True, index=True)
    codigo_cargo = Column(String(20), unique=True, nullable=False)
    nome_cargo = Column(String(150), nullable=False)
    nivel_escolaridade = Column(String(50))
    regime_juridico = Column(String(30), default="Estatutário")

    lotacao = relationship("Lotacionograma", back_populates="cargo", uselist=False)
    servidores = relationship("ServidorEfetivo", back_populates="cargo")
    contratos_temporarios = relationship("ContratoTemporario", back_populates="cargo")

class Lotacionograma(Base):
    __tablename__ = "lotacionograma"

    id_lotacao = Column(Integer, primary_key=True, index=True)
    id_cargo = Column(Integer, ForeignKey("cargos.id_cargo"), nullable=False)
    lei_criacao = Column(String(100), nullable=False)
    ano_vigencia = Column(Integer, nullable=False)
    vagas_criadas_lei = Column(Integer, nullable=False)
    vagas_ocupadas_oficial = Column(Integer, default=0)
    vagas_disponiveis_oficial = Column(Integer, default=0)
    
    cargo = relationship("Cargo", back_populates="lotacao")

class Concurso(Base):
    __tablename__ = "concursos"

    id_concurso = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=True)
    numero_edital = Column(String(50), nullable=False)
    ano_edital = Column(Integer, nullable=False)
    data_homologacao = Column(Date, nullable=False)
    data_validade_final = Column(Date, nullable=False)
    prazo_validade_meses = Column(Integer, default=12) # 12 meses (1 ano), 24 meses (2 anos)
    status = Column(String(30), default="VIGENTE") # VIGENTE, EXPIRADO, SUSPENSO

    vagas = relationship("ConcursoVaga", back_populates="concurso")
    candidatos = relationship("Candidato", back_populates="concurso")

class ConcursoVaga(Base):
    __tablename__ = "concursos_vagas"

    id_concurso_vaga = Column(Integer, primary_key=True, index=True)
    id_concurso = Column(Integer, ForeignKey("concursos.id_concurso"), nullable=False)
    id_cargo = Column(Integer, ForeignKey("cargos.id_cargo"), nullable=False)
    vagas_imediatas_edital = Column(Integer, nullable=False)
    vagas_cr = Column(Integer, default=0)

    concurso = relationship("Concurso", back_populates="vagas")
    cargo = relationship("Cargo")

class Candidato(Base):
    __tablename__ = "candidatos"

    id_candidato = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=True)
    id_concurso = Column(Integer, ForeignKey("concursos.id_concurso"), nullable=False)
    id_cargo = Column(Integer, ForeignKey("cargos.id_cargo"), nullable=False)
    cpf = Column(String(14), nullable=False)
    nome_completo = Column(String(200), nullable=False)
    classificacao_original = Column(Integer, nullable=False)
    tipo_cota = Column(String(30), default="AMPLA") # AMPLA, PCD, NEGROS
    status_atual = Column(String(40), default=StatusCandidatoEnum.AGUARDANDO_CONVOCACAO.value)
    classificacao_efetiva = Column(Integer, nullable=False)
    edital_convocacao = Column(String(100), nullable=True)
    data_posse = Column(Date, nullable=True)
    data_exoneracao = Column(Date, nullable=True)
    edital_desistencia = Column(String(100), nullable=True)
    sub_judice = Column(String(20), nullable=True)

    concurso = relationship("Concurso", back_populates="candidatos")
    cargo = relationship("Cargo")
    movimentacoes = relationship("MovimentacaoCandidato", back_populates="candidato")
    convocacoes = relationship("Convocacao", back_populates="candidato")

class MovimentacaoCandidato(Base):
    __tablename__ = "movimentacoes_candidato"

    id_movimentacao = Column(Integer, primary_key=True, index=True)
    id_candidato = Column(Integer, ForeignKey("candidatos.id_candidato"), nullable=False)
    tipo_evento = Column(String(50), nullable=False) # DESISTENCIA_EXPRESSA, DESISTENCIA_TACITA, PEDIDO_FINAL_FILA, DECISAO_JUDICIAL
    numero_processo_sei = Column(String(50))
    data_registro = Column(DateTime, default=datetime.utcnow)
    motivo_justificativa = Column(Text)
    classificacao_anterior = Column(Integer)
    classificacao_nova = Column(Integer)

    candidato = relationship("Candidato", back_populates="movimentacoes")

class Convocacao(Base):
    __tablename__ = "convocacoes"

    id_convocacao = Column(Integer, primary_key=True, index=True)
    id_concurso = Column(Integer, ForeignKey("concursos.id_concurso"), nullable=False)
    id_candidato = Column(Integer, ForeignKey("candidatos.id_candidato"), nullable=False)
    ordem_convocacao_global = Column(Integer, nullable=False)
    numero_portaria = Column(String(50), nullable=False)
    data_publicacao_doe = Column(Date, nullable=False)
    prazo_posse_limite = Column(Date, nullable=False)
    compareceu = Column(Boolean, nullable=True)

    candidato = relationship("Candidato", back_populates="convocacoes")
    concurso = relationship("Concurso")

class ServidorEfetivo(Base):
    __tablename__ = "servidores_efetivos"

    id_servidor = Column(Integer, primary_key=True, index=True)
    matricula = Column(String(30), unique=True, nullable=False)
    cpf = Column(String(14), nullable=False)
    nome = Column(String(200), nullable=False)
    id_cargo = Column(Integer, ForeignKey("cargos.id_cargo"), nullable=False)
    data_admissao = Column(Date, nullable=False)
    status_funcional = Column(String(30), default=StatusFuncionalEnum.ATIVO.value)

    cargo = relationship("Cargo", back_populates="servidores")
    afastamentos = relationship("Afastamento", back_populates="servidor")

class Afastamento(Base):
    __tablename__ = "afastamentos"

    id_afastamento = Column(Integer, primary_key=True, index=True)
    id_servidor = Column(Integer, ForeignKey("servidores_efetivos.id_servidor"), nullable=False)
    tipo_afastamento = Column(String(80), nullable=False) # LICENCA_MEDICA, LICENCA_MATERNIDADE, LICENCA_INTERESSE_PARTICULAR
    data_inicio = Column(Date, nullable=False)
    data_fim_prevista = Column(Date, nullable=False)
    data_retorno_efetivo = Column(Date, nullable=True)
    gera_direito_substituicao = Column(Boolean, default=True)

    servidor = relationship("ServidorEfetivo", back_populates="afastamentos")

class ContratoTemporario(Base):
    __tablename__ = "contratos_temporarios"

    id_contrato = Column(Integer, primary_key=True, index=True)
    numero_contrato_pss = Column(String(50), unique=True, nullable=False)
    cpf = Column(String(14), nullable=False)
    nome_contratado = Column(String(200), nullable=False)
    id_cargo = Column(Integer, ForeignKey("cargos.id_cargo"), nullable=False)
    motivo_contratacao = Column(String(50), nullable=False) # SUBSTITUICAO_AFASTAMENTO, VACANCIA_SEM_CONCURSO, EXCEPCIONAL_INTERESSE
    id_servidor_substituido = Column(Integer, ForeignKey("servidores_efetivos.id_servidor"), nullable=True)
    data_inicio_contrato = Column(Date, nullable=False)
    data_fim_prevista = Column(Date, nullable=False)
    data_rescisao_efetiva = Column(Date, nullable=True)
    status_contrato = Column(String(30), default="VIGENTE")

    cargo = relationship("Cargo", back_populates="contratos_temporarios")
    servidor_substituido = relationship("ServidorEfetivo")

class Usuario(Base):
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), unique=True, nullable=False)
    email_recuperacao = Column(String(150), nullable=True)
    codigo_recuperacao = Column(String(20), nullable=True)
    codigo_expiracao = Column(DateTime, nullable=True)
    nome = Column(String(150), nullable=False)
    senha_hash = Column(String(255), nullable=True) # None no primeiro acesso
    perfil = Column(String(50), default="ADMIN_MASTER") # ADMIN_MASTER, AUDITOR
    primeiro_acesso = Column(Boolean, default=True)
    data_criacao = Column(DateTime, default=datetime.utcnow)

class DocumentoRepositorio(Base):
    __tablename__ = "documentos_repositorio"

    id_documento = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=True)
    nome_arquivo_original = Column(String(255), nullable=False)
    caminho_arquivo = Column(String(500), nullable=False)
    tipo_documento = Column(String(80), nullable=False) # EDITAL, PORTARIA_CONVOCACAO, LOTACIONOGRAMA, TERMO_DESISTENCIA, PSS, OUTRO
    tamanho_bytes = Column(Integer, default=0)
    data_upload = Column(DateTime, default=datetime.utcnow)
    status_processamento_ia = Column(String(50), default="PROCESSADO_IA") # PROCESSADO_IA, PENDENTE, ERRO
    resumo_extracao = Column(Text, nullable=True)

    certame = relationship("CertameAbertura")

class AuditoriaAchado(Base):
    __tablename__ = "auditoria_achados"

    id_achado = Column(Integer, primary_key=True, index=True)
    modulo_origem = Column(String(50), nullable=False) # LOTACIONOGRAMA, CONCURSO_CLASSIFICACAO, CONTRATOS_TEMPORARIOS, PRE_EDITAL_TCE
    gravidade = Column(String(30), nullable=False) # INFORMATIVO, ALERTA, GRAVE, IRREGULARIDADE_CRITICA
    titulo = Column(String(200), nullable=False)
    descricao_detalhada = Column(Text, nullable=False)
    base_legal = Column(Text)
    id_referencia = Column(Integer, nullable=True)
    data_identificacao = Column(DateTime, default=datetime.utcnow)
    status_tramitacao = Column(String(30), default="PENDENTE") # PENDENTE, NOTIFICADO, JUSTIFICADO, SANADO

# --- NOVOS MODELOS DE ABERTURA DE CERTAME E ANÁLISE PRÉVIA TCE-MT ---

class CertameAbertura(Base):
    __tablename__ = "certames_abertura"

    id_certame = Column(Integer, primary_key=True, index=True)
    modalidade = Column(String(50), nullable=False) # CONCURSO_PUBLICO, PROCESSO_SELETIVO_PUBLICO, PROCESSO_SELETIVO_SIMPLIFICADO
    numero_certame = Column(String(50), nullable=False) # Ex: 001/2024
    ano = Column(Integer, nullable=False, default=2024)
    municipio = Column(String(100), default="Pontes e Lacerda - MT")
    orgao_solicitante = Column(String(150), default="Prefeitura Municipal de Pontes e Lacerda - MT")
    prefeito_ordenador = Column(String(150), default="Alcino Pereira Barcelos")
    secretario_solicitante = Column(String(150), default="Anderson da Silva Lima")
    contador_responsavel = Column(String(150), default="Márcio Henrique Tosti – CRC nº 7815/O")
    banca_examinadora = Column(String(200), default="IMPÉRIO ASSESSORIA E CONCURSOS LTDA (Pregão Presencial 077/2024)")
    lei_autorizadora = Column(String(150), default="Lei Municipal nº 1.948 de 22/10/2018")
    leis_carreira = Column(String(255), default="Lei Complementar nº 63/2008 e Lei Complementar nº 92/2010")
    data_abertura_processo = Column(Date, default=date.today)
    status_auditoria = Column(String(50), default="EM_ANALISE") # EM_ANALISE, PARECER_PREVIO_GERADO, PARECER_DEFINITIVO_EMITIDO

    anexos = relationship("CertameAnexo", back_populates="certame", cascade="all, delete-orphan")
    analises_tce = relationship("CertameAnaliseTCE", back_populates="certame", cascade="all, delete-orphan")
    parecer = relationship("ParecerTecnico", back_populates="certame", uselist=False, cascade="all, delete-orphan")
    fase_oficial = relationship("CertameFaseOficial", back_populates="certame", uselist=False, cascade="all, delete-orphan")
    parecer_oficial = relationship("ParecerOficial", back_populates="certame", uselist=False, cascade="all, delete-orphan")

class CertameFaseOficial(Base):
    __tablename__ = "certames_fase_oficial"

    id_fase_oficial = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False, unique=True)
    
    # 1. Edital de Abertura Oficial
    data_publicacao_edital = Column(Date, nullable=True)
    numero_diario_oficial_edital = Column(String(100), nullable=True)
    link_diario_oficial_edital = Column(String(500), nullable=True)
    
    # 2. Homologação das Inscrições
    data_homologacao_inscricoes = Column(Date, nullable=True)
    total_inscritos = Column(Integer, default=0)
    total_isencoes_deferidas = Column(Integer, default=0)
    
    # 3. Prazos e Recursos
    prazo_recurso_preliminar = Column(String(200), nullable=True)
    status_recursos = Column(String(100), default="SEM_RECURSOS") # SEM_RECURSOS, RECURSOS_EM_ANALISE, DEFERIDOS
    
    # 4. Realização das Provas
    data_realizacao_provas = Column(Date, nullable=True)
    gabarito_oficial_publicado = Column(Boolean, default=False)
    
    # 5. Resultado Parcial & Títulos
    data_resultado_parcial = Column(Date, nullable=True)
    data_prova_titulos = Column(Date, nullable=True)
    
    # 6. Resultado Final & Homologação
    data_resultado_final = Column(Date, nullable=True)
    data_homologacao_resultado_final = Column(Date, nullable=True)
    numero_decreto_homologacao = Column(String(100), nullable=True)
    prazo_validade_meses = Column(Integer, default=12) # 12 meses (1 ano), 24 meses (2 anos)
    status_fase_oficial = Column(String(50), default="EM_ANDAMENTO") # EM_ANDAMENTO, HOMOLOGADO_FINAL

    certame = relationship("CertameAbertura", back_populates="fase_oficial")

class CertameAnexo(Base):
    __tablename__ = "certames_anexos"

    id_anexo = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    tipo_documento = Column(String(80), nullable=False) 
    # MINUTA_EDITAL, LOTACIONOGRAMA, LEI_AUTORIZADORA, ESTUDO_IMPACTO_LRF, DECLARACAO_COMPATIBILIDADE, PORTARIA_COMISSAO, COMPROVANTE_LICITACAO_BANCA, DECLARACAO_CONCURSO_PRETERITO
    nome_arquivo = Column(String(255), nullable=False)
    caminho_arquivo = Column(String(500), nullable=False)
    conteudo_texto = Column(Text, nullable=True)
    data_upload = Column(DateTime, default=datetime.utcnow)

    certame = relationship("CertameAbertura", back_populates="anexos")

class CertameAnaliseTCE(Base):
    __tablename__ = "certames_analises_tce"

    id_analise = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    categoria_cheque = Column(String(100), nullable=False) # DOCUMENTOS_EXIGIDOS, JUSTIFICATIVA, AUTORIZACAO, BANCA_EXAMINADORA, REGULAMENTO_LEI, IMPACTO_LRF, DECLARACAO_COMPATIBILIDADE, COMISSAO_ORGANIZADORA, LOTACIONOGRAMA_VS_EDITAL, DISCREPANCIAS_CARREIRA, PRAZOS_ISENCAO
    item_exigencia = Column(String(200), nullable=False)
    status_item = Column(String(30), nullable=False) # CONFORME, RESSALVA, NAO_CONFORME
    fundamentacao_legal = Column(Text)
    detalhe_constatacao = Column(Text)

    certame = relationship("CertameAbertura", back_populates="analises_tce")

class ParecerTecnico(Base):
    __tablename__ = "pareceres_tecnicos"

    id_parecer = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    numero_parecer = Column(String(50), nullable=False) # Ex: PARECER Nº 166/2024
    assunto = Column(Text, nullable=False)
    tipo_conclusao = Column(String(40), default="FAVORAVEL_COM_RESSALVA") # FAVORAVEL, FAVORAVEL_COM_RESSALVA, DESFAVORAVEL
    
    # Texto completo editável do parecer dividido em seções para controle preciso
    fundamentacao_legal = Column(Text)
    documentos_exigidos_texto = Column(Text)
    justificativa_texto = Column(Text)
    autorizacao_texto = Column(Text)
    banca_executora_texto = Column(Text)
    regulamento_autorizacao_texto = Column(Text)
    impacto_orcamentario_texto = Column(Text)
    declaracao_compatibilidade_texto = Column(Text)
    comissao_organizadora_texto = Column(Text)
    lotacionograma_texto = Column(Text)
    edital_normativo_texto = Column(Text)
    publicacao_ampla_doc_tce_texto = Column(Text)
    reserva_vagas_pcd_texto = Column(Text)
    discrepancias_ressalvas_texto = Column(Text)
    prazos_isencoes_texto = Column(Text)
    conclusao_parecer_texto = Column(Text)
    
    auditor_responsavel = Column(String(150), default="Jansen de Pinho e Silva - Controladoria e Auditoria Municipal")
    data_emissao = Column(Date, default=date.today)
    status = Column(String(30), default="RASCUNHO_EDITAVEL") # RASCUNHO_EDITAVEL, DEFINITIVO_EMITIDO

    certame = relationship("CertameAbertura", back_populates="parecer")



class ParecerOficial(Base):
    __tablename__ = "pareceres_oficiais"

    id_parecer_oficial = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    numero_parecer = Column(String(80), nullable=False)
    objeto_analise = Column(Text, nullable=False)
    interessado_orgao = Column(String(255), nullable=False)
    fundamentacao_legal = Column(Text, nullable=False)
    relatorio_historico = Column(Text, nullable=False)
    analise_tecnica_juridica = Column(Text, nullable=False)
    conclusao_tipo = Column(String(40), default="REGULAR_COM_RESSALVAS") # REGULAR, REGULAR_COM_RESSALVAS, IRREGULAR
    justificativa_conclusao = Column(Text, nullable=False)
    auditor_responsavel = Column(String(150), default="Equipe de Controle Interno - Auditoria de Pessoal")
    data_emissao = Column(Date, default=date.today)
    status = Column(String(30), default="RASCUNHO_EDITAVEL") # RASCUNHO_EDITAVEL, DEFINITIVO_EMITIDO

    certame = relationship("CertameAbertura", back_populates="parecer_oficial")

class CertameAcompanhamentoAto(Base):
    __tablename__ = "certames_acompanhamento_atos"

    id_ato = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    numero_ato = Column(String(120), nullable=False)
    tipo_ato = Column(String(60), nullable=False) # PORTARIA_CONVOCACAO, TERMO_POSSE, TERMO_DESISTENCIA, REQUERIMENTO_FIM_FILA, DECISAO_JUDICIAL, TERMO_EXCLUSAO
    data_ato = Column(Date, default=date.today)
    resumo_afetados = Column(Text, nullable=True)
    caminho_arquivo = Column(String(500), nullable=True)
    data_registro = Column(DateTime, default=datetime.utcnow)

    certame = relationship("CertameAbertura")

class CertameVigenciaAto(Base):
    __tablename__ = "certames_vigencia_atos"

    id_vigencia_ato = Column(Integer, primary_key=True, index=True)
    id_certame = Column(Integer, ForeignKey("certames_abertura.id_certame"), nullable=False)
    tipo_ato = Column(String(80), nullable=False) # DECRETO_HOMOLOGACAO, DECRETO_PRORROGACAO, TERMO_SUSPENSAO, TERMO_RETOMADA, ADITIVO_VIGENCIA
    numero_ato = Column(String(120), nullable=False) # Ex: "Decreto Municipal nº 456/2024"
    data_publicacao = Column(Date, nullable=False)
    data_inicio_vigencia = Column(Date, nullable=True)
    prazo_validade_meses = Column(Integer, default=24) # 24 meses (2 anos), 12 meses, etc.
    nova_data_fim_vigencia = Column(Date, nullable=False)
    motivo_justificativa = Column(Text, nullable=True)
    caminho_arquivo = Column(String(500), nullable=True)
    nome_arquivo = Column(String(255), nullable=True)
    data_registro = Column(DateTime, default=datetime.utcnow)

    certame = relationship("CertameAbertura")


from sqlalchemy import text

DATABASE_URL = "sqlite:///./auditoria_pessoal.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE documentos_repositorio ADD COLUMN id_certame INTEGER REFERENCES certames_abertura(id_certame)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE lotacionograma ADD COLUMN vagas_ocupadas_oficial INTEGER DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE lotacionograma ADD COLUMN vagas_disponiveis_oficial INTEGER DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE pareceres_tecnicos ADD COLUMN publicacao_ampla_doc_tce_texto TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE pareceres_tecnicos ADD COLUMN reserva_vagas_pcd_texto TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE candidatos ADD COLUMN id_certame INTEGER REFERENCES certames_abertura(id_certame)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE concursos ADD COLUMN id_certame INTEGER REFERENCES certames_abertura(id_certame)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE concursos ADD COLUMN prazo_validade_meses INTEGER DEFAULT 12"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE certames_fase_oficial ADD COLUMN prazo_validade_meses INTEGER DEFAULT 12"))
            conn.commit()
        except Exception:
            pass
        for col in ["edital_convocacao TEXT", "data_posse DATE", "data_exoneracao DATE", "edital_desistencia TEXT", "sub_judice TEXT"]:
            try:
                conn.execute(text(f"ALTER TABLE candidatos ADD COLUMN {col}"))
                conn.commit()
            except Exception:
                pass


