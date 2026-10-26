import os
import uuid
import hashlib
from datetime import date, datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, Response
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from models import (
    SessionLocal, init_db, Cargo, Lotacionograma, Concurso, ConcursoVaga,
    Candidato, MovimentacaoCandidato, Convocacao, ServidorEfetivo, Afastamento,
    ContratoTemporario, AuditoriaAchado, DocumentoRepositorio, Usuario,
    CertameAbertura, CertameAnexo, CertameAnaliseTCE, ParecerTecnico, CertameFaseOficial, ParecerOficial, CertameAcompanhamentoAto, CertameVigenciaAto
)
from audit_engine import AuditEngine
from document_parser import DocumentParserAI
from pdf_generator import PDFTextGenerator

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="SIAP - Sistema Integrado de Auditoria de Pessoal", version="3.1.0")

from fastapi.staticfiles import StaticFiles
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "img"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")

def sha256_filter(val):
    if not val: return "SIAP-HASH-NULL"
    return hashlib.sha256(str(val).encode('utf-8')).hexdigest()

templates.env.filters["hash_sha256"] = sha256_filter

def get_certames_menu_global():
    db = SessionLocal()
    try:
        from models import Concurso
        from datetime import date
        today = date.today()
        certames = db.query(CertameAbertura).order_by(CertameAbertura.id_certame.desc()).all()
        for c in certames:
            conc = db.query(Concurso).filter_by(id_certame=c.id_certame).first()
            dt_val = conc.data_validade_final if conc else None
            st = (conc.status if conc else '').upper()
            c.is_expirado = bool((dt_val and dt_val < today) or st == 'EXPIRADO')
        return certames
    except Exception:
        return []
    finally:
        db.close()

templates.env.globals["get_certames_menu"] = get_certames_menu_global

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def sincronizar_pdfs_texto_direto(db: Session):
    anexos = db.query(CertameAnexo).all()
    for a in anexos:
        caminho = a.caminho_arquivo
        precisa_gerar = False
        if not caminho or caminho == "TEXTO_DIRETO" or not os.path.exists(caminho):
            precisa_gerar = True
        
        if precisa_gerar and a.conteudo_texto and a.conteudo_texto.strip():
            certame = db.query(CertameAbertura).filter_by(id_certame=a.id_certame).first()
            num_cert = certame.numero_certame if certame else "001/2024"
            pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{a.id_certame}")
            
            res_pdf = PDFTextGenerator.gerar_pdf_de_texto(
                id_certame=a.id_certame,
                numero_certame=num_cert,
                tipo_documento=a.tipo_documento,
                conteudo_texto=a.conteudo_texto,
                pasta_upload=pasta_certame
            )
            a.caminho_arquivo = res_pdf["caminho_arquivo"]
            a.nome_arquivo = res_pdf["nome_arquivo"]

            doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=a.id_certame, tipo_documento=a.tipo_documento).first()
            if doc_repo:
                doc_repo.caminho_arquivo = res_pdf["caminho_arquivo"]
                doc_repo.nome_arquivo_original = res_pdf["nome_arquivo"]
                doc_repo.tamanho_bytes = res_pdf["tamanho_bytes"]
            else:
                doc_repo = DocumentoRepositorio(
                    id_certame=a.id_certame,
                    nome_arquivo_original=res_pdf["nome_arquivo"],
                    caminho_arquivo=res_pdf["caminho_arquivo"],
                    tipo_documento=a.tipo_documento,
                    tamanho_bytes=res_pdf["tamanho_bytes"],
                    status_processamento_ia="GERADO_PDF_IA",
                    resumo_extracao=f"PDF de texto gerado para o Certame #{num_cert}."
                )
                db.add(doc_repo)
            db.commit()

@app.on_event("startup")
def startup_event():
    init_db()
    db = SessionLocal()
    master = db.query(Usuario).filter_by(email="prof.jan100@gmail.com").first()
    if not master:
        master = Usuario(
            email="prof.jan100@gmail.com",
            nome="Prof. Jansen Pinho",
            senha_hash=None,
            perfil="ADMIN_MASTER",
            primeiro_acesso=True
        )
        db.add(master)
        db.commit()

    cert = db.query(CertameAbertura).first()
    if not cert:
        cert = CertameAbertura(
            modalidade="PROCESSO_SELETIVO_SIMPLIFICADO",
            numero_certame="001/2024",
            ano=2024,
            municipio="Pontes e Lacerda - MT",
            orgao_solicitante="Prefeitura Municipal de Pontes e Lacerda - MT",
            prefeito_ordenador="Alcino Pereira Barcelos",
            secretario_solicitante="Anderson da Silva Lima",
            contador_responsavel="Márcio Henrique Tosti – CRC nº 7815/O",
            banca_examinadora="IMPÉRIO ASSESSORIA E CONCURSOS LTDA (Pregão Presencial 077/2024)",
            lei_autorizadora="Lei Municipal nº 1.948 de 22/10/2018",
            leis_carreira="Lei Complementar nº 63/2008 e Lei Complementar nº 92/2010"
        )
        db.add(cert)
        db.commit()
        db.refresh(cert)

    sincronizar_pdfs_texto_direto(db)

    engine = AuditEngine(db)
    certames = db.query(CertameAbertura).all()
    for c in certames:
        if not c.parecer:
            engine.executar_analise_tce_certame(c.id_certame)

    db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_session")
    if not user_email:
        return None
    return db.query(Usuario).filter_by(email=user_email).first()

# Rota de Login (GET)
@app.get("/login", response_class=HTMLResponse)
def tela_login(request: Request, erro: str = None, info: str = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "erro": erro,
        "info": info
    })

# Rota de Login (POST)
@app.post("/login")
def processar_login(
    request: Request,
    response: Response,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db)
):
    email = email.strip().lower()
    user = db.query(Usuario).filter_by(email=email).first()

    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": "Usuário não cadastrado no sistema.",
            "email_digitado": email
        })

    if user.primeiro_acesso or user.senha_hash is None:
        user.senha_hash = hash_senha(senha)
        user.primeiro_acesso = False
        db.commit()
        resp = RedirectResponse(url="/?msg=Senha cadastrada com sucesso!", status_code=303)
        resp.set_cookie(key="user_session", value=user.email, httponly=True)
        return resp

    if user.senha_hash != hash_senha(senha):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": "Senha incorreta para o e-mail informado.",
            "email_digitado": email
        })

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(key="user_session", value=user.email, httponly=True)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(key="user_session")
    return resp

# ==============================================================================
# ROTAS DE RECUPERAÇÃO DE SENHA POR E-MAIL CADASTRADO
# ==============================================================================
@app.get("/recuperar-senha", response_class=HTMLResponse)
def tela_recuperar_senha(request: Request, erro: str = None, msg: str = None):
    return templates.TemplateResponse("recuperar_senha.html", {
        "request": request,
        "erro": erro,
        "msg": msg,
        "etapa": "solicitar"
    })

@app.post("/recuperar-senha/solicitar", response_class=HTMLResponse)
def solicitar_codigo_recuperacao(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    import random
    email_clean = email.strip().lower()
    
    # Busca o usuário pelo e-mail institucional ou pelo e-mail de recuperação cadastrado
    user = db.query(Usuario).filter(
        (Usuario.email == email_clean) | (Usuario.email_recuperacao == email_clean)
    ).first()
    
    if not user:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": f"Nenhum usuário localizado com o e-mail '{email_clean}'. Verifique os dados digitados ou contate a administração.",
            "etapa": "solicitar"
        })
        
    email_destino = user.email_recuperacao or user.email
    
    # Gerar código de 6 dígitos numéricos
    codigo = f"{random.randint(100000, 999999)}"
    user.codigo_recuperacao = codigo
    user.codigo_expiracao = datetime.now() + timedelta(minutes=15)
    db.commit()
    
    # Mascarar o e-mail de recuperação para segurança na exibição (ex: jo***o@gmail.com)
    partes = email_destino.split("@")
    if len(partes) == 2:
        user_part, domain_part = partes
        if len(user_part) > 2:
            mascarado = user_part[:2] + "***" + user_part[-1] + "@" + domain_part
        else:
            mascarado = user_part[0] + "***@" + domain_part
    else:
        mascarado = email_destino[:2] + "***"
        
    msg_sucesso = f"Código de verificação gerado para o e-mail de recuperação cadastrado ({mascarado})."
    
    return templates.TemplateResponse("recuperar_senha.html", {
        "request": request,
        "msg": msg_sucesso,
        "etapa": "confirmar",
        "email": user.email,
        "email_recuperacao_mascarado": mascarado,
        "codigo_dev": codigo
    })

@app.post("/recuperar-senha/confirmar", response_class=HTMLResponse)
def confirmar_recuperacao_senha(
    request: Request,
    email: str = Form(...),
    codigo: str = Form(...),
    nova_senha: str = Form(...),
    confirmar_nova_senha: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    codigo_clean = codigo.strip()
    
    user = db.query(Usuario).filter_by(email=email_clean).first()
    if not user:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": "Usuário não localizado no sistema.",
            "etapa": "solicitar"
        })
        
    recup_email = user.email_recuperacao or user.email
    partes = recup_email.split("@")
    if len(partes) == 2:
        user_part, domain_part = partes
        if len(user_part) > 2:
            mascarado = user_part[:2] + "***" + user_part[-1] + "@" + domain_part
        else:
            mascarado = user_part[0] + "***@" + domain_part
    else:
        mascarado = recup_email[:2] + "***"
        
    if not user.codigo_recuperacao or user.codigo_recuperacao != codigo_clean:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": "Código de verificação incorreto ou inválido.",
            "etapa": "confirmar",
            "email": user.email,
            "email_recuperacao_mascarado": mascarado,
            "codigo_dev": user.codigo_recuperacao
        })
        
    if not user.codigo_expiracao or datetime.now() > user.codigo_expiracao:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": "O código de verificação expirou (validade: 15 minutos). Solicite um novo código.",
            "etapa": "solicitar"
        })
        
    if len(nova_senha) < 6:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": "A nova senha deve possuir no mínimo 6 caracteres.",
            "etapa": "confirmar",
            "email": user.email,
            "email_recuperacao_mascarado": mascarado,
            "codigo_dev": user.codigo_recuperacao
        })
        
    if nova_senha != confirmar_nova_senha:
        return templates.TemplateResponse("recuperar_senha.html", {
            "request": request,
            "erro": "A confirmação de senha não confere com a nova senha digitada.",
            "etapa": "confirmar",
            "email": user.email,
            "email_recuperacao_mascarado": mascarado,
            "codigo_dev": user.codigo_recuperacao
        })
        
    user.senha_hash = hash_senha(nova_senha)
    user.codigo_recuperacao = None
    user.codigo_expiracao = None
    user.primeiro_acesso = False
    db.commit()
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "info": f"Senha redefinida com sucesso para o usuário {user.nome}! Faça login com sua nova credencial.",
        "email_digitado": user.email
    })

# Dashboard Principal
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)

    achados = db.query(AuditoriaAchado).order_by(
        AuditoriaAchado.gravidade.desc(), 
        AuditoriaAchado.data_identificacao.desc()
    ).all()

    total_criticos = sum(1 for a in achados if a.gravidade == "IRREGULARIDADE_CRITICA" and a.status_tramitacao == "PENDENTE")
    total_graves = sum(1 for a in achados if a.gravidade == "GRAVE" and a.status_tramitacao == "PENDENTE")
    total_cargos = db.query(Cargo).count()
    total_documentos = db.query(DocumentoRepositorio).count()

    lotacoes_raw = db.query(Lotacionograma).all()
    lotacoes = []
    for lot in lotacoes_raw:
        efetivos = db.query(ServidorEfetivo).filter_by(id_cargo=lot.id_cargo, status_funcional='ATIVO').count()
        convocacoes = db.query(Convocacao).join(Candidato).filter(Candidato.id_cargo == lot.id_cargo, Convocacao.compareceu == None).count()
        saldo = lot.vagas_criadas_lei - (efetivos + convocacoes)
        lotacoes.append({
            "cargo": lot.cargo,
            "vagas_criadas_lei": lot.vagas_criadas_lei,
            "efetivos_ativos": efetivos,
            "convocacoes_pendentes": convocacoes,
            "saldo": saldo
        })

    temporarios = db.query(ContratoTemporario).filter_by(status_contrato="VIGENTE").all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "usuario": usuario,
        "achados": achados,
        "total_criticos": total_criticos,
        "total_graves": total_graves,
        "total_cargos": total_cargos,
        "total_documentos": total_documentos,
        "lotacoes": lotacoes,
        "temporarios": temporarios
    })

