import datetime
from models import (
    SessionLocal, init_db, Cargo, Lotacionograma, Concurso, ConcursoVaga,
    Candidato, MovimentacaoCandidato, Convocacao, ServidorEfetivo,
    Afastamento, ContratoTemporario
)

def seed_database():
    init_db()
    db = SessionLocal()

    # Limpa dados anteriores se houver
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
    db.commit()

    # 1. Cargos
    cargo_enf = Cargo(codigo_cargo="ENF-01", nome_cargo="Enfermeiro Padrão", nivel_escolaridade="Superior")
    cargo_med = Cargo(codigo_cargo="MED-01", nome_cargo="Médico Clínico Geral", nivel_escolaridade="Superior")
    cargo_prof = Cargo(codigo_cargo="PROF-01", nome_cargo="Professor de Educação Básica", nivel_escolaridade="Superior")
    cargo_adm = Cargo(codigo_cargo="ADM-01", nome_cargo="Auditor de Controle Interno", nivel_escolaridade="Superior")
    db.add_all([cargo_enf, cargo_med, cargo_prof, cargo_adm])
    db.commit()

    # 2. Lotacionograma (Vagas Criadas por Lei)
    lot_enf = Lotacionograma(id_cargo=cargo_enf.id_cargo, lei_criacao="Lei Municipal nº 1.200/2020", ano_vigencia=2026, vagas_criadas_lei=10)
    lot_med = Lotacionograma(id_cargo=cargo_med.id_cargo, lei_criacao="Lei Municipal nº 1.200/2020", ano_vigencia=2026, vagas_criadas_lei=5)
    lot_prof = Lotacionograma(id_cargo=cargo_prof.id_cargo, lei_criacao="Lei Municipal nº 1.200/2020", ano_vigencia=2026, vagas_criadas_lei=20)
    lot_adm = Lotacionograma(id_cargo=cargo_adm.id_cargo, lei_criacao="Lei Municipal nº 1.200/2020", ano_vigencia=2026, vagas_criadas_lei=4)
    db.add_all([lot_enf, lot_med, lot_prof, lot_adm])
    db.commit()

    # 3. Servidores Efetivos Ativos
    # No caso de Enfermeiro: 9 servidores ativos (com limite de 10 vagas)
    for i in range(1, 10):
        srv = ServidorEfetivo(
            matricula=f"MAT-ENF-{i:03d}",
            cpf=f"111.222.333-{i:02d}",
            nome=f"Servidor Efetivo Enfermeiro {i}",
            id_cargo=cargo_enf.id_cargo,
            data_admissao=datetime.date(2021, 2, 1),
            status_funcional="ATIVO"
        )
        db.add(srv)

    # Servidor Médico que está afastado (com direito a substituição)
    srv_med1 = ServidorEfetivo(matricula="MAT-MED-001", cpf="222.333.444-01", nome="Dra. Roberta Santos", id_cargo=cargo_med.id_cargo, data_admissao=datetime.date(2019, 5, 10), status_funcional="AFASTADO")
    # Servidor Médico ativo normal
    srv_med2 = ServidorEfetivo(matricula="MAT-MED-002", cpf="222.333.444-02", nome="Dr. Lucas Silveira", id_cargo=cargo_med.id_cargo, data_admissao=datetime.date(2019, 5, 10), status_funcional="ATIVO")
    db.add_all([srv_med1, srv_med2])
    db.commit()

    # 4. Afastamento do Servidor Médico (Licença Maternidade já encerrada - simulação de irregularidade)
    afast_med = Afastamento(
        id_servidor=srv_med1.id_servidor,
        tipo_afastamento="LICENCA_MATERNIDADE",
        data_inicio=datetime.date(2025, 6, 1),
        data_fim_prevista=datetime.date(2025, 12, 1),
        data_retorno_efetivo=datetime.date(2025, 12, 1), # Retornou em dez/2025
        gera_direito_substituicao=True
    )
    db.add(afast_med)
    db.commit()

    # 5. Concursos Públicos
    # Concurso 001/2024 - Saúde (Vigente)
    conc_saude = Concurso(
        numero_edital="001/2024-SAUDE",
        ano_edital=2024,
        data_homologacao=datetime.date(2024, 6, 15),
        data_validade_final=datetime.date(2026, 6, 15),
        status="VIGENTE"
    )
    # Concurso 002/2025 - Educação (Vigente)
    conc_edu = Concurso(
        numero_edital="002/2025-EDUCA",
        ano_edital=2025,
        data_homologacao=datetime.date(2025, 3, 10),
        data_validade_final=datetime.date(2027, 3, 10),
        status="VIGENTE"
    )
    db.add_all([conc_saude, conc_edu])
    db.commit()

    # Vagas no Concurso
    vaga_conc_enf = ConcursoVaga(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, vagas_imediatas_edital=3, vagas_cr=5)
    vaga_conc_prof = ConcursoVaga(id_concurso=conc_edu.id_concurso, id_cargo=cargo_prof.id_cargo, vagas_imediatas_edital=5, vagas_cr=10)
    db.add_all([vaga_conc_enf, vaga_conc_prof])
    db.commit()

    # 6. Candidatos Concurso Saúde (Enfermeiro)
    # Candidato 1: Convocado e Nomeado
    c1 = Candidato(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, cpf="001.000.000-01", nome_completo="Ana Paula Ferreira", classificacao_original=1, classificacao_efetiva=1, status_atual="CONVOCADO")
    # Candidato 2: Desistência Formal devidamente registrada
    c2 = Candidato(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, cpf="002.000.000-02", nome_completo="Bruno Mendes Lima", classificacao_original=2, classificacao_efetiva=2, status_atual="DESISTENTE_FORMAL")
    # Candidato 3: Preterido! Não foi convocado e não há desistência nos autos
    c3 = Candidato(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, cpf="003.000.000-03", nome_completo="Carlos Eduardo Souza (PRETERIDO)", classificacao_original=3, classificacao_efetiva=3, status_atual="AGUARDANDO_CONVOCACAO")
    # Candidato 4: Convocado pulando o Candidato 3 (Irregularidade Crítica!)
    c4 = Candidato(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, cpf="004.000.000-04", nome_completo="Daniela Castro", classificacao_original=4, classificacao_efetiva=4, status_atual="CONVOCADO")
    # Candidato 5: Convocado (gerando estouro de vagas legais: 9 ativos + 3 convocados = 12 provimentos projetados para 10 vagas por lei)
    c5 = Candidato(id_concurso=conc_saude.id_concurso, id_cargo=cargo_enf.id_cargo, cpf="005.000.000-05", nome_completo="Eduardo Rocha", classificacao_original=5, classificacao_efetiva=5, status_atual="CONVOCADO")

    db.add_all([c1, c2, c3, c4, c5])
    db.commit()

    # Movimentação regular do Candidato 2 (Termo formal anexado)
    mov_c2 = MovimentacaoCandidato(
        id_candidato=c2.id_candidato,
        tipo_evento="DESISTENCIA_EXPRESSA",
        numero_processo_sei="SEI-2024-88491",
        data_registro=datetime.datetime(2024, 7, 10, 14, 0),
        motivo_justificativa="Candidato tomou posse em outro cargo federal inacumulável."
    )
    db.add(mov_c2)

    # Convocações registradas no Diário Oficial
    conv1 = Convocacao(id_concurso=conc_saude.id_concurso, id_candidato=c1.id_candidato, ordem_convocacao_global=1, numero_portaria="PORT-101/2024", data_publicacao_doe=datetime.date(2024, 7, 1), prazo_posse_limite=datetime.date(2024, 8, 1), compareceu=True)
    conv4 = Convocacao(id_concurso=conc_saude.id_concurso, id_candidato=c4.id_candidato, ordem_convocacao_global=2, numero_portaria="PORT-120/2024", data_publicacao_doe=datetime.date(2024, 8, 15), prazo_posse_limite=datetime.date(2024, 9, 15), compareceu=None)
    conv5 = Convocacao(id_concurso=conc_saude.id_concurso, id_candidato=c5.id_candidato, ordem_convocacao_global=3, numero_portaria="PORT-140/2024", data_publicacao_doe=datetime.date(2024, 9, 1), prazo_posse_limite=datetime.date(2024, 10, 1), compareceu=None)
    db.add_all([conv1, conv4, conv5])
    db.commit()

    # Candidatos para Professor (Educação)
    cand_prof1 = Candidato(id_concurso=conc_edu.id_concurso, id_cargo=cargo_prof.id_cargo, cpf="006.000.000-06", nome_completo="Fabiana Gomes", classificacao_original=1, classificacao_efetiva=1, status_atual="AGUARDANDO_CONVOCACAO")
    cand_prof2 = Candidato(id_concurso=conc_edu.id_concurso, id_cargo=cargo_prof.id_cargo, cpf="007.000.000-07", nome_completo="Gabriel Vasconcelos", classificacao_original=2, classificacao_efetiva=2, status_atual="AGUARDANDO_CONVOCACAO")
    db.add_all([cand_prof1, cand_prof2])
    db.commit()

    # 7. Contratos Temporários (PSS) com Irregularidades
    # PSS 1: Substituição de Médico cujo titular já retornou da licença em dez/2025
    pss_med = ContratoTemporario(
        numero_contrato_pss="PSS-MED-2025/01",
        cpf="888.999.111-22",
        nome_contratado="Dr. Gilberto Andrade (Temporário)",
        id_cargo=cargo_med.id_cargo,
        motivo_contratacao="SUBSTITUICAO_AFASTAMENTO",
        id_servidor_substituido=srv_med1.id_servidor,
        data_inicio_contrato=datetime.date(2025, 6, 15),
        data_fim_prevista=datetime.date(2026, 6, 15),
        status_contrato="VIGENTE"
    )

    # PSS 2: Contratação de Professor Temporário para vaga livre havendo Concurso 002/2025 Vigente com aprovados aguardando
    pss_prof = ContratoTemporario(
        numero_contrato_pss="PSS-EDU-2026/05",
        cpf="777.888.333-11",
        nome_contratado="Helena Martins (Professora PSS)",
        id_cargo=cargo_prof.id_cargo,
        motivo_contratacao="VACANCIA_SEM_CONCURSO",
        id_servidor_substituido=None,
        data_inicio_contrato=datetime.date(2026, 1, 10),
        data_fim_prevista=datetime.date(2026, 12, 31),
        status_contrato="VIGENTE"
    )
    db.add_all([pss_med, pss_prof])
    db.commit()
    db.close()
    print("Base de dados de demonstração populada com sucesso!")

if __name__ == "__main__":
    seed_database()
