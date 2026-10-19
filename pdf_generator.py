import os
import uuid
import hashlib
import re
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

    @staticmethod
    def gerar_pdf_rol_convocados_filtrado(
        certame,
        filtro_cargo_cod: str,
        filtro_situacao: str,
        termo_busca: str,
        grupos_cargos: list,
        totais: dict,
        pasta_upload: str
    ) -> dict:
        os.makedirs(pasta_upload, exist_ok=True)

        filtro_nome_slug = "geral"
        if filtro_cargo_cod:
            slug_c = re.sub(r'[^a-zA-Z0-9]+', '_', filtro_cargo_cod.lower())[:35].strip('_')
            filtro_nome_slug = slug_c or "cargos"
        if filtro_situacao:
            filtro_nome_slug += f"_{filtro_situacao}"

        nome_arquivo = f"rol_convocados_{certame.numero_certame.replace('/', '_')}_{filtro_nome_slug}_{uuid.uuid4().hex[:6]}.pdf"
        caminho_arquivo = os.path.join(pasta_upload, nome_arquivo)

        # Filtrar grupos e candidatos (suporte a seleção múltipla de cargos e situações por vírgula)
        cargos_filtro_lista = [c.strip() for c in filtro_cargo_cod.split(",") if c.strip()] if filtro_cargo_cod else []
        situacoes_filtro_lista = [s.strip() for s in filtro_situacao.split(",") if s.strip()] if filtro_situacao else []

        grupos_filtrados = []
        tot_cands_filt = 0
        tot_emp_filt = 0
        tot_des_filt = 0
        tot_exon_filt = 0

        if cargos_filtro_lista:
            nomes_c = [f"{g.get('codigo_cargo')} - {g.get('cargo_nome')}" for g in grupos_cargos if g.get("codigo_cargo") in cargos_filtro_lista]
            nome_cargo_filtrado = "; ".join(nomes_c) if nomes_c else ", ".join(cargos_filtro_lista)
        else:
            nome_cargo_filtrado = "Todos os Cargos Ofertados"

        for g in grupos_cargos:
            cod_g = g.get("codigo_cargo", "")
            if cargos_filtro_lista and cod_g not in cargos_filtro_lista:
                continue

            cands_do_bloco = []
            for c in g.get("candidatos", []):
                # Filtro busca
                if termo_busca:
                    tb = termo_busca.lower()
                    if tb not in c.get("nome_completo", "").lower() and tb not in c.get("cpf", "").lower():
                        continue

                # Filtro situação (suporte a seleção múltipla por vírgula)
                bt = c.get("badge_tipo", "")
                if situacoes_filtro_lista and bt not in situacoes_filtro_lista:
                    continue

                cands_do_bloco.append(c)
                tot_cands_filt += 1
                if bt == "empossado":
                    tot_emp_filt += 1
                elif bt == "desistente":
                    tot_des_filt += 1
                elif bt == "exonerado":
                    tot_exon_filt += 1

            if cands_do_bloco:
                g_copia = dict(g)
                g_copia["candidatos_filtrados"] = cands_do_bloco
                grupos_filtrados.append(g_copia)

        situacao_label_map = {
            "": "Todas as Situações",
            "empossado": "Empossados (Exercício)",
            "desistente": "Desistentes / Renúncias",
            "exonerado": "Excluídos / Exonerados",
            "convocado": "Convocados em Trâmite"
        }
        if situacoes_filtro_lista:
            sit_label = "; ".join(situacao_label_map.get(s, s) for s in situacoes_filtro_lista)
        else:
            sit_label = "Todas as Situações"

        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Header Bar
        pdf.set_fill_color(5, 10, 24)
        pdf.rect(0, 0, 297, 28, 'F')

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 4)
        pdf.cell(277, 5, sanitize_text(f"ESTADO DE MATO GROSSO - PREFEITURA MUNICIPAL DE {certame.municipio.upper()}"), ln=True, align="C")

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 150, 94)
        pdf.cell(277, 5, sanitize_text("SISTEMA INTEGRADO DE AUDITORIA DE PESSOAL (SIAP) - CONTROLADORIA MUNICIPAL"), ln=True, align="C")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(277, 5, sanitize_text(f"ROL NOMINAL DE CANDIDATOS CONVOCADOS POR CARGO * CERTAME Nº {certame.numero_certame} ({certame.ano})"), ln=True, align="C")

        pdf.ln(12)

        # Filter Box
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        pdf.set_text_color(15, 23, 42)
        pdf.rect(10, 32, 277, 16, 'DF')

        pdf.set_xy(12, 34)
        pdf.set_font("Helvetica", "B", 8.5)
        busca_lbl = termo_busca if termo_busca else "Nenhuma"
        cargos_str = nome_cargo_filtrado if len(nome_cargo_filtrado) <= 120 else (nome_cargo_filtrado[:117] + "...")
        pdf.cell(273, 5, sanitize_text(f"FILTRO APLICADO: Cargo(s): {cargos_str} | Situação: {sit_label} | Busca: {busca_lbl}"), ln=True)

        pdf.set_xy(12, 40)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(273, 5, sanitize_text(f"Total de Candidatos no Filtro: {tot_cands_filt} | Em Exercício: {tot_emp_filt} | Desistências: {tot_des_filt} | Exonerações: {tot_exon_filt} | Em Trâmite: {tot_cands_filt - tot_emp_filt - tot_des_filt - tot_exon_filt}"), ln=True)

        pdf.ln(8)

        if not grupos_filtrados:
            pdf.ln(10)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(225, 29, 72)
            pdf.cell(277, 10, sanitize_text("Nenhum candidato localizado com os critérios de filtro selecionados."), border=1, align="C")
        else:
            for gf in grupos_filtrados:
                # Cargo Subheader
                pdf.ln(2)
                pdf.set_fill_color(30, 41, 59)
                pdf.set_draw_color(15, 23, 42)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 8.5)
                ved_txt = "0 (CR)" if gf.get("vagas_edital", 0) == 0 else str(gf.get("vagas_edital"))
                c_head = f" {gf.get('codigo_cargo')} - {gf.get('cargo_nome').upper()} [{gf.get('nivel_escolaridade')}] | Vagas Edital: {ved_txt} | Convocados: {gf.get('total_convocados')}"
                pdf.cell(277, 6.5, sanitize_text(c_head), border=1, align="L", fill=True)
                pdf.ln()

                # Table Column Headers
                pdf.set_fill_color(241, 245, 249)
                pdf.set_draw_color(203, 213, 225)
                pdf.set_text_color(15, 23, 42)
                pdf.set_font("Helvetica", "B", 7.5)

                pdf.cell(12, 6, sanitize_text("Class."), border=1, align="C", fill=True)
                pdf.cell(58, 6, sanitize_text("Nome do Candidato"), border=1, align="L", fill=True)
                pdf.cell(28, 6, sanitize_text("CPF"), border=1, align="C", fill=True)
                pdf.cell(48, 6, sanitize_text("Cargo"), border=1, align="L", fill=True)
                pdf.cell(14, 6, sanitize_text("Cota"), border=1, align="C", fill=True)
                pdf.cell(24, 6, sanitize_text("Início Vigência"), border=1, align="C", fill=True)
                pdf.cell(24, 6, sanitize_text("Fim Vigência"), border=1, align="C", fill=True)
                pdf.cell(44, 6, sanitize_text("Situação de Provimento"), border=1, align="C", fill=True)
                pdf.cell(25, 6, sanitize_text("Edital Chamada"), border=1, align="C", fill=True)
                pdf.ln()

                # Rows
                pdf.set_font("Helvetica", "", 7)
                for idx_c, cand in enumerate(gf["candidatos_filtrados"]):
                    fill = (idx_c % 2 == 1)
                    pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(30, 41, 59)

                    clas_str = f"#{cand.get('classificacao_original')}º"
                    nome_str = cand.get('nome_completo', '')[:35]
                    cpf_str = cand.get('cpf', '')
                    cargo_str = gf.get('cargo_nome', '')[:28]
                    cota_str = cand.get('tipo_cota', 'AMPLA')
                    dt_ini_str = str(cand.get('data_inicio_vigencia', '-'))
                    dt_fim_str = str(cand.get('data_fim_vigencia', '-'))
                    sit_str = cand.get('status_lbl', cand.get('status_atual', 'CONVOCADO'))
                    ed_str = cand.get('edital_convocacao', 'Edital Oficial')

                    pdf.cell(12, 5.2, sanitize_text(clas_str), border=1, align="C", fill=fill)
                    pdf.cell(58, 5.2, sanitize_text(nome_str), border=1, align="L", fill=fill)
                    pdf.cell(28, 5.2, sanitize_text(cpf_str), border=1, align="C", fill=fill)
                    pdf.cell(48, 5.2, sanitize_text(cargo_str), border=1, align="L", fill=fill)
                    pdf.cell(14, 5.2, sanitize_text(cota_str), border=1, align="C", fill=fill)
                    pdf.cell(24, 5.2, sanitize_text(dt_ini_str), border=1, align="C", fill=fill)
                    pdf.cell(24, 5.2, sanitize_text(dt_fim_str), border=1, align="C", fill=fill)

                    # Destacar status em cor
                    if cand.get('badge_tipo') == 'empossado':
                        pdf.set_text_color(5, 150, 105)
                    elif cand.get('badge_tipo') == 'desistente':
                        pdf.set_text_color(225, 29, 72)
                    elif cand.get('badge_tipo') == 'exonerado':
                        pdf.set_text_color(100, 116, 139)
                    else:
                        pdf.set_text_color(30, 64, 175)

                    pdf.cell(44, 5.2, sanitize_text(sit_str[:26]), border=1, align="C", fill=fill)
                    pdf.set_text_color(71, 85, 105)
                    pdf.cell(25, 5.2, sanitize_text(ed_str[:16]), border=1, align="C", fill=fill)
                    pdf.ln()

        # Footer
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(100, 116, 139)
        dt_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        hash_val = hashlib.sha256(f"{certame.numero_certame}_{tot_cands_filt}_{dt_str}".encode('utf-8')).hexdigest()
        pdf.cell(277, 4, sanitize_text(f"Documento gerado eletronicamente em {dt_str} pelo SIAP - Sistema Integrado de Auditoria de Pessoal | Chave de Autenticidade: {hash_val[:32]}..."), ln=True, align="C")
        pdf.cell(277, 4, sanitize_text("Relatório analítico conforme Instrução Normativa TCE-MT - Destinado à prestação de contas de encerramento do certame."), ln=True, align="C")

        pdf.output(caminho_arquivo)
        tamanho_bytes = os.path.getsize(caminho_arquivo)
        return {
            "caminho_arquivo": caminho_arquivo,
            "nome_arquivo": nome_arquivo,
            "tamanho_bytes": tamanho_bytes
        }