# --- MÓDULO LOTACIONOGRAMA LEGAL ---
@app.get("/modulo/lotacionograma", response_class=HTMLResponse)
def modulo_lotacionograma(request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    
    lotacoes_raw = db.query(Lotacionograma).all()
    lotacoes = []
    totais = {
        "vagas_existentes": 0,
        "vagas_ocupadas": 0,
        "vagas_disponiveis": 0,
        "efetivos_ativos": 0,
        "convocacoes_pendentes": 0,
        "total_cargos": len(lotacoes_raw)
    }
    for lot in lotacoes_raw:
        efetivos = db.query(ServidorEfetivo).filter_by(id_cargo=lot.id_cargo, status_funcional='ATIVO').count()
        convocacoes = db.query(Convocacao).join(Candidato).filter(Candidato.id_cargo == lot.id_cargo, Convocacao.compareceu == None).count()
        
        vagas_existentes = lot.vagas_criadas_lei
        if (efetivos + convocacoes) > 0:
            vagas_ocupadas = efetivos + convocacoes
            vagas_disponiveis = vagas_existentes - vagas_ocupadas
        else:
            vagas_ocupadas = getattr(lot, "vagas_ocupadas_oficial", 0) or 0
            vagas_disponiveis = getattr(lot, "vagas_disponiveis_oficial", 0) or (vagas_existentes - vagas_ocupadas)

        totais["vagas_existentes"] += vagas_existentes
        totais["vagas_ocupadas"] += vagas_ocupadas
        totais["vagas_disponiveis"] += vagas_disponiveis
        totais["efetivos_ativos"] += efetivos
        totais["convocacoes_pendentes"] += convocacoes

        lotacoes.append({
            "cargo": lot.cargo,
            "vagas_criadas_lei": vagas_existentes,
            "vagas_existentes": vagas_existentes,
            "efetivos_ativos": efetivos,
            "convocacoes_pendentes": convocacoes,
            "vagas_ocupadas": vagas_ocupadas,
            "vagas_disponiveis": vagas_disponiveis,
            "saldo": vagas_disponiveis,
            "lei_criacao": lot.lei_criacao
        })

    documento_oficial = db.query(DocumentoRepositorio).filter_by(tipo_documento="LOTACIONOGRAMA").order_by(DocumentoRepositorio.data_upload.desc()).first()
    if not documento_oficial:
        anexo_lot = db.query(CertameAnexo).filter_by(tipo_documento="LOTACIONOGRAMA").order_by(CertameAnexo.data_upload.desc()).first()
        if anexo_lot:
            documento_oficial = DocumentoRepositorio(
                id_documento=anexo_lot.id_anexo,
                nome_arquivo_original=anexo_lot.nome_arquivo,
                caminho_arquivo=anexo_lot.caminho_arquivo,
                tipo_documento="LOTACIONOGRAMA",
                tamanho_bytes=1024,
                data_upload=anexo_lot.data_upload,
                status_processamento_ia="PROCESSADO_COM_SUCESSO",
                resumo_extracao="Lotacionograma Completo e Oficial do Município (Servidores Efetivos)."
            )

    return templates.TemplateResponse("modulo_lotacionograma.html", {
        "request": request,
        "usuario": usuario,
        "lotacoes": lotacoes,
        "totais": totais,
        "documento_oficial": documento_oficial,
        "mensagem": msg
    })

@app.post("/modulo/lotacionograma/importar-pdf")
async def importar_pdf_lotacionograma_oficial(
    arquivo: UploadFile = File(None),
    conteudo_texto: str = Form(None),
    db: Session = Depends(get_db)
):
    texto_extraido = ""
    nome_salvo = "Lotacionograma_Oficial_Municipio.pdf"
    pasta_dest = os.path.join(UPLOAD_DIR, "lotacionograma")
    os.makedirs(pasta_dest, exist_ok=True)
    caminho_salvo = os.path.join(pasta_dest, f"{uuid.uuid4().hex[:8]}_{nome_salvo}")
    tamanho_bytes = 0

    if arquivo and arquivo.filename:
        conteudo_bytes = await arquivo.read()
        tamanho_bytes = len(conteudo_bytes)
        nome_salvo = arquivo.filename
        caminho_salvo = os.path.join(pasta_dest, f"{uuid.uuid4().hex[:8]}_{nome_salvo}")
        with open(caminho_salvo, "wb") as f:
            f.write(conteudo_bytes)
        
        if arquivo.filename.lower().endswith(".pdf"):
            texto_extraido = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
        else:
            texto_extraido = conteudo_bytes.decode("utf-8", errors="ignore")
    elif conteudo_texto and conteudo_texto.strip():
        texto_extraido = conteudo_texto.strip()
        res_pdf = PDFTextGenerator.gerar_pdf_de_texto(
            id_certame=0,
            numero_certame="OFICIAL-GERAL",
            tipo_documento="LOTACIONOGRAMA",
            conteudo_texto=texto_extraido,
            pasta_upload=pasta_dest
        )
        caminho_salvo = res_pdf["caminho_arquivo"]
        nome_salvo = res_pdf["nome_arquivo"]
        tamanho_bytes = res_pdf["tamanho_bytes"]
    else:
        return RedirectResponse(url="/modulo/lotacionograma?msg=Aviso: Selecione um arquivo PDF do Lotacionograma Oficial ou insira o texto.", status_code=303)

    # Processar IA para extrair cargos e vagas no banco relacional (Lotacionograma / Cargo)
    res_ia = DocumentParserAI.process_lotacionograma_text(texto_extraido, db)
    qtd_cargos = res_ia.get("registros_processados", 0)

    # Registrar/Atualizar no Repositório Documental
    doc_repo = db.query(DocumentoRepositorio).filter_by(tipo_documento="LOTACIONOGRAMA").first()
    if not doc_repo:
        doc_repo = DocumentoRepositorio(
            nome_arquivo_original=nome_salvo,
            caminho_arquivo=caminho_salvo,
            tipo_documento="LOTACIONOGRAMA",
            tamanho_bytes=tamanho_bytes,
            status_processamento_ia="LOTACIONOGRAMA_OFICIAL_PROCESSADO",
            resumo_extracao=f"Lotacionograma Completo e Oficial do Município importado. {qtd_cargos} cargo(s) processados por IA."
        )
        db.add(doc_repo)
    else:
        doc_repo.nome_arquivo_original = nome_salvo
        doc_repo.caminho_arquivo = caminho_salvo
        doc_repo.tamanho_bytes = tamanho_bytes
        doc_repo.status_processamento_ia = "LOTACIONOGRAMA_OFICIAL_PROCESSADO"
        doc_repo.resumo_extracao = f"Lotacionograma Completo e Oficial do Município atualizado por IA. {qtd_cargos} cargo(s) processados."

    db.commit()

    # Replicar para o Passo 1 (LOTACIONOGRAMA) de todos os certames cadastrados no sistema
    certames = db.query(CertameAbertura).all()
    for c in certames:
        anexo_c = db.query(CertameAnexo).filter_by(id_certame=c.id_certame, tipo_documento="LOTACIONOGRAMA").first()
        if not anexo_c:
            anexo_c = CertameAnexo(
                id_certame=c.id_certame,
                tipo_documento="LOTACIONOGRAMA",
                nome_arquivo=nome_salvo,
                caminho_arquivo=caminho_salvo,
                conteudo_texto=texto_extraido
            )
            db.add(anexo_c)
        else:
            anexo_c.nome_arquivo = nome_salvo
            anexo_c.caminho_arquivo = caminho_salvo
            anexo_c.conteudo_texto = texto_extraido
        
        # Garantir repositório para o certame
        doc_c = db.query(DocumentoRepositorio).filter_by(id_certame=c.id_certame, tipo_documento="LOTACIONOGRAMA").first()
        if not doc_c:
            doc_c = DocumentoRepositorio(
                id_certame=c.id_certame,
                nome_arquivo_original=nome_salvo,
                caminho_arquivo=caminho_salvo,
                tipo_documento="LOTACIONOGRAMA",
                tamanho_bytes=tamanho_bytes,
                status_processamento_ia="SINCRONIZADO_LOTACIONOGRAMA_GERAL",
                resumo_extracao=f"Replicado do Lotacionograma Completo e Oficial do Município."
            )
            db.add(doc_c)
        else:
            doc_c.nome_arquivo_original = nome_salvo
            doc_c.caminho_arquivo = caminho_salvo
            doc_c.tamanho_bytes = tamanho_bytes
            doc_c.status_processamento_ia = "SINCRONIZADO_LOTACIONOGRAMA_GERAL"
        
        db.commit()

        # Re-executar verificação TCE-MT para o certame
        engine = AuditEngine(db)
        engine.executar_analise_tce_certame(c.id_certame)

    engine_gen = AuditEngine(db)
    engine_gen.executar_auditoria_completa()

    return RedirectResponse(url=f"/modulo/lotacionograma?msg=Lotacionograma Completo e Oficial do Município importado e processado com sucesso! {qtd_cargos} cargo(s) atualizados e sincronizados com a Passo Inicial de todos os certames.", status_code=303)

@app.post("/modulo/lotacionograma/salvar")
def salvar_lotacionograma_cargo(
    codigo_cargo: str = Form(...),
    nome_cargo: str = Form(...),
    vagas_criadas_lei: int = Form(...),
    lei_criacao: str = Form(...),
    db: Session = Depends(get_db)
):
    cargo = db.query(Cargo).filter_by(codigo_cargo=codigo_cargo).first()
    if not cargo:
        cargo = Cargo(codigo_cargo=codigo_cargo, nome_cargo=nome_cargo, nivel_escolaridade="Superior")
        db.add(cargo)
        db.commit()
        db.refresh(cargo)
    
    lot = db.query(Lotacionograma).filter_by(id_cargo=cargo.id_cargo).first()
    if not lot:
        lot = Lotacionograma(
            id_cargo=cargo.id_cargo,
            lei_criacao=lei_criacao,
            ano_vigencia=2026,
            vagas_criadas_lei=vagas_criadas_lei
        )
        db.add(lot)
    else:
        lot.vagas_criadas_lei = vagas_criadas_lei
        lot.lei_criacao = lei_criacao
    db.commit()

    engine = AuditEngine(db)
    engine.executar_auditoria_completa()

    return RedirectResponse(url="/modulo/lotacionograma?msg=Cargo cadastrado/atualizado com sucesso!", status_code=303)

# --- MÓDULOS DEMAIS DA SIDEBAR ---

@app.get("/modulo/concursos", response_class=HTMLResponse)
def modulo_concursos(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    concursos = db.query(Concurso).all()
    candidatos = db.query(Candidato).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "usuario": usuario,
        "achados": db.query(AuditoriaAchado).all(),
        "total_criticos": 0, "total_graves": 0, "total_cargos": db.query(Cargo).count(),
        "total_documentos": db.query(DocumentoRepositorio).count(),
        "lotacoes": [], "temporarios": []
    })

@app.get("/modulo/temporarios", response_class=HTMLResponse)
def modulo_temporarios(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    temporarios = db.query(ContratoTemporario).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "usuario": usuario,
        "achados": db.query(AuditoriaAchado).filter_by(modulo_origem="CONTRATOS_TEMPORARIOS").all(),
        "total_criticos": 0, "total_graves": 0, "total_cargos": db.query(Cargo).count(),
        "total_documentos": db.query(DocumentoRepositorio).count(),
        "lotacoes": [], "temporarios": temporarios
    })

@app.get("/modulo/afastamentos", response_class=HTMLResponse)
def modulo_afastamentos(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    afastamentos = db.query(Afastamento).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "usuario": usuario,
        "achados": db.query(AuditoriaAchado).all(),
        "total_criticos": 0, "total_graves": 0, "total_cargos": db.query(Cargo).count(),
        "total_documentos": db.query(DocumentoRepositorio).count(),
        "lotacoes": [], "temporarios": []
    })

