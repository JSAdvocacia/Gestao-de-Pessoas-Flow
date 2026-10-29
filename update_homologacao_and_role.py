import sqlite3

conn = sqlite3.connect('auditoria_pessoal.db')
c = conn.cursor()

# 1. Update concursos
print("Updating table concursos...")
c.execute("""
    UPDATE concursos 
    SET data_homologacao = '2022-10-13', data_validade_final = '2024-10-13', prazo_validade_meses = 24
    WHERE id_concurso = 3 OR id_certame = 1
""")

c.execute("""
    UPDATE concursos 
    SET data_homologacao = '2024-01-09', data_validade_final = '2025-01-09', prazo_validade_meses = 12
    WHERE id_concurso = 4 OR id_certame = 2
""")

c.execute("""
    UPDATE concursos 
    SET data_homologacao = '2023-01-30', data_validade_final = '2024-01-30', prazo_validade_meses = 12
    WHERE id_concurso = 5 OR id_certame = 3
""")

c.execute("""
    UPDATE concursos 
    SET data_homologacao = '2025-01-30', data_validade_final = '2026-01-30', prazo_validade_meses = 12
    WHERE id_concurso = 6 OR id_certame = 4
""")

# 2. Update certames_fase_oficial
print("Updating table certames_fase_oficial...")
c.execute("""
    UPDATE certames_fase_oficial 
    SET data_homologacao_resultado_final = '2022-10-13', data_resultado_final = '2022-10-13', prazo_validade_meses = 24
    WHERE id_certame = 1
""")

c.execute("""
    UPDATE certames_fase_oficial 
    SET data_homologacao_resultado_final = '2024-01-09', data_resultado_final = '2024-01-08', prazo_validade_meses = 12
    WHERE id_certame = 2
""")

c.execute("""
    UPDATE certames_fase_oficial 
    SET data_homologacao_resultado_final = '2023-01-30', data_resultado_final = '2023-01-27', prazo_validade_meses = 12
    WHERE id_certame = 3
""")

c.execute("""
    UPDATE certames_fase_oficial 
    SET data_homologacao_resultado_final = '2025-01-30', data_resultado_final = '2025-01-30', prazo_validade_meses = 12
    WHERE id_certame = 4
""")

# 3. Update atos de acompanhamento iniciais de homologacao
print("Updating table certames_acompanhamento_atos...")
c.execute("UPDATE certames_acompanhamento_atos SET data_ato = '2022-10-13' WHERE id_certame = 1 AND tipo_ato = 'IMPORTACAO_HOMOLOGACAO_OFICIAL'")
c.execute("UPDATE certames_acompanhamento_atos SET data_ato = '2024-01-09' WHERE id_certame = 2 AND tipo_ato = 'IMPORTACAO_HOMOLOGACAO_OFICIAL'")
c.execute("UPDATE certames_acompanhamento_atos SET data_ato = '2023-01-30' WHERE id_certame = 3 AND tipo_ato = 'IMPORTACAO_HOMOLOGACAO_OFICIAL'")
c.execute("UPDATE certames_acompanhamento_atos SET data_ato = '2025-01-30' WHERE id_certame = 4 AND tipo_ato = 'IMPORTACAO_HOMOLOGACAO_OFICIAL'")

# 4. Update usuarios
print("Updating table usuarios...")
c.execute("""
    UPDATE usuarios 
    SET nome = 'Jansen de Pinho e Silva' 
    WHERE email = 'prof.jan100@gmail.com'
""")

# 5. Update pareceres_oficiais e pareceres_tecnicos
print("Updating auditor_responsavel in pareceres...")
c.execute("UPDATE pareceres_oficiais SET auditor_responsavel = 'Jansen de Pinho e Silva - Técnico em Auditoria'")
c.execute("UPDATE pareceres_tecnicos SET auditor_responsavel = 'Jansen de Pinho e Silva - Técnico em Auditoria'")

conn.commit()

print("\n--- VERIFICAÇÃO CONCURSOS ---")
c.execute("SELECT id_concurso, id_certame, numero_edital, data_homologacao, data_validade_final, prazo_validade_meses FROM concursos")
for r in c.fetchall():
    print(r)

print("\n--- VERIFICAÇÃO FASES OFICIAIS ---")
c.execute("SELECT id_certame, data_homologacao_resultado_final, prazo_validade_meses FROM certames_fase_oficial")
for r in c.fetchall():
    print(r)

print("\n--- VERIFICAÇÃO USUÁRIOS ---")
c.execute("SELECT id_usuario, nome, email, perfil FROM usuarios")
for r in c.fetchall():
    print(r)

conn.close()
print("All DB updates applied successfully!")
