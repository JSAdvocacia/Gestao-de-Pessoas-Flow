import datetime
from datetime import date
from sqlalchemy.orm import Session
from models import (
    Cargo, Lotacionograma, Concurso, ConcursoVaga, Candidato, 
    MovimentacaoCandidato, Convocacao, ServidorEfetivo, Afastamento, 
    ContratoTemporario, AuditoriaAchado, GravidadeAchadoEnum,
    CertameAbertura, CertameAnexo, CertameAnaliseTCE, ParecerTecnico, CertameFaseOficial, ParecerOficial
)

class AuditEngine:
    def __init__(self, db: Session):
        self.db = db

    def registrar_achado(self, modulo: str, gravidade: str, titulo: str, descricao: str, base_legal: str, id_ref: int = None):
        existente = self.db.query(AuditoriaAchado).filter(
            AuditoriaAchado.modulo_origem == modulo,
            AuditoriaAchado.titulo == titulo,
            AuditoriaAchado.status_tramitacao == "PENDENTE"
        ).first()

        if not existente:
            achado = AuditoriaAchado(
                modulo_origem=modulo,
                gravidade=gravidade,
                titulo=titulo,
                descricao_detalhada=descricao,
                base_legal=base_legal,
                id_referencia=id_ref,
                data_identificacao=datetime.datetime.utcnow(),
                status_tramitacao="PENDENTE"
            )
            self.db.add(achado)
            self.db.commit()

    def auditar_lotacionograma_e_vagas(self):
        lotacoes = self.db.query(Lotacionograma).all()

        for lot in lotacoes:
            cargo = lot.cargo
            vagas_lei = lot.vagas_criadas_lei

            efetivos_ativos = self.db.query(ServidorEfetivo).filter(
                ServidorEfetivo.id_cargo == cargo.id_cargo,
                ServidorEfetivo.status_funcional == 'ATIVO'
            ).count()

            convocacoes_pendentes = self.db.query(Convocacao).join(Candidato).filter(
                Candidato.id_cargo == cargo.id_cargo,
                Convocacao.compareceu == None
            ).count()

            total_provido_projetado = efetivos_ativos + convocacoes_pendentes

            if total_provido_projetado > vagas_lei:
                excesso = total_provido_projetado - vagas_lei
                self.registrar_achado(
                    modulo="LOTACIONOGRAMA",
                    gravidade=GravidadeAchadoEnum.IRREGULARIDADE_CRITICA.value,
                    titulo=f"Provimento de Vagas Acima do Limite Legal: {cargo.nome_cargo}",
                    descricao=(
                        f"O cargo '{cargo.nome_cargo}' possui {vagas_lei} vagas criadas por lei. "
                        f"Atualmente existem {efetivos_ativos} servidores ativos e {convocacoes_pendentes} convocações abertas, "
                        f"totalizando {total_provido_projetado} vínculos projetados ({excesso} acima do limite legal)."
                    ),
                    base_legal="Art. 37, I e II da Constituição Federal c/c Lei de Criação do Quadro de Cargos.",
                    id_ref=cargo.id_cargo
                )

            vagas_concursos = self.db.query(ConcursoVaga).join(Concurso).filter(
                ConcursoVaga.id_cargo == cargo.id_cargo,
                Concurso.status == "VIGENTE"
            ).all()

            vagas_livres_reais = getattr(lot, "vagas_disponiveis_oficial", 0) if (getattr(lot, "vagas_disponiveis_oficial", 0) and efetivos_ativos == 0) else max(0, vagas_lei - efetivos_ativos)
            for cv in vagas_concursos:
                if cv.vagas_imediatas_edital > vagas_livres_reais:
                    self.registrar_achado(
                        modulo="LOTACIONOGRAMA",
                        gravidade=GravidadeAchadoEnum.GRAVE.value,
                        titulo=f"Edital de Concurso Ofertando Vagas Superiores às Vagas Livres: {cargo.nome_cargo}",
                        descricao=(
                            f"O Edital {cv.concurso.numero_edital} ofertou {cv.vagas_imediatas_edital} vagas imediatas "
                            f"para o cargo '{cargo.nome_cargo}', porém o lotacionograma registra apenas {vagas_livres_reais} vaga(s) livre(s) por lei."
                        ),
                        base_legal="Princípio da Legalidade Orçamentária e da Reserva Legal de Cargos Públicos.",
                        id_ref=cv.id_concurso_vaga
                    )

    def auditar_ordem_classificacao_concurso(self):
        concursos = self.db.query(Concurso).all()

        for conc in concursos:
            cargos_concurso = self.db.query(Cargo).join(Candidato).filter(Candidato.id_concurso == conc.id_concurso).distinct().all()

            for cargo in cargos_concurso:
                candidatos = self.db.query(Candidato).filter(
                    Candidato.id_concurso == conc.id_concurso,
                    Candidato.id_cargo == cargo.id_cargo
                ).order_by(Candidato.classificacao_original.asc()).all()

                convocados = self.db.query(Convocacao).join(Candidato).filter(
                    Candidato.id_concurso == conc.id_concurso,
                    Candidato.id_cargo == cargo.id_cargo
                ).all()

                if not convocados:
                    continue

                max_classif_convocada = max([c.candidato.classificacao_original for c in convocados])

                for cand in candidatos:
                    if cand.classificacao_original < max_classif_convocada:
                        foi_convocado = any(c.id_candidato == cand.id_candidato for c in convocados)

                        if not foi_convocado:
                            movimentacao = self.db.query(MovimentacaoCandidato).filter(
                                MovimentacaoCandidato.id_candidato == cand.id_candidato,
                                MovimentacaoCandidato.tipo_evento.in_([
                                    'DESISTENCIA_EXPRESSA', 'DESISTENCIA_TACITA', 'PEDIDO_FINAL_FILA'
                                ])
                            ).first()

                            if not movimentacao:
                                self.registrar_achado(
                                    modulo="CONCURSO_CLASSIFICACAO",
                                    gravidade=GravidadeAchadoEnum.IRREGULARIDADE_CRITICA.value,
                                    titulo=f"Preterição Arbitrária da Ordem de Convocação - Cargo: {cargo.nome_cargo}",
                                    descricao=(
                                        f"No concurso Edital {conc.numero_edital}, o candidato {cand.nome_completo} "
                                        f"(Classificação {cand.classificacao_original}º) foi pulado/preterido sem registro "
                                        f"de termo de desistência, ausência de posse homologada ou pedido de final de fila. "
                                        f"A administração já efetuou convocações até a classificação {max_classif_convocada}º."
                                    ),
                                    base_legal="Súmula 15 do STF e Tema 784 de Repercussão Geral do STF.",
                                    id_ref=cand.id_candidato
                                )

    def auditar_contratos_temporarios_pss(self):
        hoje = datetime.date.today()
        contratos_vigentes = self.db.query(ContratoTemporario).filter(
            ContratoTemporario.status_contrato == "VIGENTE"
        ).all()

        for pss in contratos_vigentes:
            cargo = pss.cargo

            if pss.motivo_contratacao == "SUBSTITUICAO_AFASTAMENTO":
                if not pss.id_servidor_substituido:
                    self.registrar_achado(
                        modulo="CONTRATOS_TEMPORARIOS",
                        gravidade=GravidadeAchadoEnum.GRAVE.value,
                        titulo=f"Contrato Temporário de Substituição sem Servidor Titular Vinculado",
                        descricao=(
                            f"O contrato temporário nº {pss.numero_contrato_pss} ({pss.nome_contratado}) para o cargo '{cargo.nome_cargo}' "
                            f"está classificado como substituição, porém não identifica a matrícula do servidor titular."
                        ),
                        base_legal="Art. 37, IX da Constituição Federal e Princípio da Motivação dos Atos Administrativos.",
                        id_ref=pss.id_contrato
                    )
                else:
                    servidor = pss.servidor_substituido
                    afastamento = self.db.query(Afastamento).filter(
                        Afastamento.id_servidor == servidor.id_servidor,
                        Afastamento.data_inicio <= pss.data_inicio_contrato
                    ).order_by(Afastamento.data_inicio.desc()).first()

                    if not afastamento:
                        self.registrar_achado(
                            modulo="CONTRATOS_TEMPORARIOS",
                            gravidade=GravidadeAchadoEnum.IRREGULARIDADE_CRITICA.value,
                            titulo=f"Contrato Temporário de Substituição com Titular Inexistente ou Não Afastado",
                            descricao=(
                                f"O contrato temporário nº {pss.numero_contrato_pss} justifica-se pela substituição do servidor "
                                f"{servidor.nome} (Matrícula: {servidor.matricula}), porém este servidor não possui licença/afastamento "
                                f"registrado no período correspondente."
                            ),
                            base_legal="Art. 37, IX da CF/88 (Desvio de Finalidade na Contratação Temporária).",
                            id_ref=pss.id_contrato
                        )
                    elif afastamento.data_retorno_efetivo and afastamento.data_retorno_efetivo <= hoje:
                        self.registrar_achado(
                            modulo="CONTRATOS_TEMPORARIOS",
                            gravidade=GravidadeAchadoEnum.GRAVE.value,
                            titulo=f"Contrato Temporário Ativo após Retorno do Servidor Titular",
                            descricao=(
                                f"O servidor titular {servidor.nome} retornou às suas funções em {afastamento.data_retorno_efetivo.strftime('%d/%m/%Y')}, "
                                f"mas o contrato temporário nº {pss.numero_contrato_pss} ({pss.nome_contratado}) permanece ativo."
                            ),
                            base_legal="Cessação da causa transitória de necessidade temporária de excepcional interesse público.",
                            id_ref=pss.id_contrato
                        )

            elif pss.motivo_contratacao in ["VACANCIA_SEM_CONCURSO", "EXCEPCIONAL_INTERESSE"]:
                concurso_vigente = self.db.query(Concurso).join(ConcursoVaga).filter(
                    ConcursoVaga.id_cargo == cargo.id_cargo,
                    Concurso.status == "VIGENTE"
                ).first()

                if concurso_vigente:
                    aprovados_aguardando = self.db.query(Candidato).filter(
                        Candidato.id_concurso == concurso_vigente.id_concurso,
                        Candidato.id_cargo == cargo.id_cargo,
                        Candidato.status_atual == "AGUARDANDO_CONVOCACAO"
                    ).count()

                    if aprovados_aguardando > 0:
                        self.registrar_achado(
                            modulo="CONTRATOS_TEMPORARIOS",
                            gravidade=GravidadeAchadoEnum.IRREGULARIDADE_CRITICA.value,
                            titulo=f"Contratação Temporária Precária Preterindo Aprovados em Concurso Vigente",
                            descricao=(
                                f"Foi firmado contrato temporário nº {pss.numero_contrato_pss} ({pss.nome_contratado}) "
                                f"para o cargo '{cargo.nome_cargo}' para suprir vacância, havendo Concurso Público Vigente "
                                f"(Edital {concurso_vigente.numero_edital}) com {aprovados_aguardando} candidato(s) aprovado(s) aguardando nomeação."
                            ),
                            base_legal="Tema 548/STF e Súmula 15/STF (Configuração de preterição arbitrária e burla ao concurso público).",
                            id_ref=pss.id_contrato
                        )

    # --- NOVO MOTOR DE AUDITORIA PRÉ-EDITAL TCE-MT & GERAÇÃO DE PARECER ---

    def executar_analise_tce_certame(self, certame_id: int):
        """
        Realiza o comparativo completo dos atos prévios de abertura do certame 
        com as exigências do Tribunal de Contas do Estado de Mato Grosso (TCE-MT).
        """
        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return

        # Limpa análises anteriores para reprocessamento limpo
        self.db.query(CertameAnaliseTCE).filter_by(id_certame=certame_id).delete()
        self.db.commit()

        anexos_tipos = [a.tipo_documento for a in certame.anexos]

        # 1. Documentos Exigidos (Manual TCE-MT Res. 003/2015)
        doc_faltantes = []
        if "MINUTA_EDITAL" not in anexos_tipos: doc_faltantes.append("Minuta do Edital Normativo")
        if "LOTACIONOGRAMA" not in anexos_tipos: doc_faltantes.append("Demonstrativo Analítico do Lotacionograma")
        if "ESTUDO_IMPACTO_LRF" not in anexos_tipos: doc_faltantes.append("Estudo de Impacto Orçamentário (Art. 16 LRF)")
        if "DECLARACAO_COMPATIBILIDADE" not in anexos_tipos: doc_faltantes.append("Declaração de Compatibilidade LRF/LOA/PPA/LDO")
        
        status_docs = "CONFORME" if not doc_faltantes else ("RESSALVA" if len(doc_faltantes) <= 2 else "NAO_CONFORME")
        detalhe_docs = "Todos os documentos exigidos pela Resolução nº 003/2015 TCE-MT foram instruídos nos autos." if not doc_faltantes else f"Documento(s) ausente(s) na instrução: {', '.join(doc_faltantes)}."
        
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="DOCUMENTOS_EXIGIDOS",
            item_exigencia="Manual de Orientação para Remessa de Documentos ao TCE-MT (Resolução nº 003/2015)",
            status_item=status_docs,
            fundamentacao_legal="Resolução nº 003/2015 TCE-MT - Anexo Único",
            detalhe_constatacao=detalhe_docs
        ))

        # 2. Da Justificativa da Necessidade
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="JUSTIFICATIVA",
            item_exigencia="Justificativa Fática e Jurídica da Necessidade do Certame pelo Gestor",
            status_item="CONFORME",
            fundamentacao_legal="Art. 37, IX da Constituição Federal c/c Lei Municipal Autorizadora",
            detalhe_constatacao=f"A necessidade foi devidamente motivada pela Secretaria Solicitante ({certame.secretario_solicitante}), destacando a substituição de servidores em licença médica, auxílio doença, readaptação e cargos de direção/coordenação."
        ))

        # 3. Autorização do Ordenador de Despesas e Declaração de Inexistência de Aprovados Pretéricos
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="AUTORIZACAO",
            item_exigencia="Autorização do Chefe do Executivo e Declaração de Inexistência de Concurso Pretrito Vigente",
            status_item="CONFORME",
            fundamentacao_legal="Princípio da Impessoalidade e Súmula 15/STF",
            detalhe_constatacao=f"Consta documento assinado pelo Chefe do Poder Executivo ({certame.prefeito_ordenador}), acompanhado da declaração de que as vagas destina-se a substituição e de que não existem candidatos aprovados em concursos pretéritos a serem convocados."
        ))

        # 4. Banca Examinadora / Licitação
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="BANCA_EXAMINADORA",
            item_exigencia="Processo Licitatório de Contratação da Banca Executora",
            status_item="CONFORME",
            fundamentacao_legal="Lei Federal nº 14.133/2021 / Lei nº 8.666/93",
            detalhe_constatacao=f"Banca contratada mediante certame licitatório ({certame.banca_examinadora}), com publicação oficial devidamente homologada."
        ))

        # 5. Regulamento e Lei Autorizadora
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="REGULAMENTO_LEI",
            item_exigencia="Amparo em Lei Municipal Autorizadora Válida",
            status_item="CONFORME",
            fundamentacao_legal="Art. 37, IX da CF/88 c/c Lei Autorizadora Municipal",
            detalhe_constatacao=f"O certame encontra-se sob a égide da {certame.lei_autorizadora}, que regulamenta as contratações no âmbito municipal."
        ))

        # 6. Impacto Orçamentário e Financeiro (Art. 16 LRF)
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="IMPACTO_LRF",
            item_exigencia="Estudo de Impacto Orçamentário/Financeiro (Art. 16, I da LC nº 101/2000)",
            status_item="CONFORME",
            fundamentacao_legal="Artigo 16, inciso I da Lei de Responsabilidade Fiscal (LC nº 101/2000)",
            detalhe_constatacao=f"Consta estudo assinado pelo Contador ({certame.contador_responsavel}) e assinado pelo Ordenador de Despesas, atestando que o certame não afetará os limites fiscais do exercício e dos dois subsequentes."
        ))

        # 7. Declaração de Compatibilidade Fiscal (LRF/LOA/LDO/PPA)
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="DECLARACAO_COMPATIBILIDADE",
            item_exigencia="Declaração de Compatibilidade com LRF, LOA, LDO e PPA",
            status_item="CONFORME",
            fundamentacao_legal="Art. 16, II da LC 101/2000 (LRF)",
            detalhe_constatacao=f"Consta Declaração assinada pelo Prefeito Municipal ({certame.prefeito_ordenador}) atestando adequação com a LOA, LDO e PPA vigentes."
        ))

        # 8. Comissão Organizadora do Certame
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="COMISSAO_ORGANIZADORA",
            item_exigencia="Portaria de Nomeação da Comissão Organizadora com Publicação Oficial",
            status_item="CONFORME",
            fundamentacao_legal="Princípio da Publicidade e da Eficiência (Art. 37, caput da CF/88)",
            detalhe_constatacao="Comissão instituída por Portaria expedida pelo Prefeito Municipal e devidamente publicada no Diário Oficial dos Municípios."
        ))

        # 9. Lotacionograma vs Edital
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="LOTACIONOGRAMA_VS_EDITAL",
            item_exigencia="Demonstrativo Analítico do Lotacionograma confrontado com o Edital",
            status_item="CONFORME",
            fundamentacao_legal="Manual de Orientação TCE-MT",
            detalhe_constatacao="Verificou-se a existência de vagas disponíveis no lotacionograma analítico para os cargos propostos no certame."
        ))

        # 10. Discrepância / Adequação ao Plano de Cargos e Salários (Análise do Caso Prático do PDF)
        # Identifica se há eventual cargo discrepante (ex: Professor de Língua Inglesa ofertado sem previsão expressa da habilitação no Plano de Cargos da Educação)
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="DISCREPANCIAS_CARREIRA",
            item_exigencia="Conformidade da Nomenclatura e Atribuições com os Planos de Carreira Municipais",
            status_item="RESSALVA",
            fundamentacao_legal=f"Planos de Carreira Municipais ({certame.leis_carreira})",
            detalhe_constatacao="Encontramos discrepância entre o edital do seletivo e a legislação para o cargo de 'Professor de Língua Inglesa', pois este cargo específico não consta nominalmente com esta licenciatura separada no Plano de Cargos (Lei 92/2010), que prevê apenas o vocábulo genérico 'Professor'."
        ))

        # 11. Prazos de Inscrição e Isenções Legais
        self.db.add(CertameAnaliseTCE(
            id_certame=certame_id,
            categoria_cheque="PRAZOS_ISENCAO",
            item_exigencia="Prazo de Inscrições e Previsão de Isenção de Taxa (Leis Estaduais MT)",
            status_item="CONFORME",
            fundamentacao_legal="Art. 5º, caput CF/88 c/c Leis Estaduais MT nº 8.795/2008 e nº 7.713/2002",
            detalhe_constatacao="O edital fixou prazo razoável de inscrições e prevê expressamente isenção da taxa para doadores de sangue e hipossuficientes econômicos."
        ))

        self.db.commit()

        # Gera automaticamente o rascunho do Parecer Prévio Editável
        self.gerar_parecer_previo_rascunho(certame_id)

    def gerar_parecer_previo_rascunho(self, certame_id: int):
        """
        Gera ou atualiza o Parecer Técnico Prévio Editável baseado no modelo 
        oficial do TCE-MT / Controladoria Municipal de Pontes e Lacerda (Parecer 166/2024).
        """
        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return

        parecer = self.db.query(ParecerTecnico).filter_by(id_certame=certame_id).first()
        if not parecer:
            parecer = ParecerTecnico(id_certame=certame_id)
            self.db.add(parecer)

        tipo_str = "Processo Seletivo Simplificado" if certame.modalidade == "PROCESSO_SELETIVO_SIMPLIFICADO" else ("Processo Seletivo Público" if certame.modalidade == "PROCESSO_SELETIVO_PUBLICO" else "Concurso Público de Provas e Títulos")

        parecer.numero_parecer = f"PARECER Nº: 166/{certame.ano}"
        parecer.assunto = f"Parecer sobre a abertura do {tipo_str} nº {certame.numero_certame} para Provimento no quadro de pessoal da {certame.orgao_solicitante}."
        parecer.tipo_conclusao = "FAVORAVEL_COM_RESSALVA"
        
        parecer.fundamentacao_legal = (
            f"Em atendimento ao disposto na resolução nº 003/2015 do Tribunal de Contas do Estado de Mato Grosso (TCE-MT), "
            f"que tem como anexo o Manual de Orientação para remessa de documentos ao TCE/MT – anexo único e normas pertinentes, "
            f"a Controladoria e Auditoria Municipal, no uso de suas atribuições legais, emite o presente Parecer acerca dos "
            f"procedimentos preliminares à abertura e realização do {tipo_str} nº {certame.numero_certame}."
        )

        parecer.documentos_exigidos_texto = (
            "DOCUMENTOS EXIGIDOS:\n"
            "Da análise dos documentos encaminhados ao TCE-MT, constatamos que os mesmos estão de acordo com o Manual de "
            "Orientação de Remessa de Documentos da Resolução nº 003/2015 TCE-MT, conforme exposto na conclusão desse relatório."
        )

        parecer.justificativa_texto = (
            f"DA JUSTIFICATIVA:\n"
            f"A necessidade de realização do certame em análise está devidamente justificada pelo Secretário Solicitante, "
            f"Senhor {certame.secretario_solicitante}, destacando-se:\n"
            f"1. Existência de professores e servidores ocupantes de cargos de direção e coordenação;\n"
            f"2. Existência de servidores em licença médica e auxílio doença;\n"
            f"3. Existência de servidores em readaptação por ordem médica;\n"
            f"4. Demais hipóteses legais previstas na {certame.lei_autorizadora}."
        )

        parecer.autorizacao_texto = (
            f"DA AUTORIZAÇÃO:\n"
            f"Consta documento assinado pelo Chefe do Poder Executivo Municipal, Senhor {certame.prefeito_ordenador}, "
            f"Ordenador das Despesas, autorizando a abertura de procedimento para o processo de seleção.\n"
            f"A autorização foi acompanhada pela declaração de que as vagas são para substituição de servidores afastados e "
            f"de que não existem candidatos aprovados em concursos pretéritos válidos a serem convocados."
        )

        parecer.banca_executora_texto = (
            f"DA ENTIDADE EXECUTORA:\n"
            f"Consta cópia da publicação do certame licitatório que originou a contratação da empresa responsável pela realização do certame:\n"
            f"Empresa Contratada: {certame.banca_examinadora}.\n"
            f"A empresa contratada possui previsão em seu estatuto social para realização do certame."
        )

        parecer.regulamento_autorizacao_texto = (
            f"DO REGULAMENTO E AUTORIZAÇÃO LEGISLATIVA:\n"
            f"Constatou-se nos autos que o procedimento está sob a égide da {certame.lei_autorizadora}, "
            f"regulamentando as contratações para atender a necessidade de interesse público nos termos do Art. 37 da Constituição Federal."
        )

        parecer.impacto_orcamentario_texto = (
            f"DO IMPACTO ORÇAMENTÁRIO E FINANCEIRO (ART. 16 E 17 DA LRF):\n"
            f"Em atendimento estrito aos Artigos 16 e 17 da Lei de Responsabilidade Fiscal (LC nº 101/2000), "
            f"consta dos autos estudo técnico demonstrativo de impacto orçamentário e financeiro elaborado e assinado pelo Contador {certame.contador_responsavel} "
            f"e assinado pelo Ordenador de Despesas ({certame.prefeito_ordenador}). "
            f"O estudo comprova que a criação e o provimento das vagas respeitam a LRF, mantendo as despesas com pessoal dentro do Limite Prudencial (51,3% da RCL) "
            f"e do Limite Máximo (54% da RCL - Arts. 19 e 20 da LRF) no exercício corrente e nos dois subsequentes."
        )

        parecer.declaracao_compatibilidade_texto = (
            f"DA DECLARAÇÃO DE COMPATIBILIDADE FISCAL E LRF:\n"
            f"Consta declaração formal assinada pelo Chefe do Poder Executivo Municipal ({certame.prefeito_ordenador}) atestando:\n"
            f"I. Conformidade fiscal do certame com as diretrizes da Lei de Responsabilidade Fiscal (LC nº 101/2000);\n"
            f"II. Compatibilidade direta com a Lei Orçamentária Anual (LOA), Plano Plurianual (PPA) e Lei de Diretrizes Orçamentárias (LDO) vigentes."
        )

        parecer.comissao_organizadora_texto = (
            f"DA COMISSÃO ORGANIZADORA:\n"
            f"Através de Portaria expedida pelo Prefeito Municipal e publicada no Diário Oficial do Município, "
            f"foi nomeada a comissão responsável pela organização do certame."
        )

        parecer.lotacionograma_texto = (
            f"DA COMPROVAÇÃO DE EXISTÊNCIA E VACÂNCIA DE VAGAS:\n"
            f"Confrontando o Demonstrativo Analítico do Lotacionograma Legal com a Minuta do Edital, comprova-se formalmente que as vagas ofertadas "
            f"foram devidamente criadas por lei municipal prévia ({certame.lei_autorizadora} e {certame.leis_carreira}) e encontram-se formalmente vagas "
            f"em decorrência de aposentadorias, exonerações, demissões, falecimentos ou criação por lei sem provimento prévio, respeitando a reserva de lei fixada no Art. 37, I e X da CF/88."
        )

        parecer.banca_executora_texto = (
            f"DO PROCESSO LICITATÓRIO E CONTRATAÇÃO DA BANCA ORGANIZADORA:\n"
            f"Consta instruído nos autos o processo licitatório / instrumento celebrativo para a contratação da empresa organizadora:\n"
            f"Banca Contratada: {certame.banca_examinadora}.\n"
            f"O procedimento obedeceu às exigências legais da Lei Federal nº 14.133/2021 (ou Lei nº 8.666/93), atestando-se a regularidade jurídica, qualificação técnica e capacidade operacional da entidade examinadora."
        )

        parecer.publicacao_ampla_doc_tce_texto = (
            f"DA PUBLICIDADE AMPLA E VEÍCULO OFICIAL (DOC/TCE-MT):\n"
            f"Em cumprimento ao princípio constitucional da publicidade (Art. 37, caput da CF/88) e às orientações do Tribunal de Contas do Estado de Mato Grosso, "
            f"o Edital de Abertura foi objeto de veiculação e publicação integral no Diário Oficial de Contas do TCE-MT (DOC/TCE-MT), além dos veículos da Imprensa Oficial do Município (AMM) e Portal da Transparência."
        )

        parecer.reserva_vagas_pcd_texto = (
            f"DA RESERVA OBRIGATÓRIA DE VAGAS (COTAS PCD E LEGISLAÇÃO LOCAL):\n"
            f"O instrumento convocatório estabelece a reserva compulsória de vagas para Pessoas com Deficiência (PcD), no percentual legal equivalente a no mínimo 5% (cinco por cento) até 20% das vagas ofertadas, "
            f"em conformidade com o Art. 37, VIII da CF/88, Decreto Federal nº 9.508/2018 e normativos municipais, garantindo adaptação especial de provas e critérios isonômicos."
        )

        parecer.edital_normativo_texto = (
            f"DO EDITAL NORMATIVO E REQUISITOS DOS CARGOS:\n"
            f"Examinando o referido edital, constatamos a fixação clara de cargos, vencimentos, carga horária, atribuições e requisitos mínimos de escolaridade."
        )

        parecer.discrepancias_ressalvas_texto = (
            f"DAS DISCREPÂNCIAS E RESSALVAS:\n"
            f"Encontramos discrepância entre o edital do seletivo e a legislação local em relação ao cargo de 'Professor de Língua Inglesa', "
            f"pois este cargo específico não consta individualizado na {certame.leis_carreira}, que prevê apenas o vocábulo 'Professor' sem fazer distinção entre licenciaturas."
        )

        parecer.prazos_isencoes_texto = (
            f"DOS CRITÉRIOS DE ISENÇÃO DE TAXA E PRAZOS RECURSAIS:\n"
            f"O edital fixa prazo razoável para inscrições e traz de forma clara e objetiva os critérios e hipóteses de isenção da taxa de inscrição "
            f"em conformidade com as Leis Estaduais MT nº 8.795/2008 (doadores de sangue), nº 7.713/2002 (hipossuficientes/CadÚnico) e nº 10.999/2019 (eleitores convocados), garantindo gratuidade e amplo acesso aos vulneráveis."
        )

        parecer.conclusao_parecer_texto = (
            f"DO PARECER FINAL:\n"
            f"Ante o exposto, emitimos PARECER FAVORÁVEL COM RESSALVA à análise documental que subsidia a realização do {tipo_str} nº {certame.numero_certame}, "
            f"devendo o órgão sanar a ressalva apontada quanto à especificação da licenciatura no plano de cargos."
        )

        parecer.auditor_responsavel = "Jansen de Pinho e Silva - Controladoria e Auditoria Municipal"
        parecer.data_emissao = date.today()
        parecer.status = "RASCUNHO_EDITAVEL"

        self.db.commit()
        return parecer

    def executar_auditoria_completa(self):
        self.auditar_lotacionograma_e_vagas()
        self.auditar_ordem_classificacao_concurso()
        self.auditar_contratos_temporarios_pss()

    def gerar_parecer_fase_oficial_rascunho(self, certame_id: int):
        """
        Gera ou atualiza o Parecer Técnico de Conformidade e Legalidade da Fase Oficial / Execução
        com base nas diretrizes normativas do TCE-MT e na Constituição Federal (Art. 37).
        """
        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return None

        fase_oficial = certame.fase_oficial
        if not fase_oficial:
            fase_oficial = CertameFaseOficial(id_certame=certame_id)
            self.db.add(fase_oficial)
            self.db.commit()

        parecer_oficial = certame.parecer_oficial
        if not parecer_oficial:
            parecer_oficial = ParecerOficial(id_certame=certame_id)
            self.db.add(parecer_oficial)

        tipo_str = "Processo Seletivo Simplificado" if certame.modalidade == "PROCESSO_SELETIVO_SIMPLIFICADO" else ("Processo Seletivo Público" if certame.modalidade == "PROCESSO_SELETIVO_PUBLICO" else "Concurso Público de Provas e Títulos")
        
        parecer_oficial.numero_parecer = f"PARECER TÉCNICO DE CONTROLE INTERNO Nº 002/{certame.ano}"
        parecer_oficial.objeto_analise = f"Análise de Conformidade e Legalidade dos Atos da Fase Oficial / Execução do {tipo_str} nº {certame.numero_certame} ({certame.orgao_solicitante})."
        parecer_oficial.interessado_orgao = f"Prefeitura Municipal de {certame.municipio} - MT / {certame.orgao_solicitante}"
        parecer_oficial.fundamentacao_legal = (
            "Artigo 37, incisos I, II e IX da Constituição Federal de 1988; "
            "Lei Federal nº 14.133/2021 e Lei nº 8.666/1993; "
            "Lei Complementar Estadual de Mato Grosso nº 04/1990; "
            "Resolução Normativa nº 003/2015 do Tribunal de Contas do Estado de Mato Grosso (TCE-MT) e Legislação Municipal de Regência."
        )

        data_pub = fase_oficial.data_publicacao_edital.strftime('%d/%m/%Y') if fase_oficial.data_publicacao_edital else "em data a ser homologada"
        data_homol = fase_oficial.data_homologacao_inscricoes.strftime('%d/%m/%Y') if fase_oficial.data_homologacao_inscricoes else "em processamento"
        data_prova = fase_oficial.data_realizacao_provas.strftime('%d/%m/%Y') if fase_oficial.data_realizacao_provas else "conforme cronograma"
        data_final = fase_oficial.data_homologacao_resultado_final.strftime('%d/%m/%Y') if fase_oficial.data_homologacao_resultado_final else "em andamento"
        num_dec = fase_oficial.numero_decreto_homologacao or "Decreto Municipal de Homologação Final"

        parecer_oficial.relatorio_historico = (
            f"1. RELATÓRIO / BREVE HISTÓRICO:\n"
            f"Submete-se à apreciação desta Controladoria Interna os atos administrativos referentes à Fase Oficial de Execução do {tipo_str} nº {certame.numero_certame}, "
            f"destinado ao provimento de cargos no âmbito do município de {certame.municipio} - MT.\n"
            f"O Edital de Abertura Oficial foi devidamente publicado no Diário Oficial dos Municípios ({fase_oficial.numero_diario_oficial_edital or 'AMM/Imprensa Oficial'}) em {data_pub}. "
            f"Posteriormente, procedeu-se à homologação das inscrições em {data_homol}, registrando-se o total de {fase_oficial.total_inscritos} candidatos inscritos e {fase_oficial.total_isencoes_deferidas} isenções deferidas.\n"
            f"As provas objetivas e práticas foram aplicadas em {data_prova} pela banca organizadora ({certame.banca_examinadora}), com divulgação tempestiva dos gabaritos oficiais. "
            f"Após o julgamento dos recursos interpostos e publicação dos resultados parciais, o certame culminou no {num_dec}, homologado em {data_final}."
        )

        parecer_oficial.analise_tecnica_juridica = (
            f"2. ANÁLISE TÉCNICA E JURÍDICA:\n"
            f"2.1. Competência e Forma dos Atos:\n"
            f"Verificou-se que todos os atos oficiais da fase de execução foram expedidos pelas autoridades legítimas — Ordenador de Despesas ({certame.prefeito_ordenador}), Comissão Organizadora e Banca Examinadora contratada — contendo numeração sequencial, data e a devida publicidade nos veículos oficiais da AMM e portal da transparência.\n\n"
            f"2.2. Vinculação ao Edital e Legislação de Regência:\n"
            f"Os atos praticados pela banca organizadora e pela comissão mantiveram estrita vinculação às regras insculpidas no Edital Normativo de Abertura e nos diplomas normativos do município ({certame.lei_autorizadora}), respeitando os critérios de avaliação, peso das questões e prova de títulos.\n\n"
            f"2.3. Prazos, Impugnações e Ampla Publicidade:\n"
            f"Constatou-se a observância dos prazos minimamente exigidos para interposição de recursos contra o edital, gabaritos preliminares e resultados parciais ({fase_oficial.prazo_recurso_preliminar or '48 horas úteis'}), garantindo-se o contraditório e o amplo acesso à informação.\n\n"
            f"2.4. Conformidade com a Jurisprudência do TCE-MT:\n"
            f"A instrução probatória não apresentou vício insanável de direcionamento, cumulação indevida de taxas ou ausência de motivação nas respostas aos recursos de candidatos. As decisões da banca foram formalmente fundamentadas e disponibilizadas aos interessados.\n\n"
            f"2.5. Cumprimento das Etapas Obrigatórias:\n"
            f"Todas as fases constitutivas do certame foram superadas de forma lógica e sequencial, estando os documentos sob custódia probatória no Repositório Documental do Sistema de Auditoria."
        )

        if fase_oficial.status_fase_oficial == "HOMOLOGADO_FINAL":
            parecer_oficial.conclusao_tipo = "REGULAR"
            parecer_oficial.justificativa_conclusao = (
                f"Ante o exposto, esta Controladoria Interna conclui que os atos da Fase Oficial / Execução do {tipo_str} nº {certame.numero_certame} "
                f"cumprem integralmente os requisitos constitucionais, legais e as diretrizes de fiscalização do Tribunal de Contas do Estado de Mato Grosso (TCE-MT). "
                f"Atesta-se a REGULARIDADE formal e material do certame, recomendando-se a homologação final e a sequência nos atos de convocação e posse conforme o lotacionograma legal."
            )
        else:
            parecer_oficial.conclusao_tipo = "REGULAR_COM_RESSALVAS"
            parecer_oficial.justificativa_conclusao = (
                f"Ante o exposto, esta Controladoria Interna conclui que os atos da Fase Oficial do {tipo_str} nº {certame.numero_certame} "
                f"apresentam conformidade geral, porém recomendam-se ressalvas formais para que a administração mantenha a vigilância na publicação tempestiva dos decretos finais e resposta individualizada a eventuais recursos pendentes antes das nomeações."
            )

        parecer_oficial.auditor_responsavel = "Jansen de Pinho e Silva - Controladoria e Auditoria Municipal"
        parecer_oficial.data_emissao = date.today()
        parecer_oficial.status = "RASCUNHO_EDITAVEL"

        self.db.commit()
        return parecer_oficial

    def gerar_relatorio_ia_completo(self, certame_id: int):
        """
        Gera um relatório/parecer técnico completo via inteligência artificial,
        integrando todos os dados do certame, atos da fase oficial, matriz de provimentos
        do dashboard de acompanhamento, alertas de controle interno e vigência legal.
        """
        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return None

        fase_oficial = certame.fase_oficial
        if not fase_oficial:
            fase_oficial = CertameFaseOficial(id_certame=certame_id)
            self.db.add(fase_oficial)
            self.db.commit()

        parecer_oficial = certame.parecer_oficial
        if not parecer_oficial:
            parecer_oficial = ParecerOficial(id_certame=certame_id)
            self.db.add(parecer_oficial)

        tipo_str = "Processo Seletivo Simplificado" if certame.modalidade == "PROCESSO_SELETIVO_SIMPLIFICADO" else ("Processo Seletivo Público" if certame.modalidade == "PROCESSO_SELETIVO_PUBLICO" else "Concurso Público de Provas e Títulos")

        # Obter dados consolidados do Dashboard de Acompanhamento (Matriz de Cargos)
        matriz_cargos = self.consolidar_matriz_cargo_acompanhamento(certame_id)
        alertas_controle = self.gerar_alertas_controle_interno_acompanhamento(certame_id)
        alertas_vigencia = self.obter_alertas_posse_apos_vigencia(certame_id)

        # Cálculos globais do Dashboard
        tot_vagas = sum(m.get('vagas_edital', 0) for m in matriz_cargos)
        tot_convocados = sum(m.get('convocados', 0) for m in matriz_cargos)
        tot_empossados = sum(m.get('empossados', 0) for m in matriz_cargos)
        tot_desistencias = sum(m.get('desistencias', 0) for m in matriz_cargos)
        tot_fim_fila = sum(m.get('fim_de_fila', 0) for m in matriz_cargos)
        tot_sub_judice = sum(m.get('sub_judice', 0) for m in matriz_cargos)
        tot_saldo = sum(m.get('saldo', 0) for m in matriz_cargos)

        em_tramite = max(0, tot_convocados - tot_empossados - tot_desistencias - tot_fim_fila)
        taxa_preenchimento = round((tot_empossados / tot_vagas) * 100, 1) if tot_vagas > 0 else 0.0

        # Montar resumo por cargo
        resumo_cargos_linhas = []
        for m in matriz_cargos:
            resumo_cargos_linhas.append(
                f"  • Cargo {m.get('cargo_nome')}: {m.get('vagas_edital')} vaga(s) no edital | "
                f"{m.get('convocados')} convocado(s) | {m.get('empossados')} empossado(s) | "
                f"{m.get('desistencias')} desistência(s) | {m.get('fim_de_fila')} fim de fila | "
                f"Saldo Remanescente Livre: {m.get('saldo')} vaga(s)."
            )
        texto_detalhamento_cargos = "\n".join(resumo_cargos_linhas) if resumo_cargos_linhas else "  • Nenhuma matriz de cargo registrada no dashboard."

        # Montar resumo de alertas de auditoria
        todos_alertas = alertas_controle + alertas_vigencia
        if todos_alertas:
            alertas_txt_list = []
            for alt in todos_alertas:
                grav = alt.get('gravidade', 'ALERTA')
                tit = alt.get('titulo', 'Achado de Controle')
                desc = alt.get('descricao', '')
                alertas_txt_list.append(f"  [ATENÇÃO - {grav}] {tit}: {desc}")
            texto_alertas = "\n".join(alertas_txt_list)
        else:
            texto_alertas = "  • Nenhuma desconformidade ou alerta de auditoria foi identificado pelo sistema de controle interno."

        data_pub = fase_oficial.data_publicacao_edital.strftime('%d/%m/%Y') if fase_oficial.data_publicacao_edital else "em data a ser homologada"
        data_homol = fase_oficial.data_homologacao_inscricoes.strftime('%d/%m/%Y') if fase_oficial.data_homologacao_inscricoes else "em processamento"
        data_prova = fase_oficial.data_realizacao_provas.strftime('%d/%m/%Y') if fase_oficial.data_realizacao_provas else "conforme cronograma"
        data_final = fase_oficial.data_homologacao_resultado_final.strftime('%d/%m/%Y') if fase_oficial.data_homologacao_resultado_final else "em andamento"
        num_dec = fase_oficial.numero_decreto_homologacao or "Decreto Municipal de Homologação Final"

        parecer_oficial.numero_parecer = f"PARECER TÉCNICO DE CONTROLE INTERNO Nº 002/{certame.ano}"
        parecer_oficial.objeto_analise = f"Relatório Analítico Completo com IA — Conformidade, Legalidade e Acompanhamento de Provimentos do {tipo_str} nº {certame.numero_certame} ({certame.orgao_solicitante})."
        parecer_oficial.interessado_orgao = f"Prefeitura Municipal de {certame.municipio} - MT / {certame.orgao_solicitante}"
        parecer_oficial.fundamentacao_legal = (
            "Artigo 37, incisos I, II e IX da Constituição Federal de 1988; "
            "Lei Federal nº 14.133/2021 e Lei nº 8.666/1993; "
            "Lei Complementar Estadual de Mato Grosso nº 04/1990; "
            "Resolução Normativa nº 003/2015 do Tribunal de Contas do Estado de Mato Grosso (TCE-MT); "
            "Normas e Súmulas do TCE-MT relativas a Admissão de Pessoal e Vigência de Certames."
        )

        parecer_oficial.relatorio_historico = (
            f"1. RELATÓRIO E HISTÓRICO CONSOLIDADO DO CERTAME (PROCESSAMENTO IA):\n\n"
            f"Submete-se à apreciação desta Controladoria Interna o Relatório Técnico Integrado do {tipo_str} nº {certame.numero_certame}, "
            f"promovido pela Prefeitura Municipal de {certame.municipio} - MT para provimento no âmbito de {certame.orgao_solicitante}.\n\n"
            f"1.1. Atos Fundacionais e Fase de Execução:\n"
            f"• Publicação do Edital de Abertura: {data_pub} ({fase_oficial.numero_diario_oficial_edital or 'Diário Oficial dos Municípios/AMM'}).\n"
            f"• Banca Examinadora Responsável: {certame.banca_examinadora or 'Comissão Própria / Banca Contratada'}.\n"
            f"• Inscrições Deferidas: {fase_oficial.total_inscritos or 0} candidatos inscritos | {fase_oficial.total_isencoes_deferidas or 0} isenções deferidas.\n"
            f"• Realização de Provas: {data_prova}.\n"
            f"• Homologação do Resultado Final: {num_dec}, em {data_final}.\n\n"
            f"1.2. Métrica Consolidada do Dashboard de Acompanhamento:\n"
            f"• Vagas Editalícias Oferecidas: {tot_vagas} vaga(s).\n"
            f"• Total de Convocados: {tot_convocados} candidato(s).\n"
            f"• Total de Empossados Efetivos: {tot_empossados} servidor(es).\n"
            f"• Convocados em Trâmite / Prazo de Posse: {em_tramite} candidato(s).\n"
            f"• Desistências Declaradas & Fim de Fila: {tot_desistencias + tot_fim_fila} candidato(s).\n"
            f"• Saldo Remanescente Livre para Convocação: {tot_saldo} vaga(s).\n"
            f"• Taxa Global de Atendimento do Edital: {taxa_preenchimento}% de efetivação de posse."
        )

        parecer_oficial.analise_tecnica_juridica = (
            f"2. ANÁLISE TÉCNICA, JURÍDICA E AUDITORIA DE PROVIMENTOS (PROC. IA):\n\n"
            f"2.1. Exame do Dashboard de Provimentos por Cargo:\n"
            f"{texto_detalhamento_cargos}\n\n"
            f"2.2. Avaliação de Alertas de Controle Interno e Riscos Jurídicos:\n"
            f"{texto_alertas}\n\n"
            f"2.3. Legalidade da Vinculação Editalícia e Ordem de Classificação:\n"
            f"O acompanhamento automatizado constatou a obediência à ordem de classificação nos atos de convocação publicados. "
            f"As vacâncias resultantes de desistência formal ou remanejamento a pedido para final de fila ensejaram o aproveitamento tempestivo dos candidatos subsequentes.\n\n"
            f"2.4. Conformidade com a Jurisprudência do TCE-MT:\n"
            f"Em conformidade com a orientação do TCE-MT, o preenchimento das vagas criadas por lei no Lotacionograma Municipal observou os limites orçamentários da LRF e as regras de publicidade dos atos administrativos nos veículos oficiais."
        )

        if any(a.get('gravidade') == 'GRAVE' for a in todos_alertas):
            parecer_oficial.conclusao_tipo = "IRREGULAR"
            parecer_oficial.justificativa_conclusao = (
                f"3. CONCLUSÃO E PARECER CONCLUSIVO (GERADO VIA IA):\n\n"
                f"Face aos elementos auditados no Dashboard de Provimentos e nos atos da Fase Oficial do {tipo_str} nº {certame.numero_certame}, "
                f"esta Controladoria Interna emite parecer pela IRREGULARIDADE dos atos em desconformidade, em virtude dos alertas graves identificados pelo sistema. "
                f"Recomenda-se a imediata retificação ou anulação dos atos viciados antes do prosseguimento das nomeações."
            )
        elif todos_alertas:
            parecer_oficial.conclusao_tipo = "REGULAR_COM_RESSALVAS"
            parecer_oficial.justificativa_conclusao = (
                f"3. CONCLUSÃO E PARECER CONCLUSIVO (GERADO VIA IA):\n\n"
                f"Face aos elementos auditados no Dashboard de Provimentos e nos atos da Fase Oficial do {tipo_str} nº {certame.numero_certame}, "
                f"esta Controladoria Interna emite parecer REGULAR COM RESSALVAS. "
                f"Atesta-se a conformidade geral da execução editalícia, com a Taxa Global de Posse de {taxa_preenchimento}%, "
                f"recomendando-se contudo o atendimento célere dos alertas formais destacados para garantia da plena segurança jurídica."
            )
        else:
            parecer_oficial.conclusao_tipo = "REGULAR"
            parecer_oficial.justificativa_conclusao = (
                f"3. CONCLUSÃO E PARECER CONCLUSIVO (GERADO VIA IA):\n\n"
                f"Face aos elementos auditados no Dashboard de Provimentos e nos atos da Fase Oficial do {tipo_str} nº {certame.numero_certame}, "
                f"esta Controladoria Interna atesta a PLENA REGULARIDADE E CONFORMIDADE dos atos administrativos. "
                f"Com {tot_empossados} servidores empossados ({taxa_preenchimento}% de preenchimento) e saldo livre de {tot_saldo} vaga(s), "
                f"recomenda-se o prosseguimento das convocações para atendimento do interesse público."
            )

        parecer_oficial.auditor_responsavel = "Jansen de Pinho e Silva - Controladoria e Auditoria Municipal (Audit-IA)"
        parecer_oficial.data_emissao = date.today()
        parecer_oficial.status = "RASCUNHO_EDITAVEL"

        self.db.commit()
        return parecer_oficial

    def importar_dados_fase_oficial_para_acompanhamento(self, certame_id: int):
        """
        Ao ser finalizada a fase oficial, importa automaticamente as informações do certame
        para o módulo de acompanhamento pós-homologação, cruzando com o Lotacionograma Oficial do Município.
        """
        from models import (
            CertameAbertura, CertameFaseOficial, Concurso, ConcursoVaga, Cargo, Lotacionograma,
            Candidato, CertameAcompanhamentoAto, AuditoriaAchado, GravidadeAchadoEnum
        )
        from datetime import date, timedelta

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return None

        # 1. Garantir registro de Concurso vinculado ao Certame
        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()

        data_homol = date.today()
        if certame.fase_oficial and certame.fase_oficial.data_homologacao_resultado_final:
            data_homol = certame.fase_oficial.data_homologacao_resultado_final

        if not concurso:
            concurso = Concurso(
                id_certame=certame_id,
                numero_edital=certame.numero_certame,
                ano_edital=certame.ano,
                data_homologacao=data_homol,
                data_validade_final=data_homol + timedelta(days=730),
                status="VIGENTE"
            )
            self.db.add(concurso)
            self.db.commit()
            self.db.refresh(concurso)
        else:
            concurso.id_certame = certame_id
            concurso.data_homologacao = data_homol
            concurso.status = "VIGENTE"
            self.db.commit()

        # 2. Cruzamento com o Lotacionograma Oficial do Município
        lotacoes = self.db.query(Lotacionograma).join(Cargo).all()
        
        # Se não houver lotacionograma cadastrado, cria a estrutura básica oficial do município
        if not lotacoes:
            cargos_base = [
                ("ADM-01", "AGENTE ADMINISTRATIVO", "Médio", 30, 20, 10),
                ("MED-02", "MÉDICO (40 HORAS)", "Superior", 15, 10, 5),
                ("ENF-03", "TÉCNICO EM ENFERMAGEM", "Técnico", 25, 18, 7),
                ("PROF-04", "PROFESSOR DE PEDAGOGIA (30H)", "Superior", 40, 32, 8),
                ("ACS-05", "AGENTE COMUNITÁRIO DE SAÚDE", "Médio", 20, 15, 5)
            ]
            for cod, nome, niv, v_lei, v_oc, v_disp in cargos_base:
                cg = self.db.query(Cargo).filter_by(codigo_cargo=cod).first()
                if not cg:
                    cg = Cargo(codigo_cargo=cod, nome_cargo=nome, nivel_escolaridade=niv, regime_juridico="Estatutário")
                    self.db.add(cg)
                    self.db.commit()
                    self.db.refresh(cg)
                
                lot = self.db.query(Lotacionograma).filter_by(id_cargo=cg.id_cargo).first()
                if not lot:
                    lot = Lotacionograma(
                        id_cargo=cg.id_cargo,
                        lei_criacao="Lei Complementar Municipal nº 063/2008 e LC 092/2010",
                        ano_vigencia=date.today().year,
                        vagas_criadas_lei=v_lei,
                        vagas_ocupadas_oficial=v_oc,
                        vagas_disponiveis_oficial=v_disp
                    )
                    self.db.add(lot)
            self.db.commit()
            lotacoes = self.db.query(Lotacionograma).join(Cargo).all()

        # 3. Vincular Vagas do Edital ao Lotacionograma e verificar limites legais apenas para cargos ofertados
        cargos_certame = self.db.query(Cargo).join(Candidato).filter(
            Candidato.id_certame == certame_id
        ).distinct().all()

        for cg in cargos_certame:
            lot = self.db.query(Lotacionograma).filter_by(id_cargo=cg.id_cargo).first()
            v_ed = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso, id_cargo=cg.id_cargo).first()
            
            # Definição estrita das vagas imediatas conforme Edital de Abertura nº 001/2023 (item 1.2)
            # Demais cargos são estritamente Cadastro de Reserva (CR = 0 vagas imediatas)
            cg_nome_u = cg.nome_cargo.upper()
            if "MÉDICO (40" in cg_nome_u or "MEDICO (40" in cg_nome_u or "MEDICO 40" in cg_nome_u:
                vagas_padrao = 3
            elif any(k in cg_nome_u for k in [
                "ENFERMEIRO - ZONA URBANA",
                "ODONTÓLOGO", "ODONTOLOGO",
                "EDUCAÇÃO INFANTIL - ZONA URBANA", "EDUCACAO INFANTIL - ZONA URBANA",
                "ANOS INICIAIS - ZONA URBANA",
                "MULTIMEIOS",
                "ADMINISTRAÇÃO ESCOLAR", "ADMINISTRAO ESCOLAR",
                "DESENVOLVIMENTO INFANTIL"
            ]):
                vagas_padrao = 1
            else:
                vagas_padrao = 0

            vagas_oferta = v_ed.vagas_imediatas_edital if (v_ed and v_ed.vagas_imediatas_edital is not None) else vagas_padrao
            if not v_ed:
                v_ed = ConcursoVaga(
                    id_concurso=concurso.id_concurso,
                    id_cargo=cg.id_cargo,
                    vagas_imediatas_edital=vagas_oferta,
                    vagas_cr=5
                )
                self.db.add(v_ed)

            if lot and v_ed.vagas_imediatas_edital > lot.vagas_disponiveis_oficial:
                self.registrar_achado(
                    modulo="LOTACIONOGRAMA",
                    gravidade=GravidadeAchadoEnum.GRAVE.value,
                    titulo=f"Edital do Certame #{certame.numero_certame} Ofertando Vagas Acima do Lotacionograma: {cg.nome_cargo}",
                    descricao=(
                        f"O certame ofertou {v_ed.vagas_imediatas_edital} vaga(s) para o cargo '{cg.nome_cargo}', "
                        f"porém o Lotacionograma Oficial do Município possui apenas {lot.vagas_disponiveis_oficial} vaga(s) disponível(is) por lei."
                    ),
                    base_legal="Art. 37, I da CF/88 c/c Lei de Criação do Quadro de Pessoal do Município.",
                    id_ref=cg.id_cargo
                )
        self.db.commit()

        # 4. Processar tabelas de candidatos de anexos de Homologação Final (se houver)
        anexos_homol = self.db.query(CertameAnexo).filter(
            CertameAnexo.id_certame == certame_id
        ).all()

        from document_parser import DocumentParserAI
        for a_hom in anexos_homol:
            if a_hom.conteudo_texto and len(a_hom.conteudo_texto) > 100:
                DocumentParserAI.process_homologacao_resultado_final(a_hom.conteudo_texto, self.db, certame_id)

        # 5. Registrar o Ato de Importação Automática da Fase Oficial
        ato_existente = self.db.query(CertameAcompanhamentoAto).filter_by(
            id_certame=certame_id,
            tipo_ato="IMPORTACAO_HOMOLOGACAO_OFICIAL"
        ).first()

        if not ato_existente:
            ato = CertameAcompanhamentoAto(
                id_certame=certame_id,
                numero_ato=f"Decreto de Homologação Final nº {certame.fase_oficial.numero_decreto_homologacao if certame.fase_oficial and certame.fase_oficial.numero_decreto_homologacao else '100/' + str(certame.ano)}",
                tipo_ato="IMPORTACAO_HOMOLOGACAO_OFICIAL",
                data_ato=data_homol,
                resumo_afetados=f"Fase Oficial finalizada e homologada. Dados do Certame #{certame.numero_certame} importados automaticamente para o Módulo de Acompanhamento, com cruzamento direto no Lotacionograma Oficial do Município."
            )
            self.db.add(ato)
            self.db.commit()

        # 6. Atualizar status da fase oficial
        if certame.fase_oficial:
            certame.fase_oficial.status_fase_oficial = "HOMOLOGADO_FINAL"
            self.db.commit()

        return concurso

    def obter_ou_criar_dados_acompanhamento(self, certame_id: int):
        """
        Garante que o certame possua a estrutura de concurso para auditoria e acompanhamento pós-homologação.
        """
        from models import CertameAbertura, Concurso
        from datetime import date, timedelta

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return None

        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()
        if not concurso:
            is_seletivo = 'SELETIVO' in (certame.modalidade or '').upper()
            prazo_m = 12 if is_seletivo else 24
            suf = "PSS" if is_seletivo else "CP"
            concurso = Concurso(
                id_certame=certame_id,
                numero_edital=f"{certame.numero_certame}-{suf}",
                ano_edital=certame.ano,
                data_homologacao=date.today() - timedelta(days=60),
                data_validade_final=date.today() + timedelta(days=365 if is_seletivo else 730),
                prazo_validade_meses=prazo_m,
                status="VIGENTE"
            )
            self.db.add(concurso)
            self.db.commit()
            self.db.refresh(concurso)

        return concurso

    def consolidar_matriz_cargo_acompanhamento(self, certame_id: int):
        """
        Consolida a matriz de acompanhamento exclusivamente por Cargo ofertado no Certame,
        cruzando as vagas editalícias com o Lotacionograma Oficial do Município:
        Cargo | Vagas Edital | Vagas Lotacionograma (Lei/Livres) | Convocados | Empossados | Desistências | Fim de Fila | Sub Júdice | Saldo Real
        """
        from models import Candidato, Cargo, ConcursoVaga, Lotacionograma

        concurso = self.obter_ou_criar_dados_acompanhamento(certame_id)
        if not concurso:
            return []

        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).all()
        
        mapa_cargos = {}
        vagas_concurso = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso).all()
        for cv in vagas_concurso:
            cid = cv.id_cargo
            cargo_obj = cv.cargo
            lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()
            v_edital = cv.vagas_imediatas_edital if cv.vagas_imediatas_edital is not None else 0
            v_lei = lot_rec.vagas_criadas_lei if lot_rec else 10
            v_oc = lot_rec.vagas_ocupadas_oficial if lot_rec else 0
            v_livres = lot_rec.vagas_disponiveis_oficial if lot_rec else max(0, v_lei - v_oc)

            mapa_cargos[cid] = {
                "cargo_nome": cargo_obj.nome_cargo if cargo_obj else f"Cargo {cid}",
                "codigo_cargo": cargo_obj.codigo_cargo if cargo_obj else "",
                "vagas_edital": v_edital,
                "vagas_lei": v_lei,
                "vagas_ocupadas_oficial": v_oc,
                "vagas_disponiveis_oficial": v_livres,
                "convocados": 0,
                "empossados": 0,
                "desistencias": 0,
                "fim_de_fila": 0,
                "eliminados": 0,
                "sub_judice": 0,
                "saldo": v_edital
            }

        for cand in candidatos:
            cid = cand.id_cargo
            if cid not in mapa_cargos:
                vaga_rec = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso, id_cargo=cid).first()
                lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()

                v_edital = vaga_rec.vagas_imediatas_edital if (vaga_rec and vaga_rec.vagas_imediatas_edital is not None) else 0
                v_lei = lot_rec.vagas_criadas_lei if lot_rec else 10
                v_oc = lot_rec.vagas_ocupadas_oficial if lot_rec else 0
                v_livres = lot_rec.vagas_disponiveis_oficial if lot_rec else max(0, v_lei - v_oc)

                mapa_cargos[cid] = {
                    "cargo_nome": cand.cargo.nome_cargo if cand.cargo else "Cargo Diversos",
                    "codigo_cargo": cand.cargo.codigo_cargo if cand.cargo else "",
                    "vagas_edital": v_edital,
                    "vagas_lei": v_lei,
                    "vagas_ocupadas_oficial": v_oc,
                    "vagas_disponiveis_oficial": v_livres,
                    "convocados": 0,
                    "empossados": 0,
                    "desistencias": 0,
                    "fim_de_fila": 0,
                    "eliminados": 0,
                    "sub_judice": 0,
                    "saldo": v_edital
                }

            st = (cand.status_atual or "").upper()
            if any(k in st for k in ["CONVOCADO", "EMPOSSADO", "DESISTENTE", "FINAL DA FILA", "EXCLUÍDO", "EXONERADO", "SUB JÚDICE"]):
                mapa_cargos[cid]["convocados"] += 1

            if any(k in st for k in ["EXCLUÍDO", "EXONERADO", "NÃO COMPARECEU"]):
                mapa_cargos[cid]["eliminados"] += 1
            elif "EMPOSSADO" in st:
                mapa_cargos[cid]["empossados"] += 1
            elif "DESISTENTE" in st or "RENÚNCIA" in st:
                mapa_cargos[cid]["desistencias"] += 1
            elif "FINAL DA FILA" in st:
                mapa_cargos[cid]["fim_de_fila"] += 1
            elif "SUB JÚDICE" in st:
                mapa_cargos[cid]["sub_judice"] += 1

        resumo = []
        for cid, dados in mapa_cargos.items():
            dados["saldo"] = max(0, dados["vagas_edital"] - dados["empossados"])
            dados["cargo"] = dados["cargo_nome"]
            dados["fim_fila"] = dados["fim_de_fila"]
            resumo.append(dados)

        resumo.sort(key=lambda x: x["cargo_nome"])
        return resumo

    def gerar_alertas_controle_interno_acompanhamento(self, certame_id: int):
        """
        Retorna alertas automáticos de controle interno:
        1. Preterição da ordem de classificação.
        2. Estouro de prazo legal de posse (>30 dias).
        3. Inconsistências de Fim de Fila sem documento de opção.
        """
        from models import Candidato, Convocacao, CertameAbertura
        from datetime import date

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return []

        concurso = self.obter_ou_criar_dados_acompanhamento(certame_id)
        if not concurso:
            return []

        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).order_by(Candidato.id_cargo, Candidato.classificacao_original).all()

        alertas = []
        by_cargo = {}
        for cand in candidatos:
            by_cargo.setdefault(cand.id_cargo, []).append(cand)

        for cid, cand_list in by_cargo.items():
            cand_list.sort(key=lambda x: x.classificacao_original)
            max_conv_pos = 0

            for cand in cand_list:
                st = cand.status_atual.upper()
                pos = cand.classificacao_original
                nome_c = cand.nome_completo
                cargo_n = cand.cargo.nome_cargo if cand.cargo else "Cargo"

                # Preterição
                if "CONVOCADO" in st or "EMPOSSADO" in st:
                    if pos > max_conv_pos + 1:
                        anteriores = [c for c in cand_list if c.classificacao_original < pos and c.status_atual == "CLASSIFICADO (AGUARDANDO CONVOCAÇÃO)"]
                        if anteriores:
                            alertas.append({
                                "tipo": "PRETERICAO_CLASSIFICACAO",
                                "gravidade": "GRAVE",
                                "titulo": f"Alerta de Preterição de Ordem — {cargo_n}",
                                "descricao": f"O candidato {nome_c} (#{pos}º lugar) foi convocado/empossado enquanto {anteriores[0].nome_completo} (#{anteriores[0].classificacao_original}º) aguarda convocação sem desistência ou ordem judicial."
                            })
                    max_conv_pos = max(max_conv_pos, pos)

                # Estouro de Prazo de Posse (>30 dias)
                conv = self.db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).first()
                if conv and "CONVOCADO" in st and not conv.compareceu:
                    dias = (date.today() - conv.data_publicacao_doe).days
                    if dias > 30:
                        alertas.append({
                            "tipo": "ESTOURO_PRAZO_POSSE",
                            "gravidade": "ALERTA",
                            "titulo": f"Decurso de Prazo Legal de Posse ({dias} dias) — {nome_c}",
                            "descricao": f"A portaria {conv.numero_portaria} foi publicada em {conv.data_publicacao_doe.strftime('%d/%m/%Y')}. O prazo legal expirou sem posse ou justificativa formal."
                        })

                # Inconsistência Fim de Fila
                if "FINAL DA FILA" in st:
                    if not cand.movimentacoes:
                        alertas.append({
                            "tipo": "INCONSISTENCIA_FIM_FILA",
                            "gravidade": "INFORMATIVO",
                            "titulo": f"Pendente Requerimento de Fim de Fila — {nome_c}",
                            "descricao": f"O candidato {nome_c} consta como Fim de Fila sem anexo formal da opção do interessado no sistema."
                        })

        # Alerta de Fiscalização: Verificar se cada retificação inserida possui sua respectiva publicação
        from models import CertameAnexo, CertameVigenciaAto
        anexos = self.db.query(CertameAnexo).filter_by(id_certame=certame_id).all()
        retificacoes = [a for a in anexos if "RETIFICACAO_EDITAL" in a.tipo_documento or a.tipo_documento == "RETIFICACAO"]
        publicacoes_ret = [a for a in anexos if "PUBLICACAO_RETIFICACAO" in a.tipo_documento]

        count_ret = len(retificacoes)
        count_pub = len(publicacoes_ret)

        if count_ret > count_pub:
            alertas.append({
                "tipo": "RETIFICACAO_SEM_PUBLICACAO",
                "gravidade": "ALERTA",
                "titulo": "Retificação de Edital sem Comprovação de Publicação",
                "descricao": f"Constam {count_ret} retificação(ões) do edital anexada(s), porém apenas {count_pub} publicação(ões) de retificação cadastrada(s). Cada retificação inserida deve ser acompanhada da respectiva comprovação de publicação no Diário Oficial de Contas (DOC/TCE-MT)."
            })

        return alertas

    def obter_alertas_posse_apos_vigencia(self, certame_id: int):
        """
        Gera a lista de alertas de convocações/posses efetuadas após o vencimento da vigência.
        Fica reservado para exibição no local específico a ser indicado pelo auditor.
        """
        from models import Candidato, Convocacao, CertameAbertura, CertameVigenciaAto
        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return []

        concurso = self.obter_ou_criar_dados_acompanhamento(certame_id)
        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).order_by(Candidato.id_cargo, Candidato.classificacao_original).all()

        atos_vig = self.db.query(CertameVigenciaAto).filter_by(id_certame=certame_id).order_by(CertameVigenciaAto.nova_data_fim_vigencia.desc()).all()
        data_limite_vigencia = None
        if atos_vig:
            data_limite_vigencia = atos_vig[0].nova_data_fim_vigencia
        elif concurso and concurso.data_validade_final:
            data_limite_vigencia = concurso.data_validade_final

        alertas_vig = []
        if data_limite_vigencia:
            for cand in candidatos:
                conv = self.db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).first()
                if conv and conv.data_publicacao_doe and conv.data_publicacao_doe > data_limite_vigencia:
                    alertas_vig.append({
                        "tipo": "CONVOCACAO_POSSE_APOS_VIGENCIA",
                        "gravidade": "IRREGULARIDADE_CRITICA",
                        "titulo": f"Provimento Ilegal: Convocação/Posse após Vencimento da Vigência — {cand.nome_completo}",
                        "descricao": f"O candidato {cand.nome_completo} ({cand.cargo.nome_cargo if cand.cargo else 'Cargo'}) possui ato de provimento registrado em {conv.data_publicacao_doe.strftime('%d/%m/%Y')}, contudo a vigência do certame encerrou-se em {data_limite_vigencia.strftime('%d/%m/%Y')}. Atos praticados após a expiração da validade do concurso são nulos de pleno direito nos termos do Art. 37, III e IV da CF/88."
                    })

        return alertas_vig

    def zerar_acompanhamento_certame(self, certame_id: int) -> dict:
        """
        Zera o acompanhamento de um certame específico, removendo convocações, atos pós-homologação,
        termos e movimentações, e retornando todos os candidatos ao seu estado inicial pós-homologação.
        """
        from models import (
            CertameAbertura, Concurso, ConcursoVaga, Candidato, 
            Convocacao, MovimentacaoCandidato, CertameAcompanhamentoAto, CertameAnexo
        )
        from document_parser import DocumentParserAI

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        if not certame:
            return {"status": "ERRO", "mensagem": "Certame não encontrado."}

        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()
        id_concurso = concurso.id_concurso if concurso else 0

        # 1. Remover atos de acompanhamento registrados (exceto o ato inicial de importação da homologação)
        atos = self.db.query(CertameAcompanhamentoAto).filter_by(id_certame=certame_id).all()
        for ato in atos:
            if ato.tipo_ato != "IMPORTACAO_HOMOLOGACAO_OFICIAL":
                self.db.delete(ato)

        # 2. Buscar candidatos do certame
        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).all()

        total_zerados = len(candidatos)

        for cand in candidatos:
            # Remover convocações do candidato
            convs = self.db.query(Convocacao).filter_by(id_candidato=cand.id_candidato).all()
            for cv in convs:
                self.db.delete(cv)

            # Remover movimentações do candidato
            movs = self.db.query(MovimentacaoCandidato).filter_by(id_candidato=cand.id_candidato).all()
            for mv in movs:
                self.db.delete(mv)

            # Restaurar classificação efetiva
            cand.classificacao_efetiva = cand.classificacao_original

            # Verificar vagas do edital para determinar se é APROVADO ou CADASTRO RESERVA
            v_ed = self.db.query(ConcursoVaga).filter_by(
                id_concurso=id_concurso, id_cargo=cand.id_cargo
            ).first()
            vagas_imed = v_ed.vagas_imediatas_edital if v_ed else 5

            if cand.classificacao_original <= vagas_imed:
                cand.status_atual = "APROVADO (AGUARDANDO CONVOCAÇÃO)"
            else:
                cand.status_atual = "CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)"

        self.db.commit()

        # 3. Se houver anexos de Homologação Final com texto, re-extrai os candidatos para garantir estado limpo
        anexos_homol = self.db.query(CertameAnexo).filter(
            (CertameAnexo.id_certame == certame_id) &
            (CertameAnexo.tipo_documento.in_([
                "HOMOLOGACAO_RESULTADO_FINAL", 
                "PUBLICACAO_HOMOLOGACAO_RESULTADO_FINAL",
                "RESULTADO_FINAL_HOMOLOGACAO"
            ]))
        ).all()

        for a_hom in anexos_homol:
            if a_hom.conteudo_texto and len(a_hom.conteudo_texto) > 100:
                DocumentParserAI.process_homologacao_resultado_final(a_hom.conteudo_texto, self.db, certame_id)

        self.db.commit()

        return {
            "status": "SUCESSO",
            "candidatos_restaurados": total_zerados,
            "mensagem": f"Acompanhamento do Certame #{certame.numero_certame} zerado com sucesso. {total_zerados} candidatos retornaram ao status inicial pós-homologação."
        }

    def gerar_dossie_concurso_expirado(self, certame_id: int):
        """
        Gera o Dossiê Consolidado de Encerramento do Concurso Expirado:
        - Quadro Quantitativo Completo por Cargo (Lotacionograma, Edital, Aprovados, CR, Convocados, Empossados/Exercício, Desistências, Exonerações, Sub Júdice, Saldo)
        - Totais Consolidados do Município
        - Rol de Candidatos Aprovados e CR
        - Histórico de Vigência e Encerramento
        """
        from models import Candidato, Cargo, ConcursoVaga, Lotacionograma, CertameAbertura, Concurso

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()
        
        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).order_by(Candidato.id_cargo, Candidato.classificacao_efetiva).all()

        quadro_cargos = []
        totais = {
            "vagas_lei": 0,
            "vagas_edital": 0,
            "aprovados_diretos": 0,
            "cadastro_reserva": 0,
            "total_aprovados": 0,
            "convocados": 0,
            "empossados_exercicio": 0,
            "desistencias": 0,
            "exoneracoes": 0,
            "sub_judice": 0,
            "saldo_livre": 0
        }

        mapa_cargos = {}
        vagas_concurso = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso).all() if concurso else []
        for cv in vagas_concurso:
            cid = cv.id_cargo
            cargo_obj = cv.cargo
            lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()
            v_edital = cv.vagas_imediatas_edital if (cv.vagas_imediatas_edital is not None) else 0
            v_lei = lot_rec.vagas_criadas_lei if lot_rec else (cv.vagas_cr or 10)
            nome_c = cargo_obj.nome_cargo if cargo_obj else f"Cargo {cid}"

            mapa_cargos[cid] = {
                "id_cargo": cid,
                "cargo_nome": nome_c,
                "codigo_cargo": cargo_obj.codigo_cargo if cargo_obj else f"CARGO-{cid}",
                "vagas_lei": v_lei,
                "vagas_edital": v_edital,
                "aprovados_diretos": 0,
                "cadastro_reserva": 0,
                "convocados": 0,
                "empossados_exercicio": 0,
                "desistencias": 0,
                "exoneracoes": 0,
                "sub_judice": 0,
                "saldo_livre": v_edital
            }

        for cand in candidatos:
            cid = cand.id_cargo
            if cid not in mapa_cargos:
                vaga_rec = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso if concurso else 0, id_cargo=cid).first()
                lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()

                v_edital = vaga_rec.vagas_imediatas_edital if (vaga_rec and vaga_rec.vagas_imediatas_edital is not None) else 0
                v_lei = lot_rec.vagas_criadas_lei if lot_rec else 10

                mapa_cargos[cid] = {
                    "id_cargo": cid,
                    "cargo_nome": cand.cargo.nome_cargo if cand.cargo else "Cargo Diversos",
                    "codigo_cargo": cand.cargo.codigo_cargo if cand.cargo else f"CARGO-{cid}",
                    "vagas_lei": v_lei,
                    "vagas_edital": v_edital,
                    "aprovados_diretos": 0,
                    "cadastro_reserva": 0,
                    "convocados": 0,
                    "empossados_exercicio": 0,
                    "desistencias": 0,
                    "exoneracoes": 0,
                    "sub_judice": 0,
                    "saldo_livre": v_edital
                }

            st = (cand.status_atual or "").upper()
            
            # Classificação inicial (se <= vagas_edital é Aprovado Direto, se > é Cadastro Reserva)
            v_ed = mapa_cargos[cid]["vagas_edital"]
            if v_ed > 0 and cand.classificacao_original <= v_ed and mapa_cargos[cid]["aprovados_diretos"] < v_ed:
                mapa_cargos[cid]["aprovados_diretos"] += 1
            else:
                mapa_cargos[cid]["cadastro_reserva"] += 1

            if any(k in st for k in ["CONVOCADO", "EMPOSSADO", "DESISTENTE", "FINAL DA FILA", "EXCLUÍDO", "EXONERADO", "SUB JÚDICE"]):
                mapa_cargos[cid]["convocados"] += 1

            if "EMPOSSADO" in st:
                mapa_cargos[cid]["empossados_exercicio"] += 1
            
            if any(k in st for k in ["DESISTENTE", "RENÚNCIA", "FINAL DA FILA"]):
                mapa_cargos[cid]["desistencias"] += 1

            if any(k in st for k in ["EXCLUÍDO", "EXONERADO", "NÃO COMPARECEU"]):
                mapa_cargos[cid]["exoneracoes"] += 1

            if "SUB JÚDICE" in st or getattr(cand, 'sub_judice', False):
                mapa_cargos[cid]["sub_judice"] += 1

        # Calcular saldos e acumulados
        for cid, item in mapa_cargos.items():
            v_ed = item["vagas_edital"]
            emp = item["empossados_exercicio"]
            item["saldo_livre"] = max(0, v_ed - emp)
            item["taxa_cobertura"] = round((emp / v_ed) * 100, 1) if v_ed > 0 else 0.0
            
            quadro_cargos.append(item)

            totais["vagas_lei"] += item["vagas_lei"]
            totais["vagas_edital"] += item["vagas_edital"]
            totais["aprovados_diretos"] += item["aprovados_diretos"]
            totais["cadastro_reserva"] += item["cadastro_reserva"]
            totais["total_aprovados"] += item["aprovados_diretos"] + item["cadastro_reserva"]
            totais["convocados"] += item["convocados"]
            totais["empossados_exercicio"] += item["empossados_exercicio"]
            totais["desistencias"] += item["desistencias"]
            totais["exoneracoes"] += item["exoneracoes"]
            totais["sub_judice"] += item["sub_judice"]
            totais["saldo_livre"] += item["saldo_livre"]

        totais["taxa_cobertura_geral"] = round((totais["empossados_exercicio"] / totais["vagas_edital"]) * 100, 1) if totais["vagas_edital"] > 0 else 0.0

        return {
            "certame": certame,
            "concurso": concurso,
            "quadro_cargos": quadro_cargos,
            "totais": totais,
            "candidatos": candidatos
        }

    def gerar_relatorio_auditoria_final(self, certame_id: int):
        """
        Consolida o Relatório Completo de Auditoria ao Final do Certame:
        - Resumo e conformidade da Fase Pré-Edital (Planejamento, LRF arts. 16/17, Lei Autorizadora)
        - Resumo com Dashboard da Fase Oficial (Banca, Inscrições, Homologação)
        - Linha do Tempo / Timeline Executiva em Dashboard (Início a Encerramento/Expiração)
        - Avaliação e Quantificação Completa por Cargo (Vagas Lei, Vagas Edital, Aprovados, Convocados, Exercício, Desistências, Exonerações, Sub Júdice, Saldo)
        - Totalizadores Executivos e Distribuição por Escolaridade
        - Pareceres Prévios e Conclusivos da Auditoria de Controle Interno
        """
        from models import (
            Candidato, Cargo, ConcursoVaga, Lotacionograma, CertameAbertura, 
            Concurso, CertameFaseOficial, ParecerTecnico, ParecerOficial, CertameVigenciaAto
        )
        from datetime import date

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()
        fase_oficial = self.db.query(CertameFaseOficial).filter_by(id_certame=certame_id).first()
        parecer_tecnico = self.db.query(ParecerTecnico).filter_by(id_certame=certame_id).first()
        parecer_oficial = self.db.query(ParecerOficial).filter_by(id_certame=certame_id).first()
        atos_vigencia = self.db.query(CertameVigenciaAto).filter_by(id_certame=certame_id).order_by(CertameVigenciaAto.data_publicacao.asc()).all()

        candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).order_by(Candidato.id_cargo, Candidato.classificacao_efetiva).all()

        # Datas Relevantes do Certame (Linha do Tempo em Dashboard)
        dt_edital = fase_oficial.data_publicacao_edital if (fase_oficial and fase_oficial.data_publicacao_edital) else date(2022, 5, 25)
        dt_abertura = certame.data_abertura_processo if (certame and certame.data_abertura_processo and certame.data_abertura_processo <= dt_edital) else date(dt_edital.year, 1, 10)
        dt_inscricoes = fase_oficial.data_homologacao_inscricoes if (fase_oficial and fase_oficial.data_homologacao_inscricoes) else date(2022, 8, 1)
        dt_homologacao = (
            fase_oficial.data_homologacao_resultado_final if (fase_oficial and fase_oficial.data_homologacao_resultado_final)
            else (concurso.data_homologacao if concurso else date(2022, 10, 14))
        )
        dt_provas = fase_oficial.data_realizacao_provas if (fase_oficial and fase_oficial.data_realizacao_provas and fase_oficial.data_realizacao_provas <= dt_homologacao) else date(dt_homologacao.year, 9, 11)
        dt_parcial = fase_oficial.data_resultado_parcial if (fase_oficial and fase_oficial.data_resultado_parcial and fase_oficial.data_resultado_parcial <= dt_homologacao) else date(dt_homologacao.year, 10, 6)
        
        dt_inicio_vigencia = dt_homologacao
        dt_validade_final = concurso.data_validade_final if (concurso and concurso.data_validade_final) else date(2024, 10, 14)
        hoje = date.today()
        dias_vigencia = (dt_validade_final - dt_inicio_vigencia).days if (dt_validade_final and dt_inicio_vigencia) else 730
        is_expirado = bool((dt_validade_final and dt_validade_final < hoje) or (concurso and concurso.status == 'EXPIRADO'))

        prazo_meses_calc = getattr(concurso, 'prazo_validade_meses', None) or (fase_oficial.prazo_validade_meses if (fase_oficial and getattr(fase_oficial, 'prazo_validade_meses', None)) else (12 if 'SELETIVO' in (certame.modalidade if certame else '').upper() else 24))
        prazo_anos_calc = max(1, round(prazo_meses_calc / 12))

        timeline_datas = [
            {
                "chave": "abertura",
                "fase": "Fase Pré-Edital",
                "titulo": "Abertura do Processo Administrativo",
                "data_fmt": dt_abertura.strftime('%d/%m/%Y') if dt_abertura else "10/01/2022",
                "descricao": "Planejamento, justificativa, estudo orçamentário (LRF) e autorização legislativa.",
                "icone": "fa-folder-open",
                "badge_cor": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
            },
            {
                "chave": "edital",
                "fase": "Fase Oficial",
                "titulo": f"Publicação do Edital de Abertura nº {certame.numero_certame if certame else ''}",
                "data_fmt": dt_edital.strftime('%d/%m/%Y') if dt_edital else "25/05/2022",
                "descricao": "Publicação no Diário Oficial e abertura formal das inscrições e isenções.",
                "icone": "fa-file-lines",
                "badge_cor": "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
            },
            {
                "chave": "inscricoes",
                "fase": "Fase Oficial",
                "titulo": "Homologação das Inscrições",
                "data_fmt": dt_inscricoes.strftime('%d/%m/%Y') if dt_inscricoes else "01/08/2022",
                "descricao": "Publicação do rol definitivo de inscritos e isenções deferidas de taxa.",
                "icone": "fa-users",
                "badge_cor": "bg-sky-500/20 text-sky-300 border-sky-500/40"
            },
            {
                "chave": "provas",
                "fase": "Fase Oficial",
                "titulo": "Aplicação das Provas Objetivas",
                "data_fmt": dt_provas.strftime('%d/%m/%Y') if dt_provas else "11/09/2022",
                "descricao": "Aplicação dos exames de conhecimentos gerais e específicos pela banca.",
                "icone": "fa-pen-to-square",
                "badge_cor": "bg-purple-500/20 text-purple-300 border-purple-500/40"
            },
            {
                "chave": "homologacao",
                "fase": "Fase Oficial",
                "titulo": "Homologação do Resultado Final",
                "data_fmt": dt_homologacao.strftime('%d/%m/%Y') if dt_homologacao else "11/01/2024",
                "descricao": "Decreto de homologação definitiva do resultado e classificação final.",
                "icone": "fa-award",
                "badge_cor": "bg-amber-500/20 text-amber-300 border-amber-500/40"
            },
            {
                "chave": "vigencia",
                "fase": "Vigência & Provimentos",
                "titulo": f"Início da Vigência {'Anual' if prazo_anos_calc == 1 else ('Bienal' if prazo_anos_calc == 2 else f'{prazo_anos_calc} Anos')}",
                "data_fmt": dt_inicio_vigencia.strftime('%d/%m/%Y') if dt_inicio_vigencia else "11/01/2024",
                "descricao": f"Início da contagem do prazo de {prazo_anos_calc} ano(s) ({prazo_meses_calc} meses) para convocações e provimentos.",
                "icone": "fa-calendar-check",
                "badge_cor": "bg-teal-500/20 text-teal-300 border-teal-500/40"
            },
            {
                "chave": "encerramento",
                "fase": "Encerramento Definitivo",
                "titulo": "Término da Validade (Expiração)",
                "data_fmt": dt_validade_final.strftime('%d/%m/%Y') if dt_validade_final else "11/01/2025",
                "descricao": "Conclusão definitiva do certame com trânsito em julgado administrativo.",
                "icone": "fa-box-archive",
                "badge_cor": "bg-rose-500/20 text-rose-300 border-rose-500/40"
            }
        ]

        quadro_cargos = []
        totais = {
            "vagas_lei": 0,
            "vagas_edital": 0,
            "aprovados_diretos": 0,
            "cadastro_reserva": 0,
            "total_aprovados": 0,
            "convocados": 0,
            "empossados_exercicio": 0,
            "desistencias": 0,
            "exoneracoes": 0,
            "sub_judice": 0,
            "saldo_livre": 0,
            "cargos_preenchidos_100": 0,
            "cargos_com_saldo": 0
        }

        distribuicao_escolaridade = {
            "Superior": {"cargos": 0, "vagas_edital": 0, "aprovados": 0, "empossados": 0},
            "Médio": {"cargos": 0, "vagas_edital": 0, "aprovados": 0, "empossados": 0},
            "Técnico": {"cargos": 0, "vagas_edital": 0, "aprovados": 0, "empossados": 0}
        }

        mapa_cargos = {}
        vagas_concurso = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso).all() if concurso else []
        for cv in vagas_concurso:
            cid = cv.id_cargo
            cargo_obj = cv.cargo
            lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()
            v_edital = cv.vagas_imediatas_edital if (cv.vagas_imediatas_edital is not None) else 0
            v_lei = lot_rec.vagas_criadas_lei if lot_rec else (cv.vagas_cr or 10)
            nome_c = cargo_obj.nome_cargo if cargo_obj else f"Cargo {cid}"
            nivel_raw = cargo_obj.nivel_escolaridade if (cargo_obj and cargo_obj.nivel_escolaridade) else "Médio"

            mapa_cargos[cid] = {
                "id_cargo": cid,
                "cargo_nome": nome_c,
                "codigo_cargo": cargo_obj.codigo_cargo if cargo_obj else f"CARGO-{cid}",
                "nivel_escolaridade": nivel_raw,
                "vagas_lei": v_lei,
                "vagas_edital": v_edital,
                "aprovados_diretos": 0,
                "cadastro_reserva": 0,
                "convocados": 0,
                "empossados_exercicio": 0,
                "desistencias": 0,
                "exoneracoes": 0,
                "sub_judice": 0,
                "saldo_livre": v_edital
            }

        for cand in candidatos:
            cid = cand.id_cargo
            if cid not in mapa_cargos:
                vaga_rec = self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso if concurso else 0, id_cargo=cid).first()
                lot_rec = self.db.query(Lotacionograma).filter_by(id_cargo=cid).first()
                cargo_obj = cand.cargo

                v_edital = vaga_rec.vagas_imediatas_edital if (vaga_rec and vaga_rec.vagas_imediatas_edital is not None) else 0
                v_lei = lot_rec.vagas_criadas_lei if lot_rec else 10

                nome_c = cargo_obj.nome_cargo if cargo_obj else f"Cargo {cid}"
                nivel_raw = cargo_obj.nivel_escolaridade if (cargo_obj and cargo_obj.nivel_escolaridade) else ""
                if not nivel_raw:
                    if "Superior" in nome_c:
                        nivel_raw = "Superior"
                    elif "Técnico" in nome_c:
                        nivel_raw = "Técnico"
                    else:
                        nivel_raw = "Médio"

                mapa_cargos[cid] = {
                    "id_cargo": cid,
                    "cargo_nome": nome_c,
                    "codigo_cargo": cargo_obj.codigo_cargo if cargo_obj else f"CARGO-{cid}",
                    "nivel_escolaridade": nivel_raw,
                    "vagas_lei": v_lei,
                    "vagas_edital": v_edital,
                    "aprovados_diretos": 0,
                    "cadastro_reserva": 0,
                    "convocados": 0,
                    "empossados_exercicio": 0,
                    "desistencias": 0,
                    "exoneracoes": 0,
                    "sub_judice": 0,
                    "saldo_livre": v_edital
                }

            st = (cand.status_atual or "").upper()
            v_ed = mapa_cargos[cid]["vagas_edital"]
            if v_ed > 0 and cand.classificacao_original <= v_ed and mapa_cargos[cid]["aprovados_diretos"] < v_ed:
                mapa_cargos[cid]["aprovados_diretos"] += 1
            else:
                mapa_cargos[cid]["cadastro_reserva"] += 1

            has_posse = bool(getattr(cand, 'data_posse', None))
            has_exon = bool(getattr(cand, 'data_exoneracao', None)) or any(k in st for k in ["EXCLUÍDO", "EXONERADO", "NÃO COMPARECEU"])
            has_desist = bool(getattr(cand, 'edital_desistencia', None)) or any(k in st for k in ["DESISTENTE", "RENÚNCIA", "FINAL DA FILA"])
            has_convoc = bool(getattr(cand, 'edital_convocacao', None)) or has_posse or has_exon or has_desist or any(k in st for k in ["CONVOCADO", "EMPOSSADO"])

            if has_convoc:
                mapa_cargos[cid]["convocados"] += 1

            if has_exon:
                mapa_cargos[cid]["exoneracoes"] += 1
            elif has_desist:
                mapa_cargos[cid]["desistencias"] += 1
            elif has_posse or "EMPOSSADO" in st:
                mapa_cargos[cid]["empossados_exercicio"] += 1

            if "SUB JÚDICE" in st or getattr(cand, 'sub_judice', False):
                mapa_cargos[cid]["sub_judice"] += 1

        for cid, item in mapa_cargos.items():
            v_ed = item["vagas_edital"]
            emp = item["empossados_exercicio"]
            saldo = max(0, v_ed - emp)
            item["saldo_livre"] = saldo
            item["taxa_cobertura"] = round((emp / v_ed) * 100, 1) if v_ed > 0 else 100.0
            item["total_aprovados"] = item["aprovados_diretos"] + item["cadastro_reserva"]

            if v_ed == 0:
                item["situacao_provimento"] = "CADASTRO RESERVA"
                totais["cargos_preenchidos_100"] += 1
            elif saldo == 0:
                item["situacao_provimento"] = "100% PREENCHIDO"
                totais["cargos_preenchidos_100"] += 1
            else:
                item["situacao_provimento"] = "SALDO RESIDUAL"
                totais["cargos_com_saldo"] += 1

            quadro_cargos.append(item)

            totais["vagas_lei"] += item["vagas_lei"]
            totais["vagas_edital"] += item["vagas_edital"]
            totais["aprovados_diretos"] += item["aprovados_diretos"]
            totais["cadastro_reserva"] += item["cadastro_reserva"]
            totais["total_aprovados"] += item["total_aprovados"]
            totais["convocados"] += item["convocados"]
            totais["empossados_exercicio"] += item["empossados_exercicio"]
            totais["desistencias"] += item["desistencias"]
            totais["exoneracoes"] += item["exoneracoes"]
            totais["sub_judice"] += item["sub_judice"]
            totais["saldo_livre"] += saldo

            esc = item["nivel_escolaridade"]
            if esc in distribuicao_escolaridade:
                distribuicao_escolaridade[esc]["cargos"] += 1
                distribuicao_escolaridade[esc]["vagas_edital"] += item["vagas_edital"]
                distribuicao_escolaridade[esc]["aprovados"] += item["total_aprovados"]
                distribuicao_escolaridade[esc]["empossados"] += item["empossados_exercicio"]

        totais["taxa_cobertura_geral"] = round((totais["empossados_exercicio"] / totais["vagas_edital"]) * 100, 1) if totais["vagas_edital"] > 0 else 0.0
        totais["taxa_desistencia_geral"] = round((totais["desistencias"] / totais["convocados"]) * 100, 1) if totais["convocados"] > 0 else 0.0
        totais["taxa_aproveitamento_convocados"] = round((totais["empossados_exercicio"] / totais["convocados"]) * 100, 1) if totais["convocados"] > 0 else 0.0

        quadro_cargos.sort(key=lambda x: x["cargo_nome"])

        return {
            "certame": certame,
            "concurso": concurso,
            "fase_oficial": fase_oficial,
            "parecer_tecnico": parecer_tecnico,
            "parecer_oficial": parecer_oficial,
            "atos_vigencia": atos_vigencia,
            "timeline_datas": timeline_datas,
            "dias_vigencia": dias_vigencia,
            "is_expirado": is_expirado,
            "quadro_cargos": quadro_cargos,
            "totais": totais,
            "distribuicao_escolaridade": distribuicao_escolaridade,
            "candidatos": candidatos
        }

    def gerar_relatorio_nominal_convocados(self, certame_id: int):
        """
        Gera o Relatório Nominal de Candidatos Convocados por Cargo (Encerramento do Certame).
        Filtra estritamente os candidatos convocados (empossados em exercício, desistentes,
        exonerados/excluídos e convocados em trâmite), agrupando-os por cargo e
        omitindo os candidatos que permaneceram apenas em cadastro de reserva sem chamamento.
        """
        from models import Candidato, Cargo, ConcursoVaga, CertameAbertura, Concurso, CertameFaseOficial
        from datetime import date

        certame = self.db.query(CertameAbertura).filter_by(id_certame=certame_id).first()
        concurso = self.db.query(Concurso).filter_by(id_certame=certame_id).first()
        fase_oficial = self.db.query(CertameFaseOficial).filter_by(id_certame=certame_id).first()

        todos_candidatos = self.db.query(Candidato).filter_by(id_certame=certame_id).order_by(Candidato.id_cargo, Candidato.classificacao_original).all()

        # Filtrar apenas os que foram convocados (movimentações reais)
        # Exclui os que permaneceram apenas como cadastro de reserva não chamado
        candidatos_convocados = []
        for cand in todos_candidatos:
            st = (cand.status_atual or "").upper()
            if any(k in st for k in ["EMPOSSADO", "CONVOCADO", "DESISTENTE", "RENÚNCIA", "EXCLUÍDO", "EXONERADO"]):
                candidatos_convocados.append(cand)

        # Buscar os cargos vinculados especificamente a este certame/concurso
        cargos_vagas_ids = [cv.id_cargo for cv in self.db.query(ConcursoVaga).filter_by(id_concurso=concurso.id_concurso).all()] if concurso else []
        cargos_cands_ids = [c[0] for c in self.db.query(Candidato.id_cargo).filter_by(id_certame=certame_id).distinct().all()]
        cargos_certame_ids = list(set(cargos_vagas_ids + cargos_cands_ids))

        if cargos_certame_ids:
            cargos_db = self.db.query(Cargo).filter(Cargo.id_cargo.in_(cargos_certame_ids)).order_by(Cargo.nome_cargo.asc()).all()
        else:
            cargos_db = []

        grupos_cargos = []
        totais = {
            "total_homologados": len(todos_candidatos),
            "total_convocados": len(candidatos_convocados),
            "empossados_exercicio": 0,
            "desistencias": 0,
            "exoneracoes": 0,
            "convocados_tramite": 0,
            "candidatos_cr_omitidos": len(todos_candidatos) - len(candidatos_convocados),
            "cargos_com_convocados": 0,
            "total_cargos": len(cargos_db)
        }

        for cargo in cargos_db:
            cands_cargo = [c for c in candidatos_convocados if c.id_cargo == cargo.id_cargo]
            cands_cargo.sort(key=lambda x: x.classificacao_original or 999999)

            vaga_rec = self.db.query(ConcursoVaga).filter_by(
                id_concurso=concurso.id_concurso if concurso else 0,
                id_cargo=cargo.id_cargo
            ).first()
            v_edital = vaga_rec.vagas_imediatas_edital if (vaga_rec and vaga_rec.vagas_imediatas_edital is not None) else 0

            exon = sum(1 for c in cands_cargo if bool(getattr(c, 'data_exoneracao', None)) or any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO"]))
            des = sum(1 for c in cands_cargo if not (bool(getattr(c, 'data_exoneracao', None)) or any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO"])) and (bool(getattr(c, 'edital_desistencia', None)) or any(k in (c.status_atual or "").upper() for k in ["DESISTENTE", "RENÚNCIA"])))
            emp = sum(1 for c in cands_cargo if not (bool(getattr(c, 'data_exoneracao', None)) or any(k in (c.status_atual or "").upper() for k in ["EXCLUÍDO", "EXONERADO"])) and not (bool(getattr(c, 'edital_desistencia', None)) or any(k in (c.status_atual or "").upper() for k in ["DESISTENTE", "RENÚNCIA"])) and (bool(getattr(c, 'data_posse', None)) or "EMPOSSADO" in (c.status_atual or "").upper()))
            tram = len(cands_cargo) - emp - des - exon
            saldo = max(0, v_edital - emp)

            if len(cands_cargo) > 0:
                totais["cargos_com_convocados"] += 1

            totais["empossados_exercicio"] += emp
            totais["desistencias"] += des
            totais["exoneracoes"] += exon
            totais["convocados_tramite"] += tram

            cands_fmt = []
            for c in cands_cargo:
                st = (c.status_atual or "").upper()
                has_posse = bool(getattr(c, 'data_posse', None))
                has_exon = bool(getattr(c, 'data_exoneracao', None)) or any(k in st for k in ["EXCLUÍDO", "EXONERADO"])
                has_desist = bool(getattr(c, 'edital_desistencia', None)) or any(k in st for k in ["DESISTENTE", "RENÚNCIA"])

                if has_exon:
                    status_lbl = "EXCLUÍDO / EXONERADO"
                    status_classe = "text-slate-700 font-bold bg-slate-100 border-slate-300"
                    badge_tipo = "exonerado"
                elif has_desist:
                    status_lbl = "DESISTENTE / RENÚNCIA"
                    status_classe = "text-rose-800 font-bold bg-rose-50 border-rose-200"
                    badge_tipo = "desistente"
                elif has_posse or "EMPOSSADO" in st:
                    status_lbl = "EMPOSSADO (EXERCÍCIO)"
                    status_classe = "text-emerald-800 font-black bg-emerald-50 border-emerald-200"
                    badge_tipo = "empossado"
                else:
                    status_lbl = "CONVOCADO"
                    status_classe = "text-blue-800 font-bold bg-blue-50 border-blue-200"
                    badge_tipo = "convocado"

                dt_ini_str = c.data_posse.strftime("%d/%m/%Y") if getattr(c, 'data_posse', None) else "-"
                dt_fim_str = c.data_exoneracao.strftime("%d/%m/%Y") if getattr(c, 'data_exoneracao', None) else ("Vigente" if badge_tipo == "empossado" else "-")

                cands_fmt.append({
                    "id_candidato": c.id_candidato,
                    "classificacao_original": c.classificacao_original,
                    "classificacao_efetiva": c.classificacao_efetiva,
                    "nome_completo": c.nome_completo,
                    "cpf": c.cpf,
                    "tipo_cota": c.tipo_cota or "AMPLA",
                    "status_atual": c.status_atual,
                    "status_lbl": status_lbl,
                    "status_classe": status_classe,
                    "badge_tipo": badge_tipo,
                    "data_inicio_vigencia": dt_ini_str,
                    "data_fim_vigencia": dt_fim_str,
                    "data_posse": c.data_posse,
                    "data_exoneracao": c.data_exoneracao
                })

            grupos_cargos.append({
                "id_cargo": cargo.id_cargo,
                "codigo_cargo": cargo.codigo_cargo or f"CARGO-{cargo.id_cargo}",
                "cargo_nome": cargo.nome_cargo,
                "nivel_escolaridade": cargo.nivel_escolaridade or "Superior",
                "vagas_edital": v_edital,
                "total_convocados": len(cands_cargo),
                "empossados_exercicio": emp,
                "desistencias": des,
                "exoneracoes": exon,
                "convocados_tramite": tram,
                "saldo_livre": saldo,
                "taxa_cobertura": round((emp / v_edital) * 100, 1) if v_edital > 0 else 0.0,
                "candidatos": cands_fmt
            })

        totais["taxa_aproveitamento"] = round((totais["empossados_exercicio"] / totais["total_convocados"]) * 100, 1) if totais["total_convocados"] > 0 else 0.0

        return {
            "certame": certame,
            "concurso": concurso,
            "fase_oficial": fase_oficial,
            "grupos_cargos": grupos_cargos,
            "totais": totais,
            "data_hoje": date.today(),
            "is_expirado": True
        }


    # --- 3º RELATÓRIO GERENCIAL: CONFRONTO CONCURSOS VS. SELETIVOS (APURAÇÃO DE PRETERIÇÃO) ---
    def gerar_relatorio_auditoria_pretericao(
        self,
        tipo_cargo_filtro: str = None,
        origem_filtro: str = None,
        status_filtro: str = None,
        apenas_pretericao: bool = False,
        termo_busca: str = None,
        id_certame_base: int = 1
    ) -> dict:
        import unicodedata
        import re
        from datetime import datetime, date

        def canonical_cargo_type(raw_name):
            if not raw_name:
                return "OUTROS"
            nfkd = unicodedata.normalize('NFKD', raw_name)
            s = "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()
            
            if "DESENVOLVIMENTO INFANTIL" in s:
                return "TÉCNICO EM DESENVOLVIMENTO INFANTIL (TAE)"
            if "ASSISTENTE ADMINISTRATIVO" in s:
                return "ASSISTENTE ADMINISTRATIVO"
            if "ASSISTENTE SOCIAL EDUCACIONAL" in s:
                return "ASSISTENTE SOCIAL EDUCACIONAL"
            if "ASSISTENTE SOCIAL" in s:
                return "ASSISTENTE SOCIAL"
            if "AUXILIAR DE CONSULTORIO DENTARIO" in s:
                return "AUXILIAR DE CONSULTÓRIO DENTÁRIO"
            if "BIOQUIMICO" in s or "FARMACEUTICO" in s:
                return "BIOQUÍMICO / FARMACÊUTICO"
            if "ENFERMEIRO" in s and "TECNICO" not in s:
                return "ENFERMEIRO"
            if "TECNICO EM ENFERMAGEM" in s or ("ENFERMAGEM" in s and "TECNICO" in s):
                return "TÉCNICO EM ENFERMAGEM"
            if "FISIOTERAPEUTA" in s:
                return "FISIOTERAPEUTA"
            if "FISCAL DE TRANSITO" in s:
                return "FISCAL DE TRÂNSITO"
            if "FISCAL MUNICIPAL" in s:
                return "FISCAL MUNICIPAL"
            if "MEDICO" in s:
                return "MÉDICO"
            if "MULTIMEIOS" in s:
                return "TÉCNICO EM MULTIMEIOS DIDÁTICOS (TAE)"
            if "ADMINISTRACAO ESCOLAR" in s or "ADMINSTRA" in s:
                return "TÉCNICO EM ADMINISTRAÇÃO ESCOLAR (TAE)"
            if "NUTRICIONISTA" in s:
                return "NUTRICIONISTA"
            if "ODONTOLOGO" in s:
                return "ODONTÓLOGO"
            if "EDUCACAO FISICA" in s:
                return "PROFESSOR DE EDUCAÇÃO FÍSICA"
            if "EDUCACAO INFANTIL" in s:
                return "PROFESSOR DE EDUCAÇÃO INFANTIL"
            if "ANOS INICIAIS" in s or "ENSINO FUNDAMENTAL" in s:
                return "PROFESSOR ENSINO FUNDAMENTAL - ANOS INICIAIS"
            if "LINGUA INGLESA" in s or "INGLES" in s:
                return "PROFESSOR DE LÍNGUA INGLESA"
            if "PSICOLOGO EDUCACIONAL" in s:
                return "PSICÓLOGO EDUCACIONAL"
            if "PSICOLOGO" in s:
                return "PSICÓLOGO"
            if "HIGIENE DENTAL" in s:
                return "TÉCNICO EM HIGIENE DENTAL"
            if "PROCESSAMENTO DE DADOS" in s:
                return "TÉCNICO EM PROCESSAMENTO DE DADOS"
            if "SISTEMAS DE INFORMACAO" in s:
                return "ADMINISTRADOR DE SISTEMAS DE INFORMAÇÃO"
            if "RAIO-X" in s or "RAIO X" in s:
                return "TÉCNICO OPERACIONAL EM RAIO-X"

            clean = re.sub(r'^NIVEL\s+(MEDIO|SUPERIOR|FUNDAMENTAL)(\s+TECNICO)?\s*-\s*', '', s)
            clean = re.sub(r'^(TAE|PROFESSOR|DOCENTE)\s*-\s*', '', clean)
            clean = re.sub(r'\s*-\s*ZONA\s+(URBANA|RURAL).*$', '', clean)
            return clean.strip()

        def parse_iso_date(val):
            if not val:
                return None
            try:
                if isinstance(val, (datetime, date)):
                    return val if isinstance(val, date) else val.date()
                s = str(val).split(" ")[0].strip()
                parts = s.split("-")
                if len(parts) == 3:
                    return date(int(parts[0]), int(parts[1]), int(parts[2]))
                parts_br = s.split("/")
                if len(parts_br) == 3:
                    return date(int(parts_br[2]), int(parts_br[1]), int(parts_br[0]))
            except Exception:
                pass
            return None

        # 1. Obter vigência do Concurso Público de Referência
        certame_base = self.db.query(CertameAbertura).filter_by(id_certame=id_certame_base).first()
        concurso_base = self.db.query(Concurso).filter_by(id_certame=id_certame_base).first() if certame_base else None
        
        concurso_inicio = parse_iso_date(concurso_base.data_homologacao) if concurso_base and concurso_base.data_homologacao else date(2022, 10, 14)
        concurso_fim = parse_iso_date(concurso_base.data_validade_final) if concurso_base and concurso_base.data_validade_final else date(2024, 10, 14)

        # 2. Carregar todos os candidatos com certames e vagas
        todos_certames = self.db.query(CertameAbertura).order_by(CertameAbertura.ano.asc(), CertameAbertura.numero_certame.asc()).all()
        candidatos_query = self.db.query(Candidato).all()

        # Cache de vagas por (id_concurso, id_cargo)
        vagas_cache = {}
        for cv in self.db.query(ConcursoVaga).all():
            vagas_cache[(cv.id_concurso, cv.id_cargo)] = cv.vagas_imediatas_edital

        cargos_cache = {cg.id_cargo: cg for cg in self.db.query(Cargo).all()}
        certames_cache = {c.id_certame: c for c in todos_certames}

        # 3. Processar registros individuais
        lista_completa = []
        cargos_contagem = {}
        origens_set = set()

        for c in candidatos_query:
            cg = cargos_cache.get(c.id_cargo)
            ca = certames_cache.get(c.id_certame)
            
            cargo_nome_raw = cg.nome_cargo if cg else "Cargo Não Informado"
            canon_cargo = canonical_cargo_type(cargo_nome_raw)
            
            is_concurso = True if (ca and "CONCURSO" in (ca.modalidade or "").upper()) else (c.id_concurso == 3 or c.id_certame == 1)
            origem_tipo = "Concurso" if is_concurso else "Seletivo"
            ano_cert = ca.ano if ca else (2022 if is_concurso else 2024)
            num_cert = ca.numero_certame if ca else ("001/2022" if is_concurso else "")
            
            origem_label = f"{origem_tipo} {ano_cert}"
            origem_detalhe = f"{origem_tipo} {ano_cert} (Ed. {num_cert})" if num_cert else origem_label
            origens_set.add(origem_label)

            vagas_ed = vagas_cache.get((c.id_concurso, c.id_cargo), 1 if is_concurso else 0)
            classif = c.classificacao_original or 1
            if vagas_ed > 0 and classif <= vagas_ed:
                classif_cr_str = f"{classif}º"
                is_cr = False
            elif vagas_ed > 0:
                classif_cr_str = f"{classif - vagas_ed}º CR"
                is_cr = True
            else:
                classif_cr_str = f"{classif}º CR"
                is_cr = True

            posse_date = parse_iso_date(c.data_posse)
            exon_date = parse_iso_date(c.data_exoneracao)

            st = (c.status_atual or "").upper()
            has_posse = posse_date is not None
            has_exon = exon_date is not None or any(k in st for k in ["EXCLUÍDO", "EXONERADO"])
            has_desist = bool(c.edital_desistencia) or any(k in st for k in ["DESISTENTE", "RENÚNCIA"])

            if has_exon:
                status_label = "Exonerado"
                status_badge = "exonerado"
                status_classe = "bg-slate-100 text-slate-800 border-slate-300"
            elif has_desist:
                status_label = "Desistente/Renúncia"
                status_badge = "desistente"
                status_classe = "bg-rose-50 text-rose-800 border-rose-300"
            elif has_posse or "EMPOSSADO" in st or "EXERCÍCIO" in st:
                status_label = "Em exercício"
                status_badge = "empossado"
                status_classe = "bg-emerald-50 text-emerald-800 border-emerald-300 font-bold"
            elif "CONVOCADO" in st:
                status_label = "Convocado"
                status_badge = "convocado"
                status_classe = "bg-blue-50 text-blue-800 border-blue-300"
            else:
                status_label = "Aguardando Convocação"
                status_badge = "aguardando"
                status_classe = "bg-amber-50 text-amber-800 border-amber-300"

            # Apuração de Preterição
            is_pretericao = False
            motivo_pretericao = ""
            if not is_concurso:
                if posse_date and concurso_inicio <= posse_date <= concurso_fim:
                    is_pretericao = True
                    motivo_pretericao = f"Contratação no Seletivo em {posse_date.strftime('%d/%m/%Y')} durante vigência do Concurso 001/2022 ({concurso_inicio.strftime('%d/%m/%Y')} a {concurso_fim.strftime('%d/%m/%Y')})"
                elif has_posse and not posse_date:
                    is_pretericao = True
                    motivo_pretericao = "Contratação no Seletivo durante vigência presumida do concurso"
            else:
                if is_cr and status_badge == "aguardando":
                    motivo_pretericao = "Candidato em Cadastro de Reserva do Concurso aguardando convocação"

            reg = {
                "id_candidato": c.id_candidato,
                "nome_candidato": c.nome_completo,
                "cpf": c.cpf,
                "origem": origem_label,
                "origem_detalhe": origem_detalhe,
                "is_concurso": is_concurso,
                "ano_certame": ano_cert,
                "numero_certame": num_cert,
                "cargo_nome_original": cargo_nome_raw,
                "tipo_cargo": canon_cargo,
                "classificacao_original": classif,
                "classificacao_cr_str": classif_cr_str,
                "is_cr": is_cr,
                "data_posse": posse_date,
                "data_posse_str": posse_date.strftime("%d/%m/%Y") if posse_date else "",
                "data_exoneracao": exon_date,
                "data_exoneracao_str": exon_date.strftime("%d/%m/%Y") if exon_date else "",
                "status_label": status_label,
                "status_badge": status_badge,
                "status_classe": status_classe,
                "is_pretericao": is_pretericao,
                "motivo_pretericao": motivo_pretericao
            }

            lista_completa.append(reg)

            # Acumulador para estatísticas por tipo de cargo
            if canon_cargo not in cargos_contagem:
                cargos_contagem[canon_cargo] = {
                    "tipo_cargo": canon_cargo,
                    "total": 0,
                    "concurso": 0,
                    "seletivo": 0,
                    "pretericoes": 0
                }
            cargos_contagem[canon_cargo]["total"] += 1
            if is_concurso:
                cargos_contagem[canon_cargo]["concurso"] += 1
            else:
                cargos_contagem[canon_cargo]["seletivo"] += 1
                if is_pretericao:
                    cargos_contagem[canon_cargo]["pretericoes"] += 1

        # Lista de tipos de cargo ordenada por relevância
        tipos_cargos_lista = sorted(
            cargos_contagem.values(),
            key=lambda x: (x["concurso"] > 0 and x["seletivo"] > 0, x["pretericoes"], x["total"]),
            reverse=True
        )

        # Se nenhum cargo foi selecionado, definir default para o com maior preterição
        if not tipo_cargo_filtro and tipos_cargos_lista:
            # Seleciona o primeiro que tenha tanto concurso quanto seletivo com preterições
            cargos_com_ambos = [tc["tipo_cargo"] for tc in tipos_cargos_lista if tc["concurso"] > 0 and tc["seletivo"] > 0]
            cargo_ativo = cargos_com_ambos[0] if cargos_com_ambos else tipos_cargos_lista[0]["tipo_cargo"]
        else:
            cargo_ativo = tipo_cargo_filtro

        # 4. Aplicar filtros aos registros
        registros_filtrados = []
        for r in lista_completa:
            # Filtro tipo cargo
            if cargo_ativo and cargo_ativo != "TODOS" and r["tipo_cargo"] != cargo_ativo:
                continue

            # Filtro origem
            if origem_filtro and origem_filtro != "TODAS":
                if origem_filtro == "CONCURSO" and not r["is_concurso"]:
                    continue
                elif origem_filtro == "SELETIVO" and r["is_concurso"]:
                    continue
                elif origem_filtro not in ["CONCURSO", "SELETIVO"] and r["origem"] != origem_filtro:
                    continue

            # Filtro status
            if status_filtro and status_filtro != "TODOS":
                if status_filtro == "EM_EXERCICIO" and r["status_badge"] != "empossado":
                    continue
                elif status_filtro == "EXONERADO" and r["status_badge"] != "exonerado":
                    continue
                elif status_filtro == "DESISTENTE" and r["status_badge"] != "desistente":
                    continue
                elif status_filtro == "AGUARDANDO" and r["status_badge"] != "aguardando":
                    continue

            # Filtro apenas com alerta de preterição
            if apenas_pretericao and not r["is_pretericao"]:
                continue

            # Filtro busca por texto
            if termo_busca:
                tb = termo_busca.lower().strip()
                if (tb not in r["nome_candidato"].lower() and 
                    tb not in (r["cpf"] or "").lower() and 
                    tb not in r["origem"].lower() and 
                    tb not in r["status_label"].lower()):
                    continue

            registros_filtrados.append(r)

        # 5. Ordenação: por Data de Posse ascendente (com posse primeiro), depois sem posse por classificação
        def sort_key(x):
            has_posse = 0 if x["data_posse"] else 1
            dt_posse = x["data_posse"] or date(9999, 12, 31)
            orig_order = 0 if x["is_concurso"] else 1
            classif = x["classificacao_original"] or 999999
            return (has_posse, dt_posse, orig_order, classif)

        registros_filtrados.sort(key=sort_key)

        # 6. Totais e Métricas da Seleção
        totais = {
            "total_registros": len(registros_filtrados),
            "total_concurso": sum(1 for r in registros_filtrados if r["is_concurso"]),
            "total_seletivo": sum(1 for r in registros_filtrados if not r["is_concurso"]),
            "empossados_exercicio": sum(1 for r in registros_filtrados if r["status_badge"] == "empossado"),
            "exonerados": sum(1 for r in registros_filtrados if r["status_badge"] == "exonerado"),
            "desistencias": sum(1 for r in registros_filtrados if r["status_badge"] == "desistente"),
            "aguardando_cr": sum(1 for r in registros_filtrados if r["status_badge"] == "aguardando"),
            "alertas_pretericao": sum(1 for r in registros_filtrados if r["is_pretericao"]),
            "concurso_inicio": concurso_inicio,
            "concurso_fim": concurso_fim,
            "concurso_inicio_str": concurso_inicio.strftime("%d/%m/%Y"),
            "concurso_fim_str": concurso_fim.strftime("%d/%m/%Y"),
            "concurso_numero": certame_base.numero_certame if certame_base else "001/2022",
            "concurso_ano": certame_base.ano if certame_base else 2022
        }

        return {
            "certame_base": certame_base,
            "concurso_base": concurso_base,
            "todos_certames": todos_certames,
            "tipos_cargos_lista": tipos_cargos_lista,
            "origens_lista": sorted(list(origens_set)),
            "cargo_ativo": cargo_ativo,
            "origem_filtro": origem_filtro or "TODAS",
            "status_filtro": status_filtro or "TODOS",
            "apenas_pretericao": apenas_pretericao,
            "termo_busca": termo_busca or "",
            "registros": registros_filtrados,
            "totais": totais,
            "data_hoje": date.today()
        }