@app.get("/achados", response_class=HTMLResponse)
def lista_achados(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/normativos", response_class=HTMLResponse)
def normativos(request: Request, usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/certames", status_code=303)

# --- GESTÃO DE ACESSO & USUÁRIOS ---

@app.get("/usuarios", response_class=HTMLResponse)
def gestao_usuarios(
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
    
    usuarios_list = db.query(Usuario).order_by(Usuario.id_usuario.asc()).all()
    
    total_usuarios = len(usuarios_list)
    total_admins = sum(1 for u in usuarios_list if u.perfil == "ADMIN_MASTER")
    total_auditores = sum(1 for u in usuarios_list if u.perfil == "AUDITOR_CONTROLE_INTERNO")
    total_consultores = total_usuarios - total_admins - total_auditores
    
    msg = request.query_params.get("msg")
    erro = request.query_params.get("erro")
    
    return templates.TemplateResponse("gestao_usuarios.html", {
        "request": request,
        "usuario": usuario,
        "usuarios": usuarios_list,
        "total_usuarios": total_usuarios,
        "total_admins": total_admins,
        "total_auditores": total_auditores,
        "total_consultores": total_consultores,
        "msg": msg,
        "erro": erro,
        "active_page": "usuarios"
    })

@app.post("/usuarios/criar")
def usuarios_criar(
    nome: str = Form(...),
    email: str = Form(...),
    email_recuperacao: Optional[str] = Form(None),
    perfil: str = Form("AUDITOR_CONTROLE_INTERNO"),
    senha: str = Form(...),
    confirmar_senha: str = Form(...),
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
    
    email_clean = email.strip().lower()
    email_recup_clean = email_recuperacao.strip().lower() if email_recuperacao and email_recuperacao.strip() else email_clean
    nome_clean = nome.strip()
    
    if len(senha) < 6:
        return RedirectResponse(url="/usuarios?erro=A senha deve conter no mínimo 6 caracteres.", status_code=303)
    
    if senha != confirmar_senha:
        return RedirectResponse(url="/usuarios?erro=As senhas digitadas não coincidem.", status_code=303)
        
    existente = db.query(Usuario).filter_by(email=email_clean).first()
    if existente:
        return RedirectResponse(url=f"/usuarios?erro=O e-mail {email_clean} já está cadastrado no sistema.", status_code=303)
        
    novo_user = Usuario(
        nome=nome_clean,
        email=email_clean,
        email_recuperacao=email_recup_clean,
        senha_hash=hash_senha(senha),
        perfil=perfil,
        primeiro_acesso=False,
        data_criacao=datetime.now()
    )
    db.add(novo_user)
    db.commit()
    
    return RedirectResponse(url=f"/usuarios?msg=Usuário {nome_clean} cadastrado com sucesso!", status_code=303)

@app.post("/usuarios/{id_usuario}/editar")
def usuarios_editar(
    id_usuario: int,
    nome: str = Form(...),
    perfil: str = Form(...),
    email_recuperacao: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
        
    user_target = db.query(Usuario).filter_by(id_usuario=id_usuario).first()
    if not user_target:
        return RedirectResponse(url="/usuarios?erro=Usuário não localizado.", status_code=303)
        
    user_target.nome = nome.strip()
    user_target.perfil = perfil
    if email_recuperacao and email_recuperacao.strip():
        user_target.email_recuperacao = email_recuperacao.strip().lower()
    else:
        user_target.email_recuperacao = user_target.email
    db.commit()
    
    return RedirectResponse(url="/usuarios?msg=Dados do operador atualizados com sucesso!", status_code=303)

@app.post("/usuarios/{id_usuario}/redefinir-senha")
def usuarios_redefinir_senha(
    id_usuario: int,
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
        
    user_target = db.query(Usuario).filter_by(id_usuario=id_usuario).first()
    if not user_target:
        return RedirectResponse(url="/usuarios?erro=Usuário não localizado.", status_code=303)
        
    if len(nova_senha) < 6:
        return RedirectResponse(url="/usuarios?erro=A nova senha deve conter no mínimo 6 caracteres.", status_code=303)
        
    if nova_senha != confirmar_senha:
        return RedirectResponse(url="/usuarios?erro=A confirmação de senha não confere.", status_code=303)
        
    user_target.senha_hash = hash_senha(nova_senha)
    db.commit()
    
    return RedirectResponse(url=f"/usuarios?msg=Senha do usuário {user_target.nome} redefinida com sucesso!", status_code=303)

@app.post("/usuarios/{id_usuario}/excluir")
def usuarios_excluir(
    id_usuario: int,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
        
    if usuario.id_usuario == id_usuario:
        return RedirectResponse(url="/usuarios?erro=Não é permitido excluir o seu próprio usuário ativo.", status_code=303)
        
    user_target = db.query(Usuario).filter_by(id_usuario=id_usuario).first()
    if not user_target:
        return RedirectResponse(url="/usuarios?erro=Usuário não localizado.", status_code=303)
        
    db.delete(user_target)
    db.commit()
    
    return RedirectResponse(url=f"/usuarios?msg=Usuário {user_target.nome} removido do sistema.", status_code=303)

# --- TROCA DE SENHA DO USUÁRIO LOGADO ---

@app.get("/perfil/trocar-senha", response_class=HTMLResponse)
def perfil_trocar_senha_tela(
    request: Request,
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
        
    msg = request.query_params.get("msg")
    erro = request.query_params.get("erro")
    
    return templates.TemplateResponse("trocar_senha.html", {
        "request": request,
        "usuario": usuario,
        "msg": msg,
        "erro": erro
    })

@app.post("/perfil/trocar-senha")
def perfil_trocar_senha_executar(
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    confirmar_nova_senha: str = Form(...),
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario:
        return RedirectResponse(url="/login", status_code=303)
        
    # Validar senha atual
    if usuario.senha_hash != hash_senha(senha_atual):
        return RedirectResponse(url="/perfil/trocar-senha?erro=A senha atual digitada está incorreta.", status_code=303)
        
    if len(nova_senha) < 6:
        return RedirectResponse(url="/perfil/trocar-senha?erro=A nova senha deve ter no mínimo 6 caracteres.", status_code=303)
        
    if nova_senha != confirmar_nova_senha:
        return RedirectResponse(url="/perfil/trocar-senha?erro=A nova senha e a confirmação não coincidem.", status_code=303)
        
    # Atualizar hash
    usuario_db = db.query(Usuario).filter_by(id_usuario=usuario.id_usuario).first()
    if usuario_db:
        usuario_db.senha_hash = hash_senha(nova_senha)
        usuario_db.primeiro_acesso = False
        db.commit()
        
    return RedirectResponse(url="/usuarios?msg=Sua senha foi alterada com sucesso!", status_code=303)


# --- FLUXO DE ABERTURA DE CERTAMES & PARECER PRÉVIO TCE-MT ---

@app.get("/certames", response_class=HTMLResponse)
def certames_lista(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certames = db.query(CertameAbertura).order_by(CertameAbertura.data_abertura_processo.desc()).all()
    return templates.TemplateResponse("certames_lista.html", {
        "request": request,
        "usuario": usuario,
        "certames": certames
    })

@app.get("/certames/novo", response_class=HTMLResponse)
def certames_novo(request: Request, usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("modalidade_selecao.html", {
        "request": request,
        "usuario": usuario
    })

@app.post("/certames/criar")
def certames_criar(
    modalidade: str = Form(...),
    numero_certame: str = Form(...),
    municipio: str = Form(...),
    orgao_solicitante: str = Form(...),
    prefeito_ordenador: str = Form(...),
    secretario_solicitante: str = Form(...),
    contador_responsavel: str = Form(...),
    banca_examinadora: str = Form(...),
    lei_autorizadora: str = Form(...),
    leis_carreira: str = Form(...),
    db: Session = Depends(get_db)
):
    certame = CertameAbertura(
        modalidade=modalidade,
        numero_certame=numero_certame,
        ano=2024,
        municipio=municipio,
        orgao_solicitante=orgao_solicitante,
        prefeito_ordenador=prefeito_ordenador,
        secretario_solicitante=secretario_solicitante,
        contador_responsavel=contador_responsavel,
        banca_examinadora=banca_examinadora,
        lei_autorizadora=lei_autorizadora,
        leis_carreira=leis_carreira
    )
    db.add(certame)
    db.commit()
    db.refresh(certame)

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(certame.id_certame)

    return RedirectResponse(url=f"/certames/{certame.id_certame}/documentos", status_code=303)

@app.get("/certames/{id_certame}/editar", response_class=HTMLResponse)
def certames_editar(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    return templates.TemplateResponse("certame_editar.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame
    })

@app.post("/certames/{id_certame}/atualizar")
def certames_atualizar(
    id_certame: int,
    modalidade: str = Form(...),
    numero_certame: str = Form(...),
    municipio: str = Form(...),
    orgao_solicitante: str = Form(...),
    prefeito_ordenador: str = Form(...),
    secretario_solicitante: str = Form(...),
    contador_responsavel: str = Form(...),
    banca_examinadora: str = Form(...),
    lei_autorizadora: str = Form(...),
    leis_carreira: str = Form(...),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    certame.modalidade = modalidade
    certame.numero_certame = numero_certame.strip()
    certame.municipio = municipio.strip()
    certame.orgao_solicitante = orgao_solicitante.strip()
    certame.prefeito_ordenador = prefeito_ordenador.strip()
    certame.secretario_solicitante = secretario_solicitante.strip()
    certame.contador_responsavel = contador_responsavel.strip()
    certame.banca_examinadora = banca_examinadora.strip()
    certame.lei_autorizadora = lei_autorizadora.strip()
    certame.leis_carreira = leis_carreira.strip()

    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    return RedirectResponse(url=f"/certames/{id_certame}/wizard?msg=Dados do certame atualizados com sucesso!", status_code=303)

@app.post("/certames/excluir/{id_certame}")
@app.get("/certames/excluir/{id_certame}")
def excluir_certame(id_certame: int, db: Session = Depends(get_db)):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if certame:
        for anexo in certame.anexos:
            if anexo.caminho_arquivo and os.path.exists(anexo.caminho_arquivo):
                try: os.remove(anexo.caminho_arquivo)
                except Exception: pass

        db.query(CertameAnaliseTCE).filter_by(id_certame=id_certame).delete()
        db.query(ParecerTecnico).filter_by(id_certame=id_certame).delete()
        db.query(CertameAnexo).filter_by(id_certame=id_certame).delete()
        db.query(AuditoriaAchado).filter(AuditoriaAchado.id_referencia == id_certame).delete()
        db.delete(certame)
        db.commit()

        engine = AuditEngine(db)
        engine.executar_auditoria_completa()

    return RedirectResponse(url="/certames?msg=Certame excluído e dados zerados com sucesso!", status_code=303)


@app.get("/certames/{id_certame}/wizard", response_class=HTMLResponse)
def certames_wizard(id_certame: int, request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    # Verificar se o certame já possui o Lotacionograma anexado. Se não possuir, mas existir um Lotacionograma Oficial Geral no sistema, sincronizar automaticamente!
    anexo_lot_certame = db.query(CertameAnexo).filter_by(id_certame=id_certame, tipo_documento="LOTACIONOGRAMA").first()
    if not anexo_lot_certame:
        doc_geral = db.query(DocumentoRepositorio).filter_by(tipo_documento="LOTACIONOGRAMA").order_by(DocumentoRepositorio.data_upload.desc()).first()
        if not doc_geral:
            doc_geral = db.query(CertameAnexo).filter_by(tipo_documento="LOTACIONOGRAMA").order_by(CertameAnexo.data_upload.desc()).first()
        
        if doc_geral and doc_geral.caminho_arquivo:
            anexo_lot_certame = CertameAnexo(
                id_certame=id_certame,
                tipo_documento="LOTACIONOGRAMA",
                nome_arquivo=getattr(doc_geral, "nome_arquivo_original", None) or getattr(doc_geral, "nome_arquivo", "Lotacionograma_Oficial_Municipio.pdf"),
                caminho_arquivo=doc_geral.caminho_arquivo,
                conteudo_texto=getattr(doc_geral, "conteudo_texto", "") or "Lotacionograma Completo e Oficial do Município."
            )
            db.add(anexo_lot_certame)
            db.commit()
            engine_w = AuditEngine(db)
            engine_w.executar_analise_tce_certame(id_certame)

    anexos_cadastrados = [a.tipo_documento for a in certame.anexos]

    return templates.TemplateResponse("certame_wizard.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "anexos_cadastrados": anexos_cadastrados,
        "mensagem": msg
    })

@app.post("/certames/{id_certame}/passo-anexar")
async def certames_passo_anexar(
    id_certame: int,
    passo_tipo: str = Form(...),
    outro_tipo_nome: str = Form(None),
    arquivo: UploadFile = File(None),
    conteudo_texto: str = Form(""),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    tipo_final = outro_tipo_nome.strip() if (outro_tipo_nome and outro_tipo_nome.strip()) else passo_tipo

    texto = conteudo_texto or ""
    caminho = ""
    nome_arquivo = "Inserção Direta de Texto"
    tamanho_bytes = 0

    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    if arquivo and arquivo.filename:
        conteudo_bytes = await arquivo.read()
        tamanho_bytes = len(conteudo_bytes)
        nome_salvo = f"{uuid.uuid4().hex[:6]}_{arquivo.filename}"
        caminho = os.path.join(pasta_certame, nome_salvo)
        with open(caminho, "wb") as f:
            f.write(conteudo_bytes)
        nome_arquivo = arquivo.filename

        if arquivo.filename.lower().endswith(".pdf"):
            texto_pdf = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
            if texto_pdf:
                texto = texto_pdf
        else:
            texto_decoded = conteudo_bytes.decode("utf-8", errors="ignore")
            if texto_decoded:
                texto = texto_decoded
    elif texto and texto.strip():
        res_pdf = PDFTextGenerator.gerar_pdf_de_texto(
            id_certame=id_certame,
            numero_certame=certame.numero_certame,
            tipo_documento=tipo_final,
            conteudo_texto=texto,
            pasta_upload=pasta_certame
        )
        caminho = res_pdf["caminho_arquivo"]
        nome_arquivo = res_pdf["nome_arquivo"]
        tamanho_bytes = res_pdf["tamanho_bytes"]

    anexo = db.query(CertameAnexo).filter_by(id_certame=id_certame, tipo_documento=tipo_final).first()
    if not anexo:
        anexo = CertameAnexo(
            id_certame=id_certame,
            tipo_documento=tipo_final,
            nome_arquivo=nome_arquivo,
            caminho_arquivo=caminho,
            conteudo_texto=texto
        )
        db.add(anexo)
    else:
        anexo.nome_arquivo = nome_arquivo
        anexo.caminho_arquivo = caminho
        anexo.conteudo_texto = texto

    doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame, tipo_documento=tipo_final).first()
    if not doc_repo:
        doc_repo = DocumentoRepositorio(
            id_certame=id_certame,
            nome_arquivo_original=nome_arquivo,
            caminho_arquivo=caminho if caminho else "TEXTO_DIRETO",
            tipo_documento=tipo_final,
            tamanho_bytes=tamanho_bytes,
            status_processamento_ia="PROCESSADO_COM_SUCESSO",
            resumo_extracao=f"Instruído via Passo a Passo para o Certame #{certame.numero_certame}."
        )
        db.add(doc_repo)
    else:
        doc_repo.nome_arquivo_original = nome_arquivo
        doc_repo.caminho_arquivo = caminho if caminho else "TEXTO_DIRETO"
        doc_repo.tamanho_bytes = tamanho_bytes
    
    db.commit()

    # Se for o Passo Inicial LOTACIONOGRAMA, processar por IA para alimentar o Lotacionograma Completo e Oficial do Município e replicar
    if tipo_final == "LOTACIONOGRAMA" or passo_tipo == "LOTACIONOGRAMA":
        if texto and texto.strip():
            res_ia = DocumentParserAI.process_lotacionograma_text(texto, db)
            
            # Sincronizar documento oficial no Repositório Geral
            doc_oficial = db.query(DocumentoRepositorio).filter_by(tipo_documento="LOTACIONOGRAMA").first()
            if not doc_oficial:
                doc_oficial = DocumentoRepositorio(
                    nome_arquivo_original=nome_arquivo,
                    caminho_arquivo=caminho,
                    tipo_documento="LOTACIONOGRAMA",
                    tamanho_bytes=tamanho_bytes,
                    status_processamento_ia="LOTACIONOGRAMA_OFICIAL_PROCESSADO",
                    resumo_extracao=f"Lotacionograma Completo e Oficial do Município atualizado via Certame #{certame.numero_certame}."
                )
                db.add(doc_oficial)
            else:
                doc_oficial.nome_arquivo_original = nome_arquivo
                doc_oficial.caminho_arquivo = caminho
                doc_oficial.tamanho_bytes = tamanho_bytes
                doc_oficial.status_processamento_ia = "LOTACIONOGRAMA_OFICIAL_PROCESSADO"
                doc_oficial.resumo_extracao = f"Lotacionograma Completo e Oficial do Município atualizado via Certame #{certame.numero_certame}."
            
            # Replicar para os demais certames que não possuírem Lotacionograma ainda
            outros_certames = db.query(CertameAbertura).filter(CertameAbertura.id_certame != id_certame).all()
            for oc in outros_certames:
                anexo_oc = db.query(CertameAnexo).filter_by(id_certame=oc.id_certame, tipo_documento="LOTACIONOGRAMA").first()
                if not anexo_oc:
                    anexo_oc = CertameAnexo(
                        id_certame=oc.id_certame,
                        tipo_documento="LOTACIONOGRAMA",
                        nome_arquivo=nome_arquivo,
                        caminho_arquivo=caminho,
                        conteudo_texto=texto
                    )
                    db.add(anexo_oc)
                    doc_oc = DocumentoRepositorio(
                        id_certame=oc.id_certame,
                        nome_arquivo_original=nome_arquivo,
                        caminho_arquivo=caminho,
                        tipo_documento="LOTACIONOGRAMA",
                        tamanho_bytes=tamanho_bytes,
                        status_processamento_ia="SINCRONIZADO_LOTACIONOGRAMA_GERAL",
                        resumo_extracao=f"Replicado do Lotacionograma Completo do Município."
                    )
                    db.add(doc_oc)
                    db.commit()
                    engine_oc = AuditEngine(db)
                    engine_oc.executar_analise_tce_certame(oc.id_certame)

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    return RedirectResponse(url=f"/certames/{id_certame}/wizard?msg=Documento '{tipo_final}' inserido e processado com sucesso!", status_code=303)


@app.get("/certames/{id_certame}/documentos", response_class=HTMLResponse)
def certames_documentos(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    return templates.TemplateResponse("certame_documentos.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame
    })

@app.post("/certames/{id_certame}/anexar")
async def certames_anexar(
    id_certame: int,
    tipo_documento: str = Form(...),
    outro_tipo_nome: str = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    tipo_final = outro_tipo_nome.strip() if (outro_tipo_nome and outro_tipo_nome.strip()) else tipo_documento

    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    conteudo_bytes = await arquivo.read()
    tamanho_bytes = len(conteudo_bytes)
    nome_salvo = f"{uuid.uuid4().hex[:6]}_{arquivo.filename}"
    caminho = os.path.join(pasta_certame, nome_salvo)
    with open(caminho, "wb") as f:
        f.write(conteudo_bytes)

    if arquivo.filename.lower().endswith(".pdf"):
        texto = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
    else:
        texto = conteudo_bytes.decode("utf-8", errors="ignore")

    anexo = CertameAnexo(
        id_certame=id_certame,
        tipo_documento=tipo_final,
        nome_arquivo=arquivo.filename,
        caminho_arquivo=caminho,
        conteudo_texto=texto
    )
    db.add(anexo)

    doc_repo = DocumentoRepositorio(
        id_certame=id_certame,
        nome_arquivo_original=arquivo.filename,
        caminho_arquivo=caminho,
        tipo_documento=tipo_final,
        tamanho_bytes=tamanho_bytes,
        status_processamento_ia="PROCESSADO_COM_SUCESSO",
        resumo_extracao=f"Anexado no Repositório do Certame #{certame.numero_certame}."
    )
    db.add(doc_repo)
    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    return RedirectResponse(url=f"/certames/{id_certame}/documentos?msg=Documento '{tipo_final}' anexado com sucesso!", status_code=303)

@app.get("/certames/{id_certame}/analise-tce", response_class=HTMLResponse)
def certames_analise_tce(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    analises = db.query(CertameAnaliseTCE).filter_by(id_certame=id_certame).all()

    total_conformes = sum(1 for a in analises if a.status_item == "CONFORME")
    total_ressalvas = sum(1 for a in analises if a.status_item == "RESSALVA")
    total_nao_conformes = sum(1 for a in analises if a.status_item == "NAO_CONFORME")

    return templates.TemplateResponse("certame_analise_tce.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "analises": analises,
        "total_conformes": total_conformes,
        "total_ressalvas": total_ressalvas,
        "total_nao_conformes": total_nao_conformes
    })

@app.get("/certames/{id_certame}/parecer-previo", response_class=HTMLResponse)
def certames_parecer_previo(id_certame: int, request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    parecer = certame.parecer
    if not parecer:
        engine = AuditEngine(db)
        engine.gerar_parecer_previo_rascunho(id_certame)
        db.refresh(certame)
        parecer = certame.parecer

    return templates.TemplateResponse("parecer_previo_editor.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "parecer": parecer,
        "mensagem": msg
    })

@app.post("/certames/{id_certame}/salvar-parecer")
def salvar_parecer(
    id_certame: int,
    acao: str = Form("salvar"),
    numero_parecer: str = Form(...),
    tipo_conclusao: str = Form(...),
    assunto: str = Form(...),
    fundamentacao_legal: str = Form(...),
    documentos_exigidos_texto: str = Form(...),
    justificativa_texto: str = Form(...),
    autorizacao_texto: str = Form(...),
    banca_executora_texto: str = Form(...),
    regulamento_autorizacao_texto: str = Form(...),
    impacto_orcamentario_texto: str = Form(...),
    declaracao_compatibilidade_texto: str = Form(...),
    comissao_organizadora_texto: str = Form(...),
    lotacionograma_texto: str = Form(...),
    edital_normativo_texto: str = Form(...),
    publicacao_ampla_doc_tce_texto: str = Form(None),
    reserva_vagas_pcd_texto: str = Form(None),
    discrepancias_ressalvas_texto: str = Form(...),
    prazos_isencoes_texto: str = Form(...),
    conclusao_parecer_texto: str = Form(...),
    auditor_responsavel: str = Form(...),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    parecer = certame.parecer if certame else None

    if parecer:
        parecer.numero_parecer = numero_parecer
        parecer.tipo_conclusao = tipo_conclusao
        parecer.assunto = assunto
        parecer.fundamentacao_legal = fundamentacao_legal
        parecer.documentos_exigidos_texto = documentos_exigidos_texto
        parecer.justificativa_texto = justificativa_texto
        parecer.autorizacao_texto = autorizacao_texto
        parecer.banca_executora_texto = banca_executora_texto
        parecer.regulamento_autorizacao_texto = regulamento_autorizacao_texto
        parecer.impacto_orcamentario_texto = impacto_orcamentario_texto
        parecer.declaracao_compatibilidade_texto = declaracao_compatibilidade_texto
        parecer.comissao_organizadora_texto = comissao_organizadora_texto
        parecer.lotacionograma_texto = lotacionograma_texto
        parecer.edital_normativo_texto = edital_normativo_texto
        parecer.publicacao_ampla_doc_tce_texto = publicacao_ampla_doc_tce_texto
        parecer.reserva_vagas_pcd_texto = reserva_vagas_pcd_texto
        parecer.discrepancias_ressalvas_texto = discrepancias_ressalvas_texto
        parecer.prazos_isencoes_texto = prazos_isencoes_texto
        parecer.conclusao_parecer_texto = conclusao_parecer_texto
        parecer.auditor_responsavel = auditor_responsavel

        if acao == "emitir_definitivo":
            parecer.status = "DEFINITIVO_EMITIDO"
            certame.status_auditoria = "PARECER_DEFINITIVO_EMITIDO"
            db.commit()

            pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
            res_pdf = PDFTextGenerator.gerar_pdf_parecer_definitivo(certame, parecer, pasta_certame)

            tipo_parecer = "PARECER_DEFINITIVO_CONTROLE_INTERNO"
            
            anexo = db.query(CertameAnexo).filter_by(id_certame=id_certame, tipo_documento=tipo_parecer).first()
            if not anexo:
                anexo = CertameAnexo(
                    id_certame=id_certame,
                    tipo_documento=tipo_parecer,
                    nome_arquivo=res_pdf["nome_arquivo"],
                    caminho_arquivo=res_pdf["caminho_arquivo"],
                    conteudo_texto=parecer.conclusao_parecer_texto or parecer.assunto
                )
                db.add(anexo)
            else:
                anexo.nome_arquivo = res_pdf["nome_arquivo"]
                anexo.caminho_arquivo = res_pdf["caminho_arquivo"]
                anexo.conteudo_texto = parecer.conclusao_parecer_texto or parecer.assunto

            doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame, tipo_documento=tipo_parecer).first()
            if not doc_repo:
                doc_repo = DocumentoRepositorio(
                    id_certame=id_certame,
                    nome_arquivo_original=res_pdf["nome_arquivo"],
                    caminho_arquivo=res_pdf["caminho_arquivo"],
                    tipo_documento=tipo_parecer,
                    tamanho_bytes=res_pdf["tamanho_bytes"],
                    status_processamento_ia="DEFINITIVO_EMITIDO",
                    resumo_extracao=f"Parecer Definitivo do Controle Interno ({parecer.numero_parecer}) emitido para o Certame #{certame.numero_certame}."
                )
                db.add(doc_repo)
            else:
                doc_repo.nome_arquivo_original = res_pdf["nome_arquivo"]
                doc_repo.caminho_arquivo = res_pdf["caminho_arquivo"]
                doc_repo.tamanho_bytes = res_pdf["tamanho_bytes"]
                doc_repo.status_processamento_ia = "DEFINITIVO_EMITIDO"

            db.commit()
            return RedirectResponse(url=f"/certames/{id_certame}/parecer-definitivo", status_code=303)
        else:
            db.commit()
            return RedirectResponse(url=f"/certames/{id_certame}/parecer-previo?msg=Rascunho do Parecer salvo com sucesso!", status_code=303)

    return RedirectResponse(url="/certames", status_code=303)

@app.get("/certames/{id_certame}/parecer-definitivo", response_class=HTMLResponse)
def certames_parecer_definitivo(id_certame: int, request: Request, db: Session = Depends(get_db)):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame or not certame.parecer:
        return RedirectResponse(url="/certames", status_code=303)

    return templates.TemplateResponse("parecer_definitivo.html", {
        "request": request,
        "certame": certame,
        "parecer": certame.parecer
    })

# --- ROTAS DA FASE OFICIAL DO CERTAME (PÓS-EDITAL & EXECUÇÃO) ---

@app.get("/certames/{id_certame}/fase-oficial", response_class=HTMLResponse)
def certames_fase_oficial(id_certame: int, request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    fase_oficial = certame.fase_oficial
    if not fase_oficial:
        fase_oficial = CertameFaseOficial(id_certame=id_certame)
        db.add(fase_oficial)
        db.commit()
        db.refresh(fase_oficial)

    anexos_cadastrados = [a.tipo_documento for a in certame.anexos] if certame.anexos else []

    return templates.TemplateResponse("fase_oficial.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "fase_oficial": fase_oficial,
        "anexos_cadastrados": anexos_cadastrados,
        "mensagem": msg
    })

@app.post("/certames/{id_certame}/fase-oficial/anexar")
async def anexar_fase_oficial(
    id_certame: int,
    tipo_documento: str = Form(...),
    arquivo: UploadFile = File(None),
    arquivos: List[UploadFile] = File(None),
    conteudo_texto: str = Form(""),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    fase_oficial = certame.fase_oficial
    if not fase_oficial:
        fase_oficial = CertameFaseOficial(id_certame=id_certame)
        db.add(fase_oficial)
        db.commit()
        db.refresh(fase_oficial)

    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    lista_uploads: List[UploadFile] = []
    if arquivos:
        for f in arquivos:
            if f and f.filename:
                lista_uploads.append(f)
    if arquivo and arquivo.filename and arquivo not in lista_uploads:
        lista_uploads.append(arquivo)

    if not lista_uploads and not (conteudo_texto and conteudo_texto.strip()):
        return RedirectResponse(url=f"/certames/{id_certame}/fase-oficial?msg=Erro: Forneça pelo menos um arquivo ou cole o texto do documento.", status_code=303)

    processados = 0

    if lista_uploads:
        for item_arq in lista_uploads:
            conteudo_bytes = await item_arq.read()
            tamanho_bytes = len(conteudo_bytes)
            nome_salvo = item_arq.filename
            nome_disco = f"{uuid.uuid4().hex[:6]}_{item_arq.filename}"
            caminho_salvo = os.path.join(pasta_certame, nome_disco)
            with open(caminho_salvo, "wb") as f:
                f.write(conteudo_bytes)

            if item_arq.filename.lower().endswith(".pdf"):
                try:
                    texto_extraido = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
                except Exception:
                    texto_extraido = ""
            else:
                try:
                    texto_extraido = conteudo_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    texto_extraido = ""

            if conteudo_texto and conteudo_texto.strip():
                texto_extraido += "\n\n" + conteudo_texto.strip()

            # Processar IA na Fase Oficial
            try:
                DocumentParserAI.process_fase_oficial_text(texto_extraido, tipo_documento, fase_oficial, db=db)
            except Exception as e:
                import logging
                logging.getLogger("uvicorn").error(f"Erro ao processar IA na fase oficial: {e}", exc_info=True)

            # Salvar anexo
            anexo = CertameAnexo(
                id_certame=id_certame,
                tipo_documento=tipo_documento,
                nome_arquivo=nome_salvo,
                caminho_arquivo=caminho_salvo,
                conteudo_texto=texto_extraido[:1000] if texto_extraido else f"Documento {tipo_documento}"
            )
            db.add(anexo)

            # Salvar no repositório geral
            doc_repo = DocumentoRepositorio(
                id_certame=id_certame,
                nome_arquivo_original=nome_salvo,
                caminho_arquivo=caminho_salvo,
                tipo_documento=tipo_documento,
                tamanho_bytes=tamanho_bytes,
                status_processamento_ia="FASE_OFICIAL_PROCESSADO_IA",
                resumo_extracao=f"Anexado e processado pela IA na Fase Oficial do Certame #{certame.numero_certame}."
            )
            db.add(doc_repo)
            processados += 1
    else:
        # Apenas texto colado
        texto_extraido = conteudo_texto.strip()
        res_pdf = PDFTextGenerator.gerar_pdf_de_texto(
            id_certame=id_certame,
            numero_certame=certame.numero_certame,
            tipo_documento=tipo_documento,
            conteudo_texto=texto_extraido,
            pasta_upload=pasta_certame
        )
        nome_salvo = res_pdf["nome_arquivo"]
        caminho_salvo = res_pdf["caminho_arquivo"]
        tamanho_bytes = res_pdf["tamanho_bytes"]

        try:
            DocumentParserAI.process_fase_oficial_text(texto_extraido, tipo_documento, fase_oficial, db=db)
        except Exception as e:
            import logging
            logging.getLogger("uvicorn").error(f"Erro ao processar IA na fase oficial: {e}", exc_info=True)

        anexo = CertameAnexo(
            id_certame=id_certame,
            tipo_documento=tipo_documento,
            nome_arquivo=nome_salvo,
            caminho_arquivo=caminho_salvo,
            conteudo_texto=texto_extraido
        )
        db.add(anexo)

        doc_repo = DocumentoRepositorio(
            id_certame=id_certame,
            nome_arquivo_original=nome_salvo,
            caminho_arquivo=caminho_salvo,
            tipo_documento=tipo_documento,
            tamanho_bytes=tamanho_bytes,
            status_processamento_ia="FASE_OFICIAL_PROCESSADO_IA",
            resumo_extracao=f"Texto transcrito processado pela IA na Fase Oficial do Certame #{certame.numero_certame}."
        )
        db.add(doc_repo)
        processados += 1

    db.commit()

    # Se for homologação do resultado final, dispara a importação automática para o Módulo de Acompanhamento
    if tipo_documento in ["HOMOLOGACAO_RESULTADO_FINAL", "PUBLICACAO_HOMOLOGACAO_RESULTADO_FINAL", "HOMOLOGACAO_RESULTADO"]:
        engine = AuditEngine(db)
        engine.importar_dados_fase_oficial_para_acompanhamento(id_certame)
        return RedirectResponse(url=f"/certames/{id_certame}/acompanhamento?msg=Homologação registrada! {processados} arquivo(s) importado(s) e candidatos extraídos com sucesso.", status_code=303)

    return RedirectResponse(url=f"/certames/{id_certame}/fase-oficial?msg={processados} documento(s) oficial(is) '{tipo_documento.replace('_', ' ')}' anexado(s) e processado(s) pela IA com sucesso!", status_code=303)


@app.post("/certames/{id_certame}/fase-oficial/finalizar-e-importar")
def finalizar_fase_oficial_e_importar(id_certame: int, db: Session = Depends(get_db)):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    engine.importar_dados_fase_oficial_para_acompanhamento(id_certame)

    return RedirectResponse(
        url=f"/certames/{id_certame}/acompanhamento?msg=Fase Oficial finalizada com sucesso! Informações importadas para o Módulo de Acompanhamento e vinculadas ao Lotacionograma Oficial do Município.",
        status_code=303
    )


# --- ROTAS DE EMISSÃO E GESTÃO DO PARECER TÉCNICO DA FASE OFICIAL ---

@app.get("/certames/{id_certame}/fase-oficial/parecer", response_class=HTMLResponse)
def certames_parecer_fase_oficial(id_certame: int, request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    parecer_oficial = certame.parecer_oficial
    if not parecer_oficial:
        engine = AuditEngine(db)
        parecer_oficial = engine.gerar_parecer_fase_oficial_rascunho(id_certame)

    return templates.TemplateResponse("parecer_fase_oficial_editor.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "parecer": parecer_oficial,
        "mensagem": msg
    })

@app.post("/certames/{id_certame}/fase-oficial/gerar-relatorio-ia")
@app.get("/certames/{id_certame}/fase-oficial/gerar-relatorio-ia")
def gerar_relatorio_ia_fase_oficial(id_certame: int, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    engine.gerar_relatorio_ia_completo(id_certame)

    return RedirectResponse(
        url=f"/certames/{id_certame}/fase-oficial/parecer?msg=Relatório completo gerado com sucesso via Inteligência Artificial, integrando dados do Dashboard de Acompanhamento!",
        status_code=303
    )

@app.post("/certames/{id_certame}/fase-oficial/salvar-parecer")
def salvar_parecer_fase_oficial(
    id_certame: int,
    acao: str = Form("salvar"),
    numero_parecer: str = Form(...),
    objeto_analise: str = Form(...),
    interessado_orgao: str = Form(...),
    fundamentacao_legal: str = Form(...),
    relatorio_historico: str = Form(...),
    analise_tecnica_juridica: str = Form(...),
    conclusao_tipo: str = Form(...),
    justificativa_conclusao: str = Form(...),
    auditor_responsavel: str = Form(...),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    parecer_oficial = certame.parecer_oficial
    if not parecer_oficial:
        parecer_oficial = ParecerOficial(id_certame=id_certame)
        db.add(parecer_oficial)

    parecer_oficial.numero_parecer = numero_parecer
    parecer_oficial.objeto_analise = objeto_analise
    parecer_oficial.interessado_orgao = interessado_orgao
    parecer_oficial.fundamentacao_legal = fundamentacao_legal
    parecer_oficial.relatorio_historico = relatorio_historico
    parecer_oficial.analise_tecnica_juridica = analise_tecnica_juridica
    parecer_oficial.conclusao_tipo = conclusao_tipo
    parecer_oficial.justificativa_conclusao = justificativa_conclusao
    parecer_oficial.auditor_responsavel = auditor_responsavel

    if acao == "emitir_definitivo":
        parecer_oficial.status = "DEFINITIVO_EMITIDO"
        if certame.fase_oficial:
            certame.fase_oficial.status_fase_oficial = "HOMOLOGADO_FINAL"
        db.commit()

        # Dispara a importação automática das informações para o Módulo de Acompanhamento (Lotacionograma)
        engine = AuditEngine(db)
        engine.importar_dados_fase_oficial_para_acompanhamento(id_certame)

        pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
        res_pdf = PDFTextGenerator.gerar_pdf_parecer_fase_oficial(certame, parecer_oficial, pasta_certame)

        tipo_parecer = "PARECER_DEFINITIVO_FASE_OFICIAL"
        
        anexo = db.query(CertameAnexo).filter_by(id_certame=id_certame, tipo_documento=tipo_parecer).first()
        if not anexo:
            anexo = CertameAnexo(
                id_certame=id_certame,
                tipo_documento=tipo_parecer,
                nome_arquivo=res_pdf["nome_arquivo"],
                caminho_arquivo=res_pdf["caminho_arquivo"],
                conteudo_texto=parecer_oficial.justificativa_conclusao or parecer_oficial.objeto_analise
            )
            db.add(anexo)
        else:
            anexo.nome_arquivo = res_pdf["nome_arquivo"]
            anexo.caminho_arquivo = res_pdf["caminho_arquivo"]
            anexo.conteudo_texto = parecer_oficial.justificativa_conclusao or parecer_oficial.objeto_analise

        doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame, tipo_documento=tipo_parecer).first()
        if not doc_repo:
            doc_repo = DocumentoRepositorio(
                id_certame=id_certame,
                nome_arquivo_original=res_pdf["nome_arquivo"],
                caminho_arquivo=res_pdf["caminho_arquivo"],
                tipo_documento=tipo_parecer,
                tamanho_bytes=res_pdf["tamanho_bytes"],
                status_processamento_ia="DEFINITIVO_FASE_OFICIAL_EMITIDO",
                resumo_extracao=f"Parecer Técnico de Conformidade e Legalidade da Fase Oficial ({parecer_oficial.numero_parecer}) emitido para o Certame #{certame.numero_certame}."
            )
            db.add(doc_repo)
        else:
            doc_repo.nome_arquivo_original = res_pdf["nome_arquivo"]
            doc_repo.caminho_arquivo = res_pdf["caminho_arquivo"]
            doc_repo.tamanho_bytes = res_pdf["tamanho_bytes"]
            doc_repo.status_processamento_ia = "DEFINITIVO_FASE_OFICIAL_EMITIDO"

        db.commit()
        return RedirectResponse(url=f"/certames/{id_certame}/fase-oficial/parecer-definitivo", status_code=303)
    else:
        db.commit()
        return RedirectResponse(url=f"/certames/{id_certame}/fase-oficial/parecer?msg=Rascunho do Parecer da Fase Oficial salvo com sucesso!", status_code=303)

@app.get("/certames/{id_certame}/fase-oficial/parecer-definitivo", response_class=HTMLResponse)
def certames_parecer_fase_oficial_definitivo(id_certame: int, request: Request, db: Session = Depends(get_db)):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame or not certame.parecer_oficial:
        return RedirectResponse(url=f"/certames/{id_certame}/fase-oficial", status_code=303)

    return templates.TemplateResponse("parecer_fase_oficial_definitivo.html", {
        "request": request,
        "certame": certame,
        "parecer": certame.parecer_oficial
    })


# --- NOVO MÓDULO: ACOMPANHAMENTO DO CERTAME (GESTAO DE PROVIMENTOS & POS-HOMOLOGAÇÃO) ---

@app.get("/certames/{id_certame}/acompanhamento", response_class=HTMLResponse)
def certames_acompanhamento(id_certame: int, request: Request, msg: str = None, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    concurso = engine.obter_ou_criar_dados_acompanhamento(id_certame)
    matriz_cargos = engine.consolidar_matriz_cargo_acompanhamento(id_certame)
    alertas_controle = engine.gerar_alertas_controle_interno_acompanhamento(id_certame)

    candidatos = db.query(Candidato).filter_by(id_certame=id_certame).order_by(Candidato.id_cargo, Candidato.classificacao_efetiva).all()
    atos_registrados = db.query(CertameAcompanhamentoAto).filter_by(id_certame=id_certame).order_by(CertameAcompanhamentoAto.data_registro.desc()).all()

    for cand in candidatos:
        conv = cand.convocacoes[0] if cand.convocacoes else None
        mov_posse = next((m for m in cand.movimentacoes if m.tipo_evento == "TERMO_POSSE"), None)
        mov_desist = next((m for m in cand.movimentacoes if m.tipo_evento == "TERMO_DESISTENCIA"), None)
        mov_exon = next((m for m in cand.movimentacoes if m.tipo_evento == "EXONERACAO"), None)
        mov = cand.movimentacoes[0] if cand.movimentacoes else None

        # 1. Edital de Convocação
        cand.edital_convocacao = conv.numero_portaria if conv else "—"
        cand.edital_convocacao_val = conv.numero_portaria if (conv and conv.numero_portaria and conv.numero_portaria != "—") else ""

        # 2. Data da Posse (Apenas se o candidato for EMPOSSADO ou tiver Termo de Posse)
        dt_p = mov_posse.data_registro.date() if (mov_posse and mov_posse.data_registro) else None
        if "EMPOSSADO" in (cand.status_atual or "").upper():
            if not dt_p and conv and conv.compareceu and conv.data_publicacao_doe:
                dt_p = conv.data_publicacao_doe
            cand.data_posse_fmt = dt_p.strftime("%d/%m/%Y") if dt_p else "—"
            cand.data_posse_val = dt_p.strftime("%Y-%m-%d") if dt_p else ""
        else:
            cand.data_posse_fmt = "—"
            cand.data_posse_val = ""

        # 3. Data Exoneração / Desistência
        dt_e = mov_exon.data_registro.date() if (mov_exon and mov_exon.data_registro) else None
        if any(k in cand.status_atual for k in ["EXCLUÍDO", "EXONERADO"]) or dt_e:
            cand.data_exoneracao_fmt = dt_e.strftime("%d/%m/%Y") if dt_e else "—"
            cand.data_exoneracao_val = dt_e.strftime("%Y-%m-%d") if dt_e else ""
        else:
            cand.data_exoneracao_fmt = "—"
            cand.data_exoneracao_val = ""

        # 4. Edital Homologação Desistência / Fim de Fila
        ed_d = mov_desist.numero_processo_sei if (mov_desist and mov_desist.numero_processo_sei) else ""
        if any(k in cand.status_atual for k in ["DESISTENTE", "RENÚNCIA", "FINAL DA FILA"]) or ed_d:
            cand.edital_desistencia_fmt = ed_d if (ed_d and ed_d != "LEITURA_IA_AUTOMATICA") else "Ato Registrado"
            cand.edital_desistencia_val = ed_d if ed_d != "LEITURA_IA_AUTOMATICA" else ""
        else:
            cand.edital_desistencia_fmt = "—"
            cand.edital_desistencia_val = ""

        # 5. Posse Sub Júdice
        if "SUB JÚDICE" in cand.status_atual:
            cand.sub_judice_fmt = "SIM"
            cand.is_sub_judice = True
            cand.is_sub_judice_val = "SIM"
        else:
            cand.sub_judice_fmt = "NÃO"
            cand.is_sub_judice = False
            cand.is_sub_judice_val = "NÃO"

    cnt_total = len(candidatos)
    cnt_exonerados = sum(1 for c in candidatos if any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO", "EXCLUIDO"]))
    cnt_desistentes = sum(1 for c in candidatos if any(k in (c.status_atual or "").upper() for k in ["DESISTENTE", "RENÚNCIA", "RENUNCIA"]) and not any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO", "EXCLUIDO"]))
    cnt_empossados = sum(1 for c in candidatos if "EMPOSSADO" in (c.status_atual or "").upper() and not any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO", "EXCLUIDO", "DESISTENTE", "RENÚNCIA"]))
    cnt_convocados = sum(1 for c in candidatos if (c.status_atual or "").upper() == "CONVOCADO")
    cnt_cr = sum(1 for c in candidatos if "CADASTRO RESERVA" in (c.status_atual or "").upper())
    cnt_aprovados = sum(1 for c in candidatos if "APROVADO" in (c.status_atual or "").upper() and "CADASTRO" not in (c.status_atual or "").upper())
    cnt_cr_total = cnt_cr + cnt_aprovados

    tot_ref = cnt_total if cnt_total > 0 else 1
    pct_empossados = round((cnt_empossados / tot_ref) * 100, 1)
    pct_convocados = round((cnt_convocados / tot_ref) * 100, 1)
    pct_desistentes = round((cnt_desistentes / tot_ref) * 100, 1)
    pct_exonerados = round((cnt_exonerados / tot_ref) * 100, 1)
    pct_cr = round((cnt_cr_total / tot_ref) * 100, 1)

    summary_parts = []
    if pct_empossados > 0:
        summary_parts.append(f"{pct_empossados}% empossados")
    if pct_convocados > 0:
        summary_parts.append(f"{pct_convocados}% convocados")
    if pct_desistentes > 0:
        summary_parts.append(f"{pct_desistentes}% desistentes")
    if pct_exonerados > 0:
        summary_parts.append(f"{pct_exonerados}% exonerados")
    if pct_cr > 0:
        summary_parts.append(f"{pct_cr}% cadastro reserva")

    kpis = {
        "total": cnt_total,
        "empossados": cnt_empossados,
        "convocados": cnt_convocados,
        "desistentes": cnt_desistentes,
        "exonerados": cnt_exonerados,
        "cr": cnt_cr_total,
        "aprovados": cnt_aprovados,
        "pct_empossados": pct_empossados,
        "pct_convocados": pct_convocados,
        "pct_desistentes": pct_desistentes,
        "pct_exonerados": pct_exonerados,
        "pct_cr": pct_cr,
        "summary": " · ".join(summary_parts) if summary_parts else "100% atualizado"
    }

    return templates.TemplateResponse("certame_acompanhamento.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "concurso": concurso,
        "candidatos": candidatos,
        "matriz_cargos": matriz_cargos,
        "alertas_controle": alertas_controle,
        "atos_registrados": atos_registrados,
        "kpis": kpis,
        "mensagem": msg
    })

@app.post("/certames/{id_certame}/acompanhamento/processar-ato")
async def processar_ato_acompanhamento(
    id_certame: int,
    numero_ato: str = Form(None),
    tipo_ato: str = Form(None),
    id_candidato: int = Form(None),
    novo_status: str = Form(None),
    data_ato: str = Form(None),
    observacao: str = Form(""),
    arquivo: UploadFile = File(None),
    arquivos: List[UploadFile] = File(None),
    conteudo_texto: str = Form(""),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    if not numero_ato or not numero_ato.strip():
        numero_ato = f"ATO_IA_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not tipo_ato or not tipo_ato.strip():
        tipo_ato = "PORTARIA_CONVOCACAO"

    engine = AuditEngine(db)
    concurso = engine.obter_ou_criar_dados_acompanhamento(id_certame)

    data_ato_dt = date.today()
    if data_ato:
        try:
            data_ato_dt = datetime.strptime(data_ato, "%Y-%m-%d").date()
        except Exception:
            pass

    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    # Consolida lista de arquivos recebidos (seja por 'arquivo' individual ou 'arquivos' múltiplos)
    lista_uploads: List[UploadFile] = []
    if arquivos:
        for f in arquivos:
            if f and f.filename:
                lista_uploads.append(f)
    if arquivo and arquivo.filename and arquivo not in lista_uploads:
        lista_uploads.append(arquivo)

    total_afetados_ia = 0
    caminhos_salvos = []

    for item_arq in lista_uploads:
        conteudo_bytes = await item_arq.read()
        nome_disco = f"ato_{uuid.uuid4().hex[:6]}_{item_arq.filename}"
        caminho_salvo = os.path.join(pasta_certame, nome_disco)
        with open(caminho_salvo, "wb") as f:
            f.write(conteudo_bytes)
        caminhos_salvos.append(caminho_salvo)

        # Leitura e parsing por IA
        text_ext = ""
        if item_arq.filename.lower().endswith(".pdf"):
            try:
                text_ext = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
            except Exception:
                pass
        else:
            try:
                text_ext = conteudo_bytes.decode("utf-8", errors="ignore")
            except Exception:
                pass

        if conteudo_texto:
            text_ext += "\n" + conteudo_texto

        if text_ext:
            # Auto-detecção de formato e conteúdo do documento
            is_csv_tabular = any(sep in text_ext[:1000] for sep in [",", ";", "\t", "|"]) and ("inscric" in text_ext.lower() or "cargo" in text_ext.lower()) and any(k in text_ext.lower() for k in ["posse", "convoc", "situac", "status", "exoner"])
            res_ia_done = False

            if is_csv_tabular:
                res_csv = DocumentParserAI.process_csv_provimento_tabular(text_ext, db, id_certame)
                if res_csv.get("afetados", 0) > 0:
                    total_afetados_ia += res_csv.get("afetados", 0)
                    res_ia_done = True

            if not res_ia_done:
                text_lower = text_ext.lower()
                is_relatorio_exonerados = (
                    "relação de exonerados" in text_lower or "relacao de exonerados" in text_lower or
                    ("exonerad" in text_lower and any(k in text_lower for k in ["matrícula", "matricula", "término do contrato", "termino do contrato", "valor recebido"]))
                )
                is_relatorio_afastados = (
                    "relação de afastados" in text_lower or "relacao de afastados" in text_lower or
                    ("afastamento" in text_lower and any(k in text_lower for k in ["carência", "carencia", "dias", "auxílio doença", "auxilio doenca"]))
                )

                if is_relatorio_exonerados:
                    res_ex = DocumentParserAI.process_relatorio_exonerados_texto(text_ext, db, id_certame)
                    total_afetados_ia += res_ex.get("afetados", 0)
                elif is_relatorio_afastados:
                    res_af = DocumentParserAI.process_relatorio_afastados_texto(text_ext, db, id_certame)
                    total_afetados_ia += res_af.get("afetados", 0)
                else:
                    is_convoc = (
                        tipo_ato in ["PORTARIA_CONVOCACAO", "CONVOCACAO"] or
                        any(k in text_ext.upper() for k in ["EDITAL DE CONVOCA", "PORTARIA DE CONVOCA", "CONVOCAR O", "CONVOCAR", "CONVOCAÇÃO", "CONVOCACAO"])
                    )
                    if not is_convoc and "HOMOLOGA" in text_ext.upper() and ("APROVADO" in text_ext.upper() or "RESULTADO FINAL" in text_ext.upper()):
                        res_homol = DocumentParserAI.process_homologacao_resultado_final(text_ext, db, id_certame)
                        total_afetados_ia += res_homol.get("candidatos_injetados", 0)
                    else:
                        res_prov = DocumentParserAI.process_ato_provimento_texto(text_ext, db, id_certame, tipo_ato_default=tipo_ato)
                        total_afetados_ia += res_prov.get("afetados", 0)

        # Manter acervo unificado: Adicionar anexo e documento no repositório do certame
        tipo_anx = f"ACOMPANHAMENTO_{tipo_ato}"
        anexo = CertameAnexo(
            id_certame=id_certame,
            tipo_documento=tipo_anx,
            nome_arquivo=item_arq.filename,
            caminho_arquivo=caminho_salvo,
            conteudo_texto=text_ext[:1000] if text_ext else f"Ato {numero_ato}"
        )
        db.add(anexo)

        doc_repo = DocumentoRepositorio(
            id_certame=id_certame,
            nome_arquivo_original=item_arq.filename,
            caminho_arquivo=caminho_salvo,
            tipo_documento=tipo_anx,
            tamanho_bytes=os.path.getsize(caminho_salvo) if os.path.exists(caminho_salvo) else len(conteudo_bytes),
            status_processamento_ia="ACOMPANHAMENTO_PROCESSADO_IA",
            resumo_extracao=f"Ato de Acompanhamento {numero_ato} ({tipo_ato}) processado via IA no certame #{certame.numero_certame}."
        )
        db.add(doc_repo)

    # Se um candidato específico foi selecionado no form manualmente
    cand_afetado = None
    if id_candidato:
        cand_afetado = db.query(Candidato).filter_by(id_candidato=id_candidato).first()
        if cand_afetado and novo_status:
            status_anterior = cand_afetado.status_atual
            cand_afetado.status_atual = novo_status

            if novo_status == "FINAL DA FILA (RECLASSIFICADO)":
                cand_afetado.classificacao_efetiva = cand_afetado.classificacao_original + 10

            mov = MovimentacaoCandidato(
                id_candidato=cand_afetado.id_candidato,
                tipo_evento=tipo_ato,
                numero_processo_sei=numero_ato,
                motivo_justificativa=observacao or f"Status alterado de '{status_anterior}' para '{novo_status}' via {numero_ato}.",
                classificacao_anterior=cand_afetado.classificacao_original,
                classificacao_nova=cand_afetado.classificacao_efetiva
            )
            db.add(mov)

            # Se for convocação, registra Convocacao
            if "CONVOCADO" in novo_status or tipo_ato == "PORTARIA_CONVOCACAO":
                conv = db.query(Convocacao).filter_by(id_candidato=cand_afetado.id_candidato).first()
                if not conv:
                    conv = Convocacao(
                        id_concurso=cand_afetado.id_concurso,
                        id_candidato=cand_afetado.id_candidato,
                        ordem_convocacao_global=cand_afetado.classificacao_original,
                        numero_portaria=numero_ato,
                        data_publicacao_doe=data_ato_dt,
                        prazo_posse_limite=data_ato_dt + timedelta(days=30),
                        compareceu=(novo_status == "EMPOSSADO")
                    )
                    db.add(conv)
                else:
                    conv.numero_portaria = numero_ato
                    conv.data_publicacao_doe = data_ato_dt
                    if novo_status == "EMPOSSADO":
                        conv.compareceu = True

    # Registra o Ato em CertameAcompanhamentoAto
    caminho_primeiro = caminhos_salvos[0] if caminhos_salvos else None
    resumo = f"Ato {numero_ato} ({tipo_ato.replace('_', ' ')}) processado."
    if len(lista_uploads) > 0:
        resumo += f" {len(lista_uploads)} arquivo(s) lido(s) via IA."
    if total_afetados_ia > 0:
        resumo += f" {total_afetados_ia} candidato(s) atualizado(s) automaticamente."
    if cand_afetado:
        resumo += f" Candidato manual: {cand_afetado.nome_completo} -> {cand_afetado.status_atual}."

    ato_reg = CertameAcompanhamentoAto(
        id_certame=id_certame,
        numero_ato=numero_ato,
        tipo_ato=tipo_ato,
        data_ato=data_ato_dt,
        resumo_afetados=resumo,
        caminho_arquivo=caminho_primeiro
    )
    db.add(ato_reg)
    db.commit()

    msg_final = f"Ato '{numero_ato}' registrado! "
    if len(lista_uploads) > 0:
        msg_final += f"{len(lista_uploads)} arquivo(s) lido(s) pela IA e "
    if total_afetados_ia > 0:
        msg_final += f"{total_afetados_ia} status de candidato(s) atualizados automaticamente!"
    else:
        msg_final += "informações sincronizadas."

    return RedirectResponse(url=f"/certames/{id_certame}/acompanhamento?msg={msg_final}", status_code=303)


@app.post("/certames/{id_certame}/acompanhamento/zerar")
def zerar_acompanhamento(id_certame: int, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    res = engine.zerar_acompanhamento_certame(id_certame)

    msg_txt = res.get("mensagem", "Acompanhamento zerado com sucesso!")
    return RedirectResponse(url=f"/certames/{id_certame}/acompanhamento?msg={msg_txt}", status_code=303)


class CandidatoProvimentoUpdateSchema(BaseModel):
    edital_convocacao: Optional[str] = ""
    data_posse: Optional[str] = ""
    data_exoneracao: Optional[str] = ""
    edital_desistencia: Optional[str] = ""
    sub_judice: Optional[str] = "NÃO"

@app.post("/api/candidatos/{id_candidato}/atualizar-provimento")
def atualizar_provimento_candidato_api(
    id_candidato: int,
    payload: CandidatoProvimentoUpdateSchema,
    db: Session = Depends(get_db)
):
    from datetime import datetime, date, time, timedelta

    cand = db.query(Candidato).filter_by(id_candidato=id_candidato).first()
    if not cand:
        return JSONResponse({"status": "ERRO", "mensagem": "Candidato não encontrado"}, status_code=404)

    def parse_dt(v):
        if not v or not str(v).strip() or str(v).strip() in ['—', '-', 'None', 'null']: return None
        for f in ["%Y-%m-%d", "%d/%m/%Y"]:
            try: return datetime.strptime(str(v).strip(), f).date()
            except Exception: pass
        return None

    dt_posse = parse_dt(payload.data_posse)
    dt_exon = parse_dt(payload.data_exoneracao)
    conv_txt = payload.edital_convocacao.strip() if payload.edital_convocacao else ""
    desist_txt = payload.edital_desistencia.strip() if payload.edital_desistencia else ""
    is_sj = (payload.sub_judice or "").strip().upper() in ["SIM", "S", "TRUE", "1"]

    # Calcular novo status dinamicamente
    if dt_exon:
        novo_status = "EXCLUÍDO / EXONERADO"
    elif dt_posse:
        novo_status = "EMPOSSADO"
    elif desist_txt:
        novo_status = "DESISTENTE / RENÚNCIA"
    elif is_sj:
        novo_status = "SUB JÚDICE / POSSE POR DECISÃO JUDICIAL"
    elif conv_txt:
        novo_status = "CONVOCADO"
    else:
        if "APROVADO" in (cand.status_atual or "").upper():
            novo_status = "APROVADO (AGUARDANDO CONVOCAÇÃO)"
        else:
            novo_status = "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

    cand.status_atual = novo_status

    # 1. Atualizar Convocação
    if conv_txt or dt_posse or novo_status in ["CONVOCADO", "EMPOSSADO"]:
        conv = db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).first()
        doe_dt = dt_posse or date.today()
        num_p = conv_txt if conv_txt else "Portaria Convocação"
        if not conv:
            conv = Convocacao(
                id_concurso=cand.id_concurso,
                id_candidato=cand.id_candidato,
                ordem_convocacao_global=cand.classificacao_original,
                numero_portaria=num_p,
                data_publicacao_doe=doe_dt,
                prazo_posse_limite=doe_dt + timedelta(days=30),
                compareceu=(novo_status == "EMPOSSADO")
            )
            db.add(conv)
        else:
            conv.numero_portaria = num_p
            if dt_posse: conv.data_publicacao_doe = dt_posse
            conv.compareceu = (novo_status == "EMPOSSADO")

    # 2. Atualizar Movimentação de Posse
    if dt_posse:
        mov_p = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_POSSE").first()
        dt_p_dt = datetime.combine(dt_posse, datetime.min.time())
        if not mov_p:
            mov_p = MovimentacaoCandidato(
                id_candidato=cand.id_candidato,
                tipo_evento="TERMO_POSSE",
                numero_processo_sei=conv_txt or "TERMO_POSSE",
                data_registro=dt_p_dt,
                motivo_justificativa="Termo de Posse e Exercício alterado via edição direta na tabela"
            )
            db.add(mov_p)
        else:
            mov_p.data_registro = dt_p_dt
            if conv_txt: mov_p.numero_processo_sei = conv_txt
    else:
        db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_POSSE").delete()

    # 3. Atualizar Movimentação de Desistência
    if desist_txt:
        mov_d = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_DESISTENCIA").first()
        if not mov_d:
            mov_d = MovimentacaoCandidato(
                id_candidato=cand.id_candidato,
                tipo_evento="TERMO_DESISTENCIA",
                numero_processo_sei=desist_txt,
                data_registro=datetime.utcnow(),
                motivo_justificativa=f"Homologação de Desistência nº {desist_txt}"
            )
            db.add(mov_d)
        else:
            mov_d.numero_processo_sei = desist_txt
    else:
        if "DESISTENTE" not in novo_status:
            db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="TERMO_DESISTENCIA").delete()

    # 4. Atualizar Movimentação de Exoneração
    if dt_exon:
        mov_e = db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="EXONERACAO").first()
        dt_e_dt = datetime.combine(dt_exon, datetime.min.time())
        if not mov_e:
            mov_e = MovimentacaoCandidato(
                id_candidato=cand.id_candidato,
                tipo_evento="EXONERACAO",
                numero_processo_sei="EXONERACAO",
                data_registro=dt_e_dt,
                motivo_justificativa=f"Exoneração registrada em {dt_exon}"
            )
            db.add(mov_e)
        else:
            mov_e.data_registro = dt_e_dt
    else:
        if "EXONERADO" not in novo_status:
            db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato, tipo_evento="EXONERACAO").delete()

    # 5. Atualizar Lotacionograma
    empossados_cnt = db.query(Candidato).filter(
        (Candidato.id_cargo == cand.id_cargo),
        (Candidato.status_atual == "EMPOSSADO")
    ).count()
    
    lot = db.query(Lotacionograma).filter_by(id_cargo=cand.id_cargo).first()
    if lot:
        lot.vagas_ocupadas_oficial = empossados_cnt
        lot.vagas_disponiveis_oficial = max(0, lot.vagas_criadas_lei - empossados_cnt)

    db.commit()

    engine = AuditEngine(db)
    matriz_cargos = engine.consolidar_matriz_cargo_acompanhamento(cand.id_certame or 1)

    return JSONResponse({
        "status": "SUCESSO",
        "novo_status": cand.status_atual,
        "id_candidato": cand.id_candidato,
        "id_cargo": cand.id_cargo,
        "matriz_cargos": matriz_cargos
    })


# --- ROTAS DE GERAÇÃO DE DOSSIÊS EM SEPARADO E RELATÓRIO ANALÍTICO ---

# 1. Dossiê e Parecer Prévio (Fase Pré-Edital)
@app.get("/certames/{id_certame}/dossie-pre-edital", response_class=HTMLResponse)
def certame_dossie_pre_edital(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    analises = db.query(CertameAnaliseTCE).filter_by(id_certame=id_certame).all()
    anexos = db.query(CertameAnexo).filter_by(id_certame=id_certame).order_by(CertameAnexo.data_upload.asc()).all()

    return templates.TemplateResponse("dossie_pre_edital.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "analises": analises,
        "anexos": anexos,
        "data_hoje": date.today()
    })

# 2. Dossiê e Parecer Técnico da Fase Oficial (Pós-Edital)
@app.get("/certames/{id_certame}/dossie-fase-oficial", response_class=HTMLResponse)
def certame_dossie_fase_oficial(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    anexos = db.query(CertameAnexo).filter_by(id_certame=id_certame).order_by(CertameAnexo.data_upload.asc()).all()

    return templates.TemplateResponse("dossie_fase_oficial.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "anexos": anexos,
        "data_hoje": date.today()
    })

def classificar_fase_documento(tipo_doc: str):
    if not tipo_doc:
        return ("Fase Pré-Edital", "bg-emerald-100 text-emerald-800 border-emerald-300")
    
    tp = tipo_doc.upper().strip()
    
    if tp.startswith("ACOMPANHAMENTO_") or tp in [
        "PORTARIA_CONVOCACAO", "TERMO_POSSE", "TERMO_DESISTENCIA", 
        "RECLASSIFICACAO_FIM_FILA", "DECISAO_JUDICIAL", "TERMO_RENUNCIA"
    ]:
        return ("Acompanhamento", "bg-amber-100 text-amber-800 border-amber-300")

    if tp.startswith("PARECER_"):
        return ("Parecer Técnico", "bg-purple-100 text-purple-800 border-purple-300")

    fase_oficial_types = [
        "EDITAL_ABERTURA_OFICIAL", "EDITAL_OFICIAL", "EDITAL_ABERTURA",
        "PUBLICACAO_EDITAL", "PUBLICACAO_EDITAL_ABERTURA",
        "RETIFICACAO_EDITAL", "RETIFICACAO", "RETIFICACAO_EDITAL_OFICIAL",
        "PUBLICACAO_RETIFICACAO", "PUBLICACAO_RETIFICACAO_EDITAL",
        "HOMOLOGACAO_INSCRICOES", "HOMOLOGACAO_INSCRIÇOES",
        "PUBLICACAO_INSCRICOES_DEFERIDAS", "PUBLICACAO_INSCRICOES",
        "GABARITO_PRELIMINAR", "GABARITO_DEFINITIVO",
        "RESULTADO_PRELIMINAR", "PUBLICACAO_RESULTADO_PRELIMINAR",
        "RESULTADO_DEFINITIVO", "PUBLICACAO_RESULTADO_DEFINITIVO",
        "HOMOLOGACAO_RESULTADO_FINAL", "HOMOLOGACAO_FINAL",
        "PUBLICACAO_HOMOLOGACAO_RESULTADO_FINAL", "PUBLICACAO_HOMOLOGACAO_FINAL", "PUBLICACAO_HOMOLOGACAO"
    ]
    if tp in fase_oficial_types or any(k in tp for k in ["RESULTADO", "GABARITO", "HOMOLOGACAO", "RETIFICACAO", "INSCRICOES_DEFERIDAS"]):
        return ("Fase Oficial", "bg-indigo-100 text-indigo-800 border-indigo-300")

    return ("Fase Pré-Edital", "bg-emerald-100 text-emerald-800 border-emerald-300")


# 3. Dossiê Geral Unificado (Todas as Fases)
@app.get("/certames/{id_certame}/dossie-geral", response_class=HTMLResponse)
@app.get("/certames/{id_certame}/dossie", response_class=HTMLResponse)
def certame_dossie_geral(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    matriz_cargos = engine.consolidar_matriz_cargo_acompanhamento(id_certame)
    analises = db.query(CertameAnaliseTCE).filter_by(id_certame=id_certame).all()
    anexos_raw = db.query(CertameAnexo).filter_by(id_certame=id_certame).order_by(CertameAnexo.data_upload.asc()).all()

    anexos = []
    for a in anexos_raw:
        rotulo, cor = classificar_fase_documento(a.tipo_documento)
        a.fase_rotulo = rotulo
        a.fase_cor = cor
        anexos.append(a)

    return templates.TemplateResponse("dossie_geral.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "matriz_cargos": matriz_cargos,
        "analises": analises,
        "anexos": anexos,
        "data_hoje": date.today()
    })

# 4. Relatório Analítico de Acompanhamento do Certame (Provimentos & Vagas)
@app.get("/certames/{id_certame}/acompanhamento/relatorio-analitico", response_class=HTMLResponse)
def certame_relatorio_analitico_acompanhamento(id_certame: int, request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    concurso = engine.obter_ou_criar_dados_acompanhamento(id_certame)
    matriz_cargos = engine.consolidar_matriz_cargo_acompanhamento(id_certame)
    alertas_controle = engine.gerar_alertas_controle_interno_acompanhamento(id_certame)

    candidatos = db.query(Candidato).filter_by(id_certame=id_certame).order_by(Candidato.id_cargo, Candidato.classificacao_efetiva).all()
    atos_registrados = db.query(CertameAcompanhamentoAto).filter_by(id_certame=id_certame).order_by(CertameAcompanhamentoAto.data_registro.desc()).all()

    return templates.TemplateResponse("relatorio_analitico_acompanhamento.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "concurso": concurso,
        "candidatos": candidatos,
        "matriz_cargos": matriz_cargos,
        "alertas_controle": alertas_controle,
        "atos_registrados": atos_registrados,
        "data_hoje": date.today()
    })

# --- ROTA DE CONCURSO EXPIRADO ---
@app.get("/certames/{id_certame}/expirado", response_class=HTMLResponse)
def certames_concurso_expirado(
    id_certame: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    dossie_expirado = engine.gerar_dossie_concurso_expirado(id_certame)
    
    fase_pre = certame
    fase_oficial = db.query(CertameFaseOficial).filter_by(id_certame=id_certame).first()
    atos_vigencia = db.query(CertameVigenciaAto).filter_by(id_certame=id_certame).order_by(CertameVigenciaAto.data_publicacao.asc()).all()

    return templates.TemplateResponse("certame_expirado.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "concurso": dossie_expirado["concurso"],
        "fase_oficial": fase_oficial,
        "atos_vigencia": atos_vigencia,
        "quadro_cargos": dossie_expirado["quadro_cargos"],
        "totais": dossie_expirado["totais"],
        "candidatos": dossie_expirado["candidatos"],
        "active_page": "expirado"
    })

@app.get("/certames/{id_certame}/expirado/relatorio-analitico", response_class=HTMLResponse)
def certames_relatorio_analitico_expirado(
    id_certame: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    dossie_expirado = engine.gerar_dossie_concurso_expirado(id_certame)
    
    return templates.TemplateResponse("relatorio_analitico_expirado.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "concurso": dossie_expirado["concurso"],
        "quadro_cargos": dossie_expirado["quadro_cargos"],
        "totais": dossie_expirado["totais"],
        "candidatos": dossie_expirado["candidatos"],
        "data_hoje": date.today()
    })

@app.get("/certames/{id_certame}/relatorio-auditoria-final", response_class=HTMLResponse)
@app.get("/certames/{id_certame}/expirado/auditoria", response_class=HTMLResponse)
def certames_relatorio_auditoria_final(
    id_certame: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_auditoria_final(id_certame)

    return templates.TemplateResponse("certame_relatorio_auditoria_final.html", {
        "request": request,
        "usuario": usuario,
        "certame": dados["certame"],
        "concurso": dados["concurso"],
        "fase_oficial": dados["fase_oficial"],
        "parecer_tecnico": dados["parecer_tecnico"],
        "parecer_oficial": dados["parecer_oficial"],
        "atos_vigencia": dados["atos_vigencia"],
        "timeline_datas": dados["timeline_datas"],
        "dias_vigencia": dados["dias_vigencia"],
        "is_expirado": dados["is_expirado"],
        "quadro_cargos": dados["quadro_cargos"],
        "totais": dados["totais"],
        "distribuicao_escolaridade": dados["distribuicao_escolaridade"],
        "candidatos": dados["candidatos"],
        "data_hoje": date.today(),
        "active_page": "relatorio_auditoria_final"
    })

# --- MÓDULO DE RELATÓRIOS DE AUDITORIA ---
@app.get("/modulo/relatorios", response_class=HTMLResponse)
@app.get("/modulo/relatorios-auditoria", response_class=HTMLResponse)
@app.get("/relatorios", response_class=HTMLResponse)
def modulo_relatorios_geral(
    request: Request,
    id_certame: int = None,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    todos_certames = db.query(CertameAbertura).order_by(CertameAbertura.ano.desc(), CertameAbertura.numero_certame.asc()).all()
    if id_certame:
        certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    else:
        certame = todos_certames[0] if todos_certames else None
        
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_auditoria_final(certame.id_certame)

    return templates.TemplateResponse("modulo_relatorios.html", {
        "request": request,
        "usuario": usuario,
        "certame": dados["certame"],
        "todos_certames": todos_certames,
        "concurso": dados["concurso"],
        "fase_oficial": dados["fase_oficial"],
        "quadro_cargos": dados["quadro_cargos"],
        "totais": dados["totais"],
        "distribuicao_escolaridade": dados["distribuicao_escolaridade"],
        "is_expirado": dados["is_expirado"],
        "data_hoje": date.today(),
        "active_page": "modulo_relatorios"
    })

@app.get("/certames/{id_certame}/relatorios", response_class=HTMLResponse)
@app.get("/certames/{id_certame}/relatorios/quantitativo-consolidado", response_class=HTMLResponse)
def certames_relatorios_modulo(
    id_certame: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    todos_certames = db.query(CertameAbertura).order_by(CertameAbertura.ano.desc(), CertameAbertura.numero_certame.asc()).all()
    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_auditoria_final(id_certame)

    return templates.TemplateResponse("modulo_relatorios.html", {
        "request": request,
        "usuario": usuario,
        "certame": dados["certame"],
        "todos_certames": todos_certames,
        "concurso": dados["concurso"],
        "fase_oficial": dados["fase_oficial"],
        "quadro_cargos": dados["quadro_cargos"],
        "totais": dados["totais"],
        "distribuicao_escolaridade": dados["distribuicao_escolaridade"],
        "is_expirado": dados["is_expirado"],
        "data_hoje": date.today(),
        "active_page": "modulo_relatorios"
    })

# --- 2º RELATÓRIO GERENCIAL: ROL NOMINAL DE CONVOCADOS POR CARGO ---
@app.get("/modulo/relatorios/rol-convocados", response_class=HTMLResponse)
def modulo_relatorios_rol_convocados(
    request: Request,
    id_certame: int = None,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    todos_certames = db.query(CertameAbertura).order_by(CertameAbertura.ano.desc(), CertameAbertura.numero_certame.asc()).all()
    if id_certame:
        certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    else:
        certame = todos_certames[0] if todos_certames else None
        
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_nominal_convocados(certame.id_certame)

    return templates.TemplateResponse("modulo_relatorio_nominal_convocados.html", {
        "request": request,
        "usuario": usuario,
        "certame": dados["certame"],
        "todos_certames": todos_certames,
        "concurso": dados["concurso"],
        "fase_oficial": dados["fase_oficial"],
        "grupos_cargos": dados["grupos_cargos"],
        "totais": dados["totais"],
        "data_hoje": dados["data_hoje"],
        "is_expirado": dados["is_expirado"],
        "active_page": "modulo_relatorios"
    })

@app.get("/certames/{id_certame}/relatorios/rol-convocados", response_class=HTMLResponse)
@app.get("/certames/{id_certame}/rol-convocados", response_class=HTMLResponse)
def certames_relatorio_rol_convocados(
    id_certame: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    todos_certames = db.query(CertameAbertura).order_by(CertameAbertura.ano.desc(), CertameAbertura.numero_certame.asc()).all()
    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_nominal_convocados(id_certame)

    return templates.TemplateResponse("modulo_relatorio_nominal_convocados.html", {
        "request": request,
        "usuario": usuario,
        "certame": dados["certame"],
        "todos_certames": todos_certames,
        "concurso": dados["concurso"],
        "fase_oficial": dados["fase_oficial"],
        "grupos_cargos": dados["grupos_cargos"],
        "totais": dados["totais"],
        "data_hoje": dados["data_hoje"],
        "is_expirado": dados["is_expirado"],
        "active_page": "modulo_relatorios"
    })

# --- ROTA DE EXPORTAÇÃO PDF DO ROL NOMINAL DE CONVOCADOS COM FILTRO APLICADO ---
@app.get("/certames/{id_certame}/relatorios/rol-convocados/pdf")
def certames_relatorio_rol_convocados_pdf(
    id_certame: int,
    cargo: str = "",
    cargos: str = "",
    situacao: str = "",
    busca: str = "",
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame:
        certame = db.query(CertameAbertura).first()
    if not certame:
        return RedirectResponse(url="/certames", status_code=303)

    cargo_filtro = cargo or cargos or ""

    engine = AuditEngine(db)
    dados = engine.gerar_relatorio_nominal_convocados(certame.id_certame)

    res = PDFTextGenerator.gerar_pdf_rol_convocados_filtrado(
        certame=certame,
        filtro_cargo_cod=cargo_filtro,
        filtro_situacao=situacao,
        termo_busca=busca,
        grupos_cargos=dados["grupos_cargos"],
        totais=dados["totais"],
        pasta_upload=UPLOAD_DIR
    )

    return FileResponse(
        res["caminho_arquivo"],
        media_type="application/pdf",
        filename=res["nome_arquivo"]
    )

@app.get("/modulo/relatorios/rol-convocados/pdf")
def modulo_relatorio_rol_convocados_pdf(
    id_certame: int = None,
    cargo: str = "",
    cargos: str = "",
    situacao: str = "",
    busca: str = "",
    db: Session = Depends(get_db),
    usuario = Depends(get_current_user)
):
    if not id_certame:
        todos = db.query(CertameAbertura).order_by(CertameAbertura.ano.desc(), CertameAbertura.numero_certame.asc()).all()
        id_certame = todos[0].id_certame if todos else 1
    return certames_relatorio_rol_convocados_pdf(
        id_certame=id_certame,
        cargo=cargo,
        cargos=cargos,
        situacao=situacao,
        busca=busca,
        db=db,
        usuario=usuario
    )

# --- ROTA DE VIGÊNCIA DO CERTAME ---
@app.get("/certames/{id_certame}/vigencia", response_class=HTMLResponse)
def tela_vigencia_certame(
    id_certame: int, 
    request: Request, 
    msg: str = None, 
    db: Session = Depends(get_db), 
    usuario = Depends(get_current_user)
):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    engine = AuditEngine(db)
    concurso = engine.obter_ou_criar_dados_acompanhamento(id_certame)
    fase_oficial = db.query(CertameFaseOficial).filter_by(id_certame=id_certame).first()

    atos_vigencia = db.query(CertameVigenciaAto).filter_by(id_certame=id_certame).order_by(CertameVigenciaAto.data_publicacao.asc()).all()

    # Cálculo da Vigência
    data_homologacao = None
    if fase_oficial and fase_oficial.data_homologacao_resultado_final:
        data_homologacao = fase_oficial.data_homologacao_resultado_final
    elif concurso and concurso.data_homologacao:
        data_homologacao = concurso.data_homologacao
    elif atos_vigencia and atos_vigencia[0].data_inicio_vigencia:
        data_homologacao = atos_vigencia[0].data_inicio_vigencia
    else:
        data_homologacao = certame.data_abertura_processo or date(2024, 6, 1)

    # Determinação dinâmica do prazo de validade (12 meses para seletivo / 24 para concurso)
    prazo_original_meses = getattr(concurso, 'prazo_validade_meses', None) or (fase_oficial.prazo_validade_meses if (fase_oficial and getattr(fase_oficial, 'prazo_validade_meses', None)) else (12 if 'SELETIVO' in (certame.modalidade or '').upper() else 24))

    anos_vigencia = prazo_original_meses // 12
    meses_extra = prazo_original_meses % 12
    try:
        data_fim_original = date(data_homologacao.year + anos_vigencia, data_homologacao.month + meses_extra, data_homologacao.day)
    except Exception:
        data_fim_original = data_homologacao + timedelta(days=int(prazo_original_meses * 30.4375))

    data_fim_efetiva = data_fim_original
    status_vigencia = "VIGENTE"
    total_prorrogacoes = 0

    if atos_vigencia:
        for ato in atos_vigencia:
            if ato.tipo_ato in ["DECRETO_PRORROGACAO", "ADITIVO_VIGENCIA"]:
                total_prorrogacoes += 1
            if ato.nova_data_fim_vigencia and ato.nova_data_fim_vigencia > data_fim_efetiva:
                data_fim_efetiva = ato.nova_data_fim_vigencia

        ultimo_ato = atos_vigencia[-1]
        if ultimo_ato.tipo_ato == "TERMO_SUSPENSAO":
            status_vigencia = "SUSPENSO"

    hoje = date.today()
    if status_vigencia != "SUSPENSO":
        if data_fim_efetiva >= hoje:
            status_vigencia = "VIGENTE" if total_prorrogacoes == 0 else "PRORROGADO"
        else:
            status_vigencia = "EXPIRADO"

    dias_restantes = (data_fim_efetiva - hoje).days

    # Atualiza status e vigência no concurso
    if concurso:
        concurso.data_homologacao = data_homologacao
        concurso.prazo_validade_meses = prazo_original_meses
        concurso.data_validade_final = data_fim_efetiva
        concurso.status = status_vigencia
        db.commit()

    # Alertas de Auditoria (incluindo provimentos após expiração)
    alertas_controle = engine.gerar_alertas_controle_interno_acompanhamento(id_certame)

    # Identificar nomeações/posses irregulares após a vigência
    posses_irregulares = [a for a in alertas_controle if a.get("tipo") == "CONVOCACAO_POSSE_APOS_VIGENCIA"]

    return templates.TemplateResponse("certame_vigencia.html", {
        "request": request,
        "usuario": usuario,
        "certame": certame,
        "concurso": concurso,
        "fase_oficial": fase_oficial,
        "atos_vigencia": atos_vigencia,
        "data_homologacao": data_homologacao,
        "prazo_original_meses": prazo_original_meses,
        "data_fim_original": data_fim_original,
        "data_fim_efetiva": data_fim_efetiva,
        "total_prorrogacoes": total_prorrogacoes,
        "status_vigencia": status_vigencia,
        "dias_restantes": dias_restantes,
        "alertas_controle": alertas_controle,
        "posses_irregulares": posses_irregulares,
        "mensagem": msg
    })


@app.post("/certames/{id_certame}/vigencia/adicionar-ato")
async def adicionar_ato_vigencia(
    id_certame: int,
    request: Request,
    numero_ato: str = Form(...),
    tipo_ato: str = Form(...),
    data_publicacao: str = Form(None),
    prazo_validade_meses: int = Form(24),
    nova_data_fim_vigencia: str = Form(None),
    motivo_justificativa: str = Form(""),
    arquivos: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    caminho_salvo = None
    nome_salvo_orig = None
    texto_extraido = ""

    if arquivos:
        for f in arquivos:
            if f and f.filename:
                conteudo_bytes = await f.read()
                nome_salvo_orig = f.filename
                nome_arquivo_fs = f"{uuid.uuid4().hex[:6]}_{f.filename}"
                caminho_salvo = os.path.join(pasta_certame, nome_arquivo_fs)
                with open(caminho_salvo, "wb") as file_out:
                    file_out.write(conteudo_bytes)

                if f.filename.lower().endswith(".pdf"):
                    texto_extraido = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
                else:
                    texto_extraido = conteudo_bytes.decode("utf-8", errors="ignore")
                break

    # Trata data de publicação
    dt_pub = date.today()
    if data_publicacao:
        try: dt_pub = date.fromisoformat(data_publicacao)
        except Exception: pass

    # Trata nova data fim de vigência
    dt_fim = None
    if nova_data_fim_vigencia:
        try: dt_fim = date.fromisoformat(nova_data_fim_vigencia)
        except Exception: pass

    if not dt_fim:
        try: dt_fim = date(dt_pub.year + (prazo_validade_meses // 12), dt_pub.month, dt_pub.day)
        except Exception: dt_fim = dt_pub + timedelta(days=prazo_validade_meses * 30)

    num_ato_final = numero_ato
    if numero_ato == "LEITURA_IA_AUTOMATICA" or not numero_ato.strip():
        num_ato_final = f"Decreto de Prorrogação (Ingestão IA) - {dt_pub.strftime('%d/%m/%Y')}"
        if "decreto" in texto_extraido.lower():
            import re
            m = re.search(r"decreto\s*(?:nº|n°|n\.|\s)?\s*(\d+[\/\d]*)", texto_extraido, re.IGNORECASE)
            if m: num_ato_final = f"Decreto nº {m.group(1)}"

    novo_ato = CertameVigenciaAto(
        id_certame=id_certame,
        tipo_ato=tipo_ato,
        numero_ato=num_ato_final,
        data_publicacao=dt_pub,
        prazo_validade_meses=prazo_validade_meses,
        nova_data_fim_vigencia=dt_fim,
        motivo_justificativa=motivo_justificativa or (f"Texto IA: {texto_extraido[:200]}" if texto_extraido else "Alteração de vigência devidamente registrada."),
        caminho_arquivo=caminho_salvo,
        nome_arquivo=nome_salvo_orig
    )
    db.add(novo_ato)

    # Se houver anexo, grava também em CertameAnexo e Repositório
    if caminho_salvo:
        anexo = CertameAnexo(
            id_certame=id_certame,
            tipo_documento="DECRETO_PRORROGACAO_VIGENCIA",
            nome_arquivo=nome_salvo_orig,
            caminho_arquivo=caminho_salvo,
            conteudo_texto=texto_extraido
        )
        db.add(anexo)

        doc_repo = DocumentoRepositorio(
            id_certame=id_certame,
            nome_arquivo_original=nome_salvo_orig,
            caminho_arquivo=caminho_salvo,
            tipo_documento="DECRETO_PRORROGACAO_VIGENCIA",
            tamanho_bytes=os.path.getsize(caminho_salvo) if os.path.exists(caminho_salvo) else 0,
            status_processamento_ia="PROCESSADO_IA",
            resumo_extracao=f"Ato de alteração de vigência ({num_ato_final}) processado."
        )
        db.add(doc_repo)

    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    msg_txt = f"Ato '{num_ato_final}' registrado! Vigência do certame estendida/atualizada até {dt_fim.strftime('%d/%m/%Y')}."
    return RedirectResponse(url=f"/certames/{id_certame}/vigencia?msg={msg_txt}", status_code=303)


@app.post("/certames/{id_certame}/vigencia/configurar-marco-inicial")
async def configurar_marco_inicial_vigencia(
    id_certame: int,
    data_homologacao_str: str = Form(...),
    prazo_validade_meses: int = Form(...),
    numero_decreto: str = Form(None),
    db: Session = Depends(get_db)
):
    certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
    if not certame: return RedirectResponse(url="/certames", status_code=303)

    try:
        dt_homol = date.fromisoformat(data_homologacao_str)
    except Exception:
        dt_homol = date.today()

    if certame.fase_oficial:
        certame.fase_oficial.data_homologacao_resultado_final = dt_homol
        certame.fase_oficial.prazo_validade_meses = prazo_validade_meses
        if numero_decreto and numero_decreto.strip():
            certame.fase_oficial.numero_decreto_homologacao = numero_decreto.strip()
    
    concurso = db.query(Concurso).filter_by(id_certame=id_certame).first()
    if concurso:
        concurso.data_homologacao = dt_homol
        concurso.prazo_validade_meses = prazo_validade_meses
        anos = prazo_validade_meses // 12
        meses_extra = prazo_validade_meses % 12
        try:
            concurso.data_validade_final = date(dt_homol.year + anos, dt_homol.month + meses_extra, dt_homol.day)
        except Exception:
            concurso.data_validade_final = dt_homol + timedelta(days=int(prazo_validade_meses * 30.4375))
        
        hoje = date.today()
        concurso.status = "VIGENTE" if concurso.data_validade_final >= hoje else "EXPIRADO"

    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    return RedirectResponse(url=f"/certames/{id_certame}/vigencia?msg=Marco inicial e prazo de validade ({prazo_validade_meses} meses) atualizados com sucesso!", status_code=303)


@app.post("/certames/{id_certame}/vigencia/excluir-ato/{id_vigencia_ato}")
def excluir_ato_vigencia(id_certame: int, id_vigencia_ato: int, db: Session = Depends(get_db)):
    ato = db.query(CertameVigenciaAto).filter_by(id_vigencia_ato=id_vigencia_ato, id_certame=id_certame).first()
    if ato:
        if ato.caminho_arquivo and os.path.exists(ato.caminho_arquivo):
            try: os.remove(ato.caminho_arquivo)
            except Exception: pass
        db.delete(ato)
        db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    return RedirectResponse(url=f"/certames/{id_certame}/vigencia?msg=Ato de vigência excluído!", status_code=303)

# Rotas de Servimento / Visualização e Download de PDFs do Acervo Probatório
@app.get("/anexos/{id_anexo}/visualizar")
def visualizar_anexo(id_anexo: int, db: Session = Depends(get_db)):
    anexo = db.query(CertameAnexo).filter_by(id_anexo=id_anexo).first()
    if not anexo or not anexo.caminho_arquivo or not os.path.exists(anexo.caminho_arquivo):
        return Response("Arquivo PDF não encontrado no acervo do certame.", status_code=404)
    
    media_type = "application/pdf" if anexo.caminho_arquivo.lower().endswith(".pdf") else "text/plain"
    return FileResponse(
        path=anexo.caminho_arquivo, 
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'}
    )

@app.get("/anexos/{id_anexo}/baixar")
def baixar_anexo(id_anexo: int, db: Session = Depends(get_db)):
    anexo = db.query(CertameAnexo).filter_by(id_anexo=id_anexo).first()
    if not anexo or not anexo.caminho_arquivo or not os.path.exists(anexo.caminho_arquivo):
        return Response("Arquivo não encontrado no acervo do certame.", status_code=404)
    
    return FileResponse(path=anexo.caminho_arquivo, filename=anexo.nome_arquivo)

@app.post("/anexos/excluir/{id_anexo}")
def excluir_anexo(id_anexo: int, request: Request, db: Session = Depends(get_db)):
    anexo = db.query(CertameAnexo).filter_by(id_anexo=id_anexo).first()
    if not anexo:
        return RedirectResponse(url="/certames", status_code=303)
    
    id_certame = anexo.id_certame
    caminho = anexo.caminho_arquivo
    nome_arquivo = anexo.nome_arquivo

    if caminho and caminho != "TEXTO_DIRETO" and os.path.exists(caminho):
        try:
            os.remove(caminho)
        except Exception:
            pass

    doc_repo = db.query(DocumentoRepositorio).filter(
        (DocumentoRepositorio.caminho_arquivo == caminho) | 
        ((DocumentoRepositorio.id_certame == id_certame) & (DocumentoRepositorio.nome_arquivo_original == nome_arquivo))
    ).first()
    if doc_repo:
        db.delete(doc_repo)

    db.delete(anexo)
    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    referer = request.headers.get("referer")
    if referer:
        sep = "&" if "?" in referer else "?"
        return RedirectResponse(url=f"{referer}{sep}msg=Documento '{nome_arquivo}' excluído do dossiê e evidências reprocessadas com sucesso!", status_code=303)
    return RedirectResponse(url=f"/certames/{id_certame}/documentos?msg=Documento excluído do dossiê!", status_code=303)

@app.post("/anexos/atualizar/{id_anexo}")
async def atualizar_anexo(
    id_anexo: int,
    request: Request,
    arquivo: UploadFile = File(None),
    conteudo_texto: str = Form(None),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    anexo = db.query(CertameAnexo).filter_by(id_anexo=id_anexo).first()
    if not anexo:
        return RedirectResponse(url="/certames", status_code=303)
    
    id_certame = anexo.id_certame
    pasta_certame = os.path.join(UPLOAD_DIR, "certames", f"certame_{id_certame}")
    os.makedirs(pasta_certame, exist_ok=True)

    if arquivo and arquivo.filename:
        if anexo.caminho_arquivo and os.path.exists(anexo.caminho_arquivo):
            try:
                os.remove(anexo.caminho_arquivo)
            except Exception:
                pass

        conteudo_bytes = await arquivo.read()
        tamanho_bytes = len(conteudo_bytes)
        nome_salvo = f"{uuid.uuid4().hex[:6]}_{arquivo.filename}"
        novo_caminho = os.path.join(pasta_certame, nome_salvo)
        with open(novo_caminho, "wb") as f:
            f.write(conteudo_bytes)

        if arquivo.filename.lower().endswith(".pdf"):
            texto = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
        else:
            texto = conteudo_bytes.decode("utf-8", errors="ignore")

        anexo.nome_arquivo = arquivo.filename
        anexo.caminho_arquivo = novo_caminho
        if texto:
            anexo.conteudo_texto = texto
        anexo.data_upload = datetime.utcnow()

        doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame, nome_arquivo_original=anexo.nome_arquivo).first()
        if not doc_repo:
            doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame).first()
        if doc_repo:
            doc_repo.nome_arquivo_original = arquivo.filename
            doc_repo.caminho_arquivo = novo_caminho
            doc_repo.tamanho_bytes = tamanho_bytes
            doc_repo.data_upload = datetime.utcnow()
            doc_repo.status_processamento_ia = "ATUALIZADO_COM_SUCESSO"
    elif conteudo_texto and conteudo_texto.strip():
        certame = db.query(CertameAbertura).filter_by(id_certame=id_certame).first()
        num_cert = certame.numero_certame if certame else "001/2024"

        if anexo.caminho_arquivo and os.path.exists(anexo.caminho_arquivo):
            try:
                os.remove(anexo.caminho_arquivo)
            except Exception:
                pass

        res_pdf = PDFTextGenerator.gerar_pdf_de_texto(
            id_certame=id_certame,
            numero_certame=num_cert,
            tipo_documento=anexo.tipo_documento,
            conteudo_texto=conteudo_texto.strip(),
            pasta_upload=pasta_certame
        )
        anexo.conteudo_texto = conteudo_texto.strip()
        anexo.caminho_arquivo = res_pdf["caminho_arquivo"]
        anexo.nome_arquivo = res_pdf["nome_arquivo"]
        anexo.data_upload = datetime.utcnow()

        doc_repo = db.query(DocumentoRepositorio).filter_by(id_certame=id_certame, tipo_documento=anexo.tipo_documento).first()
        if doc_repo:
            doc_repo.nome_arquivo_original = res_pdf["nome_arquivo"]
            doc_repo.caminho_arquivo = res_pdf["caminho_arquivo"]
            doc_repo.tamanho_bytes = res_pdf["tamanho_bytes"]
            doc_repo.data_upload = datetime.utcnow()
            doc_repo.status_processamento_ia = "ATUALIZADO_COM_SUCESSO"

    db.commit()

    engine = AuditEngine(db)
    engine.executar_analise_tce_certame(id_certame)

    referer = request.headers.get("referer")
    if referer:
        sep = "&" if "?" in referer else "?"
        return RedirectResponse(url=f"{referer}{sep}msg=Documento '{anexo.nome_arquivo}' e evidências do dossiê atualizados com sucesso!", status_code=303)
    return RedirectResponse(url=f"/certames/{id_certame}/documentos?msg=Documento atualizado!", status_code=303)


@app.get("/repositorio/visualizar/{id_documento}")
def visualizar_documento_repositorio(id_documento: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentoRepositorio).filter_by(id_documento=id_documento).first()
    if not doc or not doc.caminho_arquivo or not os.path.exists(doc.caminho_arquivo):
        return Response("Arquivo não encontrado no repositório.", status_code=404)
    
    media_type = "application/pdf" if doc.caminho_arquivo.lower().endswith(".pdf") else "text/plain"
    return FileResponse(
        path=doc.caminho_arquivo, 
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{doc.nome_arquivo_original}"'}
    )

@app.get("/repositorio/baixar/{id_documento}")
def baixar_documento_repositorio(id_documento: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentoRepositorio).filter_by(id_documento=id_documento).first()
    if not doc or not doc.caminho_arquivo or not os.path.exists(doc.caminho_arquivo):
        return Response("Arquivo não encontrado no repositório.", status_code=404)
    
    return FileResponse(path=doc.caminho_arquivo, filename=doc.nome_arquivo_original)

# Repositório de Documentos Organizado por Certame
@app.get("/repositorio", response_class=HTMLResponse)
def tela_repositorio(request: Request, db: Session = Depends(get_db), usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    certames = db.query(CertameAbertura).order_by(CertameAbertura.data_abertura_processo.desc()).all()
    
    for c in certames:
        anexos_ordenados = []
        for a in c.anexos:
            rotulo, cor = classificar_fase_documento(a.tipo_documento)
            a.fase_rotulo = rotulo
            a.fase_cor = cor
            anexos_ordenados.append(a)
        c.anexos_ordenados = anexos_ordenados

    docs_avulsos = db.query(DocumentoRepositorio).filter(DocumentoRepositorio.id_certame == None).order_by(DocumentoRepositorio.data_upload.desc()).all()
    docs_todos = db.query(DocumentoRepositorio).order_by(DocumentoRepositorio.data_upload.desc()).all()

    return templates.TemplateResponse("repositorio.html", {
        "request": request,
        "usuario": usuario,
        "certames": certames,
        "documentos_avulsos": docs_avulsos,
        "documentos": docs_todos
    })

@app.post("/repositorio/excluir/{id_documento}")
def excluir_documento(id_documento: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentoRepositorio).filter_by(id_documento=id_documento).first()
    if doc:
        if os.path.exists(doc.caminho_arquivo):
            try: os.remove(doc.caminho_arquivo)
            except Exception: pass
        db.delete(doc)
        db.commit()
    return RedirectResponse(url="/repositorio", status_code=303)

@app.post("/repositorio/atualizar/{id_documento}")
async def atualizar_documento_repositorio(
    id_documento: int,
    request: Request,
    arquivo: UploadFile = File(None),
    conteudo_texto: str = Form(None),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    doc = db.query(DocumentoRepositorio).filter_by(id_documento=id_documento).first()
    if not doc:
        return RedirectResponse(url="/repositorio", status_code=303)
    
    texto = ""
    if arquivo and arquivo.filename:
        if doc.caminho_arquivo and os.path.exists(doc.caminho_arquivo):
            try:
                os.remove(doc.caminho_arquivo)
            except Exception:
                pass

        conteudo_bytes = await arquivo.read()
        tamanho_bytes = len(conteudo_bytes)
        nome_salvo = f"{uuid.uuid4().hex[:8]}_{arquivo.filename}"
        novo_caminho = os.path.join(UPLOAD_DIR, nome_salvo)
        with open(novo_caminho, "wb") as f:
            f.write(conteudo_bytes)

        if arquivo.filename.lower().endswith(".pdf"):
            texto = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
        else:
            texto = conteudo_bytes.decode("utf-8", errors="ignore")

        doc.nome_arquivo_original = arquivo.filename
        doc.caminho_arquivo = novo_caminho
        doc.tamanho_bytes = tamanho_bytes
        doc.data_upload = datetime.utcnow()
        doc.status_processamento_ia = "ATUALIZADO_COM_SUCESSO"

    elif conteudo_texto and conteudo_texto.strip():
        texto = conteudo_texto.strip()
        if doc.caminho_arquivo and os.path.exists(doc.caminho_arquivo):
            try:
                os.remove(doc.caminho_arquivo)
            except Exception:
                pass
        
        nome_salvo = f"{uuid.uuid4().hex[:8]}_texto_atualizado.txt"
        novo_caminho = os.path.join(UPLOAD_DIR, nome_salvo)
        with open(novo_caminho, "w", encoding="utf-8") as f:
            f.write(texto)

        doc.caminho_arquivo = novo_caminho
        doc.tamanho_bytes = len(texto.encode("utf-8"))
        doc.data_upload = datetime.utcnow()
        doc.status_processamento_ia = "ATUALIZADO_COM_SUCESSO"

    if texto:
        if doc.tipo_documento == "LOTACIONOGRAMA":
            DocumentParserAI.process_lotacionograma_text(texto, db)
        elif doc.tipo_documento in ["EDITAL", "EDITAL_CONCURSO"]:
            DocumentParserAI.process_edital_text(texto, db)
        elif doc.tipo_documento == "PORTARIA_CONVOCACAO":
            DocumentParserAI.process_convocacao_portaria_text(texto, db)

    db.commit()

    engine = AuditEngine(db)
    engine.executar_auditoria_completa()

    return RedirectResponse(url="/repositorio?msg=Documento atualizado e reprocessado com sucesso!", status_code=303)


# Ingestão e Leitura por IA
@app.get("/importar", response_class=HTMLResponse)
def tela_importar(request: Request, msg: str = None, usuario = Depends(get_current_user)):
    if not usuario: return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("importar.html", {
        "request": request,
        "usuario": usuario,
        "mensagem": msg
    })

@app.post("/importar/ia-pdf")
async def importar_ia_pdf(
    tipo_documento: str = Form(...),
    outro_tipo_nome: str = Form(""),
    arquivo: UploadFile = File(None),
    arquivos: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    lista_uploads: List[UploadFile] = []
    if arquivos:
        for f in arquivos:
            if f and f.filename:
                lista_uploads.append(f)
    if arquivo and arquivo.filename and arquivo not in lista_uploads:
        lista_uploads.append(arquivo)

    if not lista_uploads:
        return RedirectResponse(url="/importar?msg=Erro: Nenhum arquivo selecionado.", status_code=303)

    total_processados = 0
    msgs = []

    for item_arq in lista_uploads:
        conteudo_bytes = await item_arq.read()
        tamanho_bytes = len(conteudo_bytes)
        
        nome_salvo = f"{uuid.uuid4().hex[:8]}_{item_arq.filename}"
        caminho_completo = os.path.join(UPLOAD_DIR, nome_salvo)
        with open(caminho_completo, "wb") as f:
            f.write(conteudo_bytes)

        if item_arq.filename.lower().endswith(".pdf"):
            try:
                texto = DocumentParserAI.extract_text_from_pdf(conteudo_bytes)
            except Exception:
                texto = ""
        else:
            try:
                texto = conteudo_bytes.decode("utf-8", errors="ignore")
            except Exception:
                texto = ""

        msg_item = ""
        tipo_classificado = tipo_documento
        if tipo_documento == "OUTROS_DOCUMENTOS_COMPLEMENTARES" and outro_tipo_nome:
            tipo_classificado = outro_tipo_nome.strip().upper()

        cert_target = db.query(CertameAbertura).first()
        id_cert_target = cert_target.id_certame if cert_target else 1

        if ("inscric" in texto.lower() or "cargo" in texto.lower()) and any(k in texto.lower() for k in ["posse", "convoc", "situac", "status", "exoner"]):
            tipo_classificado = "PLANILHA_PROVIMENTO_CSV"
            res = DocumentParserAI.process_csv_provimento_tabular(texto, db, id_cert_target)
            msg_item = f"Planilha de Provimento ({item_arq.filename}): {res.get('afetados', 0)} candidato(s)/provimento(s) atualizados no Acompanhamento."
            engine_item = AuditEngine(db)
            engine_item.importar_dados_fase_oficial_para_acompanhamento(id_cert_target)
        elif tipo_documento == "LOTACIONOGRAMA" or ("lei" in texto.lower() and "vagas" in texto.lower() and tipo_documento == "AUTO"):
            tipo_classificado = "LOTACIONOGRAMA"
            res = DocumentParserAI.process_lotacionograma_text(texto, db)
            msg_item = f"Lotacionograma ({item_arq.filename}): {res.get('registros_processados', 0)} cargo(s)/vagas atualizados."
        elif tipo_documento == "EDITAL" or ("edital" in texto.lower() and tipo_documento == "AUTO"):
            tipo_classificado = "EDITAL_CONCURSO"
            res = DocumentParserAI.process_edital_text(texto, db)
            msg_item = f"Edital {res.get('edital')} ({item_arq.filename}): {res.get('vagas_cargos', 0)} quantitativo(s) cadastrado(s)."
        else:
            tipo_classificado = tipo_classificado or "PORTARIA_CONVOCACAO"
            res = DocumentParserAI.process_convocacao_portaria_text(texto, db)
            msg_item = f"Documento {tipo_classificado} ({item_arq.filename}) processado."

        doc_repo = DocumentoRepositorio(
            nome_arquivo_original=item_arq.filename,
            caminho_arquivo=caminho_completo,
            tipo_documento=tipo_classificado,
            tamanho_bytes=tamanho_bytes,
            status_processamento_ia="PROCESSADO_COM_SUCESSO",
            resumo_extracao=msg_item
        )
        db.add(doc_repo)
        total_processados += 1
        msgs.append(msg_item)

    db.commit()

    engine = AuditEngine(db)
    engine.executar_auditoria_completa()

    msg_resumo = f"{total_processados} arquivo(s) lido(s) e processados pela IA com sucesso!"
    return RedirectResponse(url=f"/importar?msg={msg_resumo}", status_code=303)

@app.post("/importar/texto-direto")
def importar_texto_direto(
    tipo_documento: str = Form("LOTACIONOGRAMA"),
    conteudo_texto: str = Form(""),
    db: Session = Depends(get_db)
):
    if not conteudo_texto or not conteudo_texto.strip():
        return RedirectResponse(url="/importar?msg=Aviso: Insira o texto ou código para efetuar a importação.", status_code=303)

    cert_target = db.query(CertameAbertura).first()
    id_cert_target = cert_target.id_certame if cert_target else 1

    msg = ""
    if ("inscric" in conteudo_texto.lower() or "cargo" in conteudo_texto.lower()) and any(k in conteudo_texto.lower() for k in ["posse", "convoc", "situac", "status", "exoner"]):
        res = DocumentParserAI.process_csv_provimento_tabular(conteudo_texto, db, id_cert_target)
        msg = f"Matriz de Provimentos CSV importada: {res.get('afetados', 0)} candidato(s)/atos atualizados no Acompanhamento."
    elif tipo_documento == "LOTACIONOGRAMA":
        res = DocumentParserAI.process_lotacionograma_text(conteudo_texto, db)
        msg = f"Lotacionograma importado: {res.get('registros_processados', 0)} cargo(s) processados."
    elif tipo_documento == "EDITAL":
        res = DocumentParserAI.process_edital_text(conteudo_texto, db)
        msg = f"Edital importado: {res.get('vagas_cargos', 0)} vaga(s) registradas."
    elif tipo_documento == "CONVOCACAO":
        res = DocumentParserAI.process_convocacao_portaria_text(conteudo_texto, db)
        msg = f"Portaria importada: {res.get('convocacoes_adicionadas', 0)} convocação(ões) registrada(s)."
    else:
        res = DocumentParserAI.process_csv_provimento_tabular(conteudo_texto, db, id_cert_target)
        msg = f"Matriz de Provimentos importada: {res.get('afetados', 0)} candidato(s) atualizados."

    engine = AuditEngine(db)
    engine.importar_dados_fase_oficial_para_acompanhamento(id_cert_target)
    engine.executar_auditoria_completa()

    return RedirectResponse(url=f"/importar?msg={msg}", status_code=303)

@app.post("/executar-auditoria")
def trigger_auditoria(db: Session = Depends(get_db)):
    engine = AuditEngine(db)
    engine.executar_auditoria_completa()
    return RedirectResponse(url="/", status_code=303)

@app.get("/zerar-banco")
def zerar_banco(db: Session = Depends(get_db)):
    db.query(AuditoriaAchado).delete()
    db.query(ContratoTemporario).delete()
    db.query(Afastamento).delete()
    db.query(ServidorEfetivo).delete()
    db.query(Convocacao).delete()
    db.query(MovimentacaoCandidato).delete()
    db.query(Candidato).delete()
    db.query(ConcursoVaga).delete()
    db.query(Concurso).delete()
    db.query(Lotacionograma).delete()
    db.query(Cargo).delete()
    db.query(DocumentoRepositorio).delete()
    db.query(CertameAnaliseTCE).delete()
    db.query(ParecerTecnico).delete()
    db.query(CertameAnexo).delete()
    db.query(CertameAbertura).delete()
    db.commit()

    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            try: os.remove(os.path.join(UPLOAD_DIR, f))
            except Exception: pass

    return RedirectResponse(url="/", status_code=303)

@app.post("/sanar-achado/{id_achado}")
def sanar_achado(id_achado: int, db: Session = Depends(get_db)):
    achado = db.query(AuditoriaAchado).filter_by(id_achado=id_achado).first()
    if achado:
        achado.status_tramitacao = "NOTIFICADO / EM TRATAMENTO"
        db.commit()
    return RedirectResponse(url="/", status_code=303)
