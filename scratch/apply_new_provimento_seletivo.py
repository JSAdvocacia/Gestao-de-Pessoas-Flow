import pypdf
import re
import sqlite3
import unicodedata
from datetime import datetime, date

pdf_path = r'C:\Users\Jansen.Pinho\.gemini\antigravity\brain\ee80db35-aadb-4571-a01d-c8624c58d26c\.user_uploaded\media_1792527725129_a5c99d49.pdf'
db_path = r'C:\Users\Jansen.Pinho\.gemini\antigravity\scratch\sistema-auditoria-pessoal\auditoria_pessoal.db'

print("Lendo novo PDF oficial de provimento (30/01/2025 até 30/01/2026)...")
reader = pypdf.PdfReader(pdf_path)

def norm(text):
    if not text:
        return ''
    n = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r'[^A-Z0-9]', '', n.upper())

alias_map = {
    norm('VITORIA FERNANDA DE OLIVEIRA GONCALVES'): norm('VITORIA FERNANDA DE OLIVEIRA GONCALVES CABREIRA'),
    norm('GLAUCIA M. MARTINS FERNANDES'): norm('GLAUCIA MADELEINE MARTINS FERNANDES'),
    norm('RAQUEL SOARES DA SILVA CARVALHO'): norm('RAQUEL SOARES DA SILVA'),
    norm('ISABEL ROSA MACHADO'): norm('ISABEL ROSA MACHADO NEVES'),
    norm('FALUBIA FERREIRA DO NASCIMENTO'): norm('FALUBIA FERREIRA DO NASCIMENTO MORAES'),
    norm('MARIA ROSA O NASCIMENTO'): norm('MARIA ROSA DE OLIVEIRA NASCIMENTO'),
    norm('JOVINA MARIA J BORGES NETA'): norm('JOVINA MARIA JOSE BORGES NETA'),
    norm('GLEIZIANE RODRIGUES FERRARI'): norm('GLEIZIANE RODRIGUES FERRARI MOREIRA'),
    norm('VANUZA COSMO DOS SANTOS'): norm('VANUZA COSME DOS SANTOS'),
    norm('LILIAN C LEGRAMANTI BARCELLO'): norm('LILIAN CRISTINA LEGRAMANTI BARCELLO'),
    norm('MARIA DA PENHA SEVERINO CHUBE'): norm('MARIA DA PENHA SEVIRINO CHUBE'),
    norm('ROZELI ROSA GERMANO'): norm('ROSELI ROSA GERMANO'),
    norm('ROSENILDA MARCILENE P DE OLIVEIRA'): norm('ROSENILDA MARCILENE PEREIRA DE OLIVEIRA'),
    norm('LEORIANE RUMAO MIRA MENDES'): norm('LEORIANE RUMAO MIRANDA MENDES'),
    norm('MARY KATE AMORIM AMONTEIO'): norm('MARY KATE AMORIM MONTEIRO'),
    norm('RAYARA SOUZA ANDRADE'): norm('RAYARA SOUZA ANDRADE CAMPOS'),
    norm('ROSELI GOMES RODRIGUES'): norm('ROSELI GOMES RODRIQUES NEVES'),
    norm('CLEIDE CLEUNICE DE FREITAS'): norm('CLEIDE CLEUNICE DE FREITAS SILVA'),
    norm('SILMARA DE SOUZA FLORES'): norm('SILMARA DE SOUZA FLORES SANTANA'),
    norm('FERNANDA RODRIGUES LIMA OLIVEIRA'): norm('FERNANDA RODRIGUES LIMA')
}

provimentos = {}
linhas_totais = 0
for idx_p, p in enumerate(reader.pages):
    txt = p.extract_text() or ''
    for line in txt.split('\n'):
        m = re.match(r'^(\d+\.\d+)\s*-\s*([A-Z\s\xC0-\xFF\.\-\']+?)\s+(\d{2}/\d{2}/\d{4})', line)
        if m:
            linhas_totais += 1
            nome = m.group(2).strip()
            nome = re.sub(r'\s*\d{2}/\d{2}/\d{4}.*$', '', nome).strip()
            m_cpf = re.search(r'(\d{3}\.\d{3}\.\d{3}\-\d{2})', line)
            cpf = m_cpf.group(1) if m_cpf else None
            all_dates = re.findall(r'(\d{2}/\d{2}/\d{4})', line)
            parsed_dates = [datetime.strptime(d, '%d/%m/%Y').date() for d in all_dates]
            n_nome = norm(nome)
            if n_nome:
                entry = provimentos.setdefault(n_nome, {
                    'nome_pdf': nome,
                    'cpf': cpf,
                    'datas_admissao': [],
                    'vigencias_inicio': [],
                    'vigencias_fim': [],
                    'linhas': []
                })
                entry['linhas'].append(line)
                if cpf and not entry['cpf']:
                    entry['cpf'] = cpf
                if len(parsed_dates) >= 1:
                    entry['datas_admissao'].append(parsed_dates[0])
                if len(parsed_dates) >= 3:
                    entry['vigencias_inicio'].append(parsed_dates[1])
                    entry['vigencias_fim'].append(parsed_dates[2])
                elif len(parsed_dates) == 2:
                    entry['vigencias_inicio'].append(parsed_dates[1])

