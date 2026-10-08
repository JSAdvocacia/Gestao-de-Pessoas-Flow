import os
import uuid
import hashlib
from datetime import datetime
from fpdf import FPDF

def sanitize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("—", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'").replace("•", "*")
    return s.encode('latin-1', 'replace').decode('latin-1')

class PDFTextGenerator:
    @staticmethod
    def gerar_pdf_de_texto(id_certame: int, numero_certame: str, tipo_documento: str, conteudo_texto: str, pasta_upload: str) -> dict:
        os.makedirs(pasta_upload, exist_ok=True)
        
        tipo_clean = tipo_documento.replace('/', '_').replace(' ', '_').lower()
        nome_arquivo = f"{tipo_clean}_transcrito_{uuid.uuid4().hex[:6]}.pdf"
        caminho_arquivo = os.path.join(pasta_upload, nome_arquivo)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Header Bar
        pdf.set_fill_color(5, 10, 24)
        pdf.rect(0, 0, 210, 30, 'F')

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 6)
        pdf.cell(190, 5, sanitize_text("ESTADO DE MATO GROSSO"), ln=True, align="C")
        
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 150, 94)
        pdf.cell(190, 5, sanitize_text("SISTEMA INTEGRADO DE AUDITORIA DE PESSOAL - CONTROLADORIA MUNICIPAL"), ln=True, align="C")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(190, 5, sanitize_text(f"DOCUMENTO TRANSCRITO * PROCESSO DE CERTAME Nº {numero_certame}"), ln=True, align="C")

        pdf.ln(10)

        # Document Title Box
        pdf.set_fill_color(240, 253, 244)
        pdf.set_draw_color(16, 185, 129)
        pdf.set_text_color(6, 78, 59)
        pdf.set_font("Helvetica", "B", 10)
        
        titulo_doc = tipo_documento.replace('_', ' ').upper()
        pdf.cell(190, 8, sanitize_text(f" TIPO DO DOCUMENTO: {titulo_doc}"), border=1, ln=True, fill=True, align="L")
        
        pdf.ln(6)

        # Body Text
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 41, 59)

        texto_sanitizado = sanitize_text(conteudo_texto)
        pdf.multi_cell(190, 6, texto_sanitizado)

        # Footer Information
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 116, 139)
        
        data_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        hash_val = hashlib.sha256(conteudo_texto.encode('utf-8')).hexdigest()
        
        pdf.cell(190, 5, sanitize_text(f"Data de Ingestao: {data_str} | Chave de Autenticidade (SHA-256): {hash_val[:32]}..."), ln=True, align="C")
        pdf.cell(190, 5, sanitize_text("Documento gerado automaticamente pelo SIAP para instrucao probatoria do Dossie de Auditoria."), ln=True, align="C")

        pdf.output(caminho_arquivo)

        tamanho_bytes = os.path.getsize(caminho_arquivo)
        return {
            "caminho_arquivo": caminho_arquivo,
            "nome_arquivo": nome_arquivo,
            "tamanho_bytes": tamanho_bytes
        }

    @staticmethod
    def gerar_pdf_parecer_definitivo(certame, parecer, pasta_upload: str) -> dict:
        os.makedirs(pasta_upload, exist_ok=True)
        nome_arquivo = f"parecer_definitivo_ci_{certame.numero_certame.replace('/', '_')}.pdf"
        caminho_arquivo = os.path.join(pasta_upload, nome_arquivo)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Header
        pdf.set_fill_color(5, 10, 24)
        pdf.rect(0, 0, 210, 32, 'F')

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        pdf.cell(190, 5, sanitize_text(f"ESTADO DE MATO GROSSO - {certame.municipio.upper()}"), ln=True, align="C")
        
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 150, 94)
        pdf.cell(190, 5, sanitize_text("CONTROLADORIA E AUDITORIA GERAL DO MUNICÍPIO"), ln=True, align="C")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(190, 5, sanitize_text(f"PARECER TÉCNICO DEFINITIVO DO CONTROLE INTERNO * {parecer.numero_parecer}"), ln=True, align="C")

        pdf.ln(10)

        # Title Box
        pdf.set_fill_color(240, 253, 244)
        pdf.set_draw_color(16, 185, 129)
        pdf.set_text_color(6, 78, 59)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(190, 8, sanitize_text(f" ASSUNTO: {parecer.assunto}"), border=1, ln=True, fill=True, align="L")
        
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(16, 185, 129)
        pdf.cell(190, 6, sanitize_text(f"CONCLUSÃO DO CONTROLE INTERNO: {parecer.tipo_conclusao.replace('_', ' ')}"), ln=True)

        pdf.ln(4)

        sections = [
            ("1. Fundamentacao Legal", parecer.fundamentacao_legal),
            ("2. Exigencias Documentais", parecer.documentos_exigidos_texto),
            ("3. Estudo de Impacto Orcamentario LRF", parecer.impacto_orcamentario_texto),
            ("4. Lotacionograma e Existencia de Vagas", parecer.lotacionograma_texto),
            ("5. Licitacao da Banca e Regulamento", parecer.banca_executora_texto or parecer.regulamento_autorizacao_texto),
            ("6. Edital Normativo", parecer.edital_normativo_texto),
            ("7. Publicacao Ampla no DOC/TCE-MT", parecer.publicacao_ampla_doc_tce_texto),
            ("8. Reserva Obrigatoria de Vagas (PcD)", parecer.reserva_vagas_pcd_texto),
            ("9. Prazos e Criterios de Isencao de Taxa", parecer.prazos_isencoes_texto),
            ("10. Conclusao Final do Parecer Definitivo", parecer.conclusao_parecer_texto)
        ]

        for sec_title, sec_body in sections:
            if sec_body and sec_body.strip():
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(190, 6, sanitize_text(sec_title), ln=True)
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(51, 65, 85)
                pdf.multi_cell(190, 5, sanitize_text(sec_body))
                pdf.ln(2)

        # Signature Block
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(190, 5, sanitize_text(f"Auditor Responsavel: {parecer.auditor_responsavel}"), ln=True, align="C")
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 116, 139)
        data_str = datetime.now().strftime('%d/%m/%Y')
        pdf.cell(190, 5, sanitize_text(f"Emitido em: {data_str} * Valido para Remessa de Fiscalizacao ao TCE-MT"), ln=True, align="C")

        pdf.output(caminho_arquivo)
        tamanho_bytes = os.path.getsize(caminho_arquivo)
        return {
            "caminho_arquivo": caminho_arquivo,
            "nome_arquivo": nome_arquivo,
            "tamanho_bytes": tamanho_bytes
        }


    @staticmethod
    def gerar_pdf_parecer_fase_oficial(certame, parecer_oficial, pasta_upload: str) -> dict:
        os.makedirs(pasta_upload, exist_ok=True)
        nome_arquivo = f"parecer_tecnico_fase_oficial_{certame.numero_certame.replace('/', '_')}.pdf"
        caminho_arquivo = os.path.join(pasta_upload, nome_arquivo)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Header
        pdf.set_fill_color(5, 10, 24)
        pdf.rect(0, 0, 210, 32, 'F')

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        pdf.cell(190, 5, sanitize_text(f"ESTADO DE MATO GROSSO - {certame.municipio.upper()}"), ln=True, align="C")
        
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 150, 94)
        pdf.cell(190, 5, sanitize_text("CONTROLADORIA E AUDITORIA GERAL DO MUNICÍPIO"), ln=True, align="C")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(190, 5, sanitize_text(f"PARECER TÉCNICO DE CONFORMIDADE E LEGALIDADE * FASE OFICIAL * {parecer_oficial.numero_parecer}"), ln=True, align="C")

        pdf.ln(10)

        # Title Box
        pdf.set_fill_color(240, 253, 244)
        pdf.set_draw_color(16, 185, 129)
        pdf.set_text_color(6, 78, 59)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(190, 8, sanitize_text(f" OBJETO DA ANÁLISE: {parecer_oficial.objeto_analise}"), border=1, ln=True, fill=True, align="L")
        
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(16, 185, 129)
        conc_label = parecer_oficial.conclusao_tipo.replace('_', ' ')
        pdf.cell(190, 6, sanitize_text(f"CONCLUSÃO DO CONTROLE INTERNO: {conc_label}"), ln=True)

        pdf.ln(4)

        sections = [
            ("Interessado / Orgao", parecer_oficial.interessado_orgao),
            ("Fundamentacao Legal", parecer_oficial.fundamentacao_legal),
            ("1. Relatorio / Breve Historico", parecer_oficial.relatorio_historico),
            ("2. Analise Tecnica e Juridica", parecer_oficial.analise_tecnica_juridica),
            ("3. Conclusao e Recomendacao", f"Opcao: [{conc_label}]\nJustificativa: {parecer_oficial.justificativa_conclusao}")
        ]

        for sec_title, sec_body in sections:
            if sec_body and sec_body.strip():
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(190, 6, sanitize_text(sec_title), ln=True)
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(51, 65, 85)
                pdf.multi_cell(190, 5, sanitize_text(sec_body))
                pdf.ln(2)

        # Signature Block
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(190, 5, sanitize_text(f"Equipe de Controle Interno: {parecer_oficial.auditor_responsavel}"), ln=True, align="C")
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 116, 139)
        data_str = datetime.now().strftime('%d/%m/%Y')
        pdf.cell(190, 5, sanitize_text(f"Emitido em: {data_str} * Valido para Remessa de Fiscalizacao ao TCE-MT"), ln=True, align="C")

        pdf.output(caminho_arquivo)
        tamanho_bytes = os.path.getsize(caminho_arquivo)
        return {
            "caminho_arquivo": caminho_arquivo,
            "nome_arquivo": nome_arquivo,
            "tamanho_bytes": tamanho_bytes
        }