print(f"Total de linhas provimento: {linhas_totais}")
print(f"Total de servidores únicos: {len(provimentos)}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

cands = c.execute('''
    SELECT id_candidato, nome_completo, classificacao_original, id_cargo, status_atual, edital_convocacao, cpf 
    FROM candidatos 
    WHERE id_certame = 4
''').fetchall()
print(f"Total de candidatos do Certame 4: {len(cands)}")

# Fim oficial de vigência do Seletivo 001/2024: 30/01/2026
cutoff_vigencia = date(2026, 1, 30)

# Limpar eventos de posse, exoneração e desistência anteriores do certame 4
c.execute('''
    DELETE FROM movimentacoes_candidato 
    WHERE id_candidato IN (SELECT id_candidato FROM candidatos WHERE id_certame = 4)
      AND tipo_evento IN ('TERMO_POSSE', 'EXONERACAO', 'TERMO_DESISTENCIA', 'DESISTENCIA_EXPRESSA', 'DESISTENCIA_TACITA')
''')

stats = {
    'EMPOSSADO (EXERCÍCIO)': 0,
    'EXCLUÍDO / EXONERADO': 0,
    'DESISTENTE / RENÚNCIA': 0,
    'CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)': 0,
    'CPFS_ATUALIZADOS': 0
}

for cand in cands:
    cid, nome, clf, id_cargo, st_atual, ed_conv, cpf_db = cand
    n_nome = norm(nome)
    n_mapped = alias_map.get(n_nome, n_nome)
    is_convocado = bool(ed_conv) or ('CONVOCADO' in (st_atual or '')) or ('DESISTENTE' in (st_atual or '')) or ('EMPOSSADO' in (st_atual or '')) or ('EXCLU' in (st_atual or ''))
    
    if n_mapped in provimentos:
        prov = provimentos[n_mapped]
        real_cpf = prov['cpf'] or cpf_db
        if prov['cpf'] and prov['cpf'] != cpf_db:
            stats['CPFS_ATUALIZADOS'] += 1
            
        all_start_dates = prov['datas_admissao'] + prov['vigencias_inicio']
        dt_posse = min(all_start_dates) if all_start_dates else date(2025, 2, 1)
        finais = prov['vigencias_fim']
        
        # Se não possui vigência fim explícita ou término em/após 30/01/2026:
        # Permaneceu ativo até o encerramento do certame
        if not finais or max(finais) >= cutoff_vigencia:
            novo_status = 'EMPOSSADO (EXERCÍCIO)'
            dt_posse_str = dt_posse.strftime('%Y-%m-%d')
            dt_exon_str = None
            stats['EMPOSSADO (EXERCÍCIO)'] += 1
            
            # Movimentação Posse
            c.execute('''
                INSERT INTO movimentacoes_candidato (id_candidato, tipo_evento, numero_processo_sei, data_registro, motivo_justificativa)
                VALUES (?, 'TERMO_POSSE', 'PROVIMENTO 2025/2026', ?, 'Termo de Posse e Início de Exercício conforme Relação Oficial de Provimento')
            ''', (cid, f"{dt_posse_str} 00:00:00.000000"))
        else:
            # Contrato encerrou durante a vigência do certame (ex: término do ano letivo 2025 em 19/12/2025)
            novo_status = 'EXCLUÍDO / EXONERADO'
            dt_posse_str = dt_posse.strftime('%Y-%m-%d')
            dt_exon = max(finais)
            dt_exon_str = dt_exon.strftime('%Y-%m-%d')
            stats['EXCLUÍDO / EXONERADO'] += 1
            
            # Movimentação Posse
            c.execute('''
                INSERT INTO movimentacoes_candidato (id_candidato, tipo_evento, numero_processo_sei, data_registro, motivo_justificativa)
                VALUES (?, 'TERMO_POSSE', 'PROVIMENTO 2025/2026', ?, 'Termo de Posse e Início de Exercício conforme Relação Oficial de Provimento')
            ''', (cid, f"{dt_posse_str} 00:00:00.000000"))
            
            # Movimentação Exoneração
            c.execute('''
                INSERT INTO movimentacoes_candidato (id_candidato, tipo_evento, numero_processo_sei, data_registro, motivo_justificativa)
                VALUES (?, 'EXONERACAO', 'TÉRMINO CONTRATUAL', ?, ?)
            ''', (cid, f"{dt_exon_str} 00:00:00.000000", f"Término de vigência de contrato temporário registrada em {dt_exon.strftime('%d/%m/%Y')}"))

        c.execute('''
            UPDATE candidatos 
            SET cpf = ?, status_atual = ?, data_posse = ?, data_exoneracao = ?, edital_desistencia = NULL
            WHERE id_candidato = ?
        ''', (real_cpf, novo_status, dt_posse_str, dt_exon_str, cid))

    else:
        # Não consta no relatório de provimento do período do certame
        if is_convocado:
            novo_status = 'DESISTENTE / RENÚNCIA'
            stats['DESISTENTE / RENÚNCIA'] += 1
            c.execute('''
                INSERT INTO movimentacoes_candidato (id_candidato, tipo_evento, numero_processo_sei, data_registro, motivo_justificativa)
                VALUES (?, 'TERMO_DESISTENCIA', 'NÃO COMPARECIMENTO', '2026-01-30 00:00:00.000000', 'Candidato convocado não compareceu para posse ou renunciou ao prazo legal')
            ''', (cid,))
            c.execute('''
                UPDATE candidatos 
                SET status_atual = ?, data_posse = NULL, data_exoneracao = NULL, edital_desistencia = 'RENÚNCIA TÁCITA (NÃO APRESENTAÇÃO)'
                WHERE id_candidato = ?
            ''', (novo_status, cid))
        else:
            novo_status = 'CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)'
            stats['CADASTRO RESERVA (AGUARDANDO CONVOCAÇÃO)'] += 1
            c.execute('''
                UPDATE candidatos 
                SET status_atual = ?, data_posse = NULL, data_exoneracao = NULL, edital_desistencia = NULL
                WHERE id_candidato = ?
            ''', (novo_status, cid))

conn.commit()
conn.close()

print("Atualização com o novo arquivo concluída com sucesso!")
for k, v in stats.items():
    print(f"  {k}: {v}")
