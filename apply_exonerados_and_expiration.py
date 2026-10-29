import sqlite3
import pypdf
import re
import unicodedata
from datetime import datetime

def normalize_text(text):
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9\s]', ' ', text.upper()).strip()

def parse_date(d_str):
    try:
        parts = d_str.split('/')
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    except:
        return None

pdf_path = r'C:\Users\Jansen.Pinho\.gemini\antigravity\brain\ee80db35-aadb-4571-a01d-c8624c58d26c\.user_uploaded\media_1793275426311.pdf'
print(f"Reading PDF: {pdf_path}")
reader = pypdf.PdfReader(pdf_path)
date_pattern = re.compile(r'(\d{2}/\d{2}/\d{4})')

pdf_records = []
for p_idx, page in enumerate(reader.pages):
    txt = page.extract_text()
    for raw_line in txt.splitlines():
        line = raw_line.strip()
        if not line or 'ESTADO DE MATO' in line or 'PREFEITURA MUNICIPAL' in line or 'PONTES E LACERDA' in line or 'RELA' in line or 'MATRICULA' in line:
            continue
        if 'ARRelacao_Exonerados' in line or 'Pgina:' in line or '53 /' in line:
            continue
        date_match = date_pattern.search(line)
        if not date_match:
            continue
        m = re.search(r'\d+/\s*\d+\s*([A-Za-z\u00C0-\u00FF\s\.\-]+)$', line)
        if m:
            nome = m.group(1).strip()
            cargo_match = re.search(r'(\d+\s*-\s*[A-Z\s\-]+?)\s+\d{2}/\d{2}/\d{4}', line)
            cargo_str = cargo_match.group(1).strip() if cargo_match else ""
            tipo_match = re.search(r'^\d+\.\d+\s+(.*?)\s*\d+\s*-', line)
            tipo_str = tipo_match.group(1).strip() if tipo_match else ""
            pdf_records.append({
                'nome': nome,
                'nome_norm': normalize_text(nome),
                'data': parse_date(date_match.group(1)),
                'cargo': cargo_str,
                'cargo_norm': normalize_text(cargo_str),
                'tipo': tipo_str
            })

print(f"Total parsed records from PDF: {len(pdf_records)}")

conn = sqlite3.connect('auditoria_pessoal.db')
c = conn.cursor()

# Backup table before applying
c.execute("CREATE TABLE IF NOT EXISTS candidatos_backup_before_pdf_exoneracao AS SELECT * FROM candidatos")

c.execute("""
    SELECT c.id_candidato, c.nome_completo, cg.nome_cargo, ct.modalidade, ct.numero_certame, ct.ano, 
           c.data_posse, c.data_exoneracao, c.status_atual
    FROM candidatos c
    LEFT JOIN cargos cg ON c.id_cargo = cg.id_cargo
    LEFT JOIN certames_abertura ct ON c.id_certame = ct.id_certame
    WHERE c.data_posse IS NOT NULL
""")
candidates = c.fetchall()

updated_from_pdf = 0
updated_from_seletivo_term = 0

for cand in candidates:
    cid, cnome, ccargo, cmod, cnum, cano, cposse, cexon, cstat = cand
    cnorm = normalize_text(cnome)
    
    # Check PDF match
    matches = [r for r in pdf_records if r['nome_norm'] == cnorm]
    valid_matches = [m for m in matches if m['data'] >= cposse]
    
    new_exon = cexon
    new_stat = cstat
    
    if valid_matches:
        # Match cargo keyword
        cand_cargo_keywords = [w for w in normalize_text(ccargo).split() if len(w) > 3]
        best_match = None
        for vm in valid_matches:
            if any(k in vm['cargo_norm'] for k in cand_cargo_keywords):
                best_match = vm
                break
        if not best_match:
            best_match = valid_matches[0]
            
        new_exon = best_match['data']
        new_stat = 'EXCLUÍDO / EXONERADO'
        updated_from_pdf += 1
    elif cmod == 'PROCESSO_SELETIVO_SIMPLIFICADO':
        # Seletivo statutory 1-year contract expiration rule
        if cano == 2022:
            if cposse < '2023-01-01':
                new_exon = '2022-12-16'
            else:
                new_exon = '2023-12-12'
            new_stat = 'EXCLUÍDO / EXONERADO'
            updated_from_seletivo_term += 1
        elif cano == 2023:
            new_exon = '2024-12-06'
            new_stat = 'EXCLUÍDO / EXONERADO'
            updated_from_seletivo_term += 1
        elif cano == 2024 and cposse < '2026-01-01':
            new_exon = '2025-12-19'
            new_stat = 'EXCLUÍDO / EXONERADO'
            updated_from_seletivo_term += 1

    if new_exon != cexon or new_stat != cstat:
        c.execute("""
            UPDATE candidatos 
            SET data_exoneracao = ?, status_atual = ?
            WHERE id_candidato = ?
        """, (new_exon, new_stat, cid))

conn.commit()
print(f"Database successfully updated!")
print(f"Total updated: {updated_from_pdf + updated_from_seletivo_term}")
print(f"  - Updated from PDF: {updated_from_pdf}")
print(f"  - Updated from Seletivo 1-year expiration: {updated_from_seletivo_term}")

# Verify Iara and Eliana
c.execute("""
    SELECT c.id_candidato, c.nome_completo, cg.nome_cargo, ct.modalidade, ct.numero_certame, ct.ano, 
           c.data_posse, c.data_exoneracao, c.status_atual
    FROM candidatos c
    LEFT JOIN cargos cg ON c.id_cargo = cg.id_cargo
    LEFT JOIN certames_abertura ct ON c.id_certame = ct.id_certame
    WHERE c.nome_completo LIKE '%IARA%ALMEIDA%' OR c.nome_completo LIKE '%ELIANA%VITAL%'
""")
rows = c.fetchall()
print("\n--- VERIFICATION OF IARA AND ELIANA IN DATABASE ---")
for r in rows:
    print(r)

conn.close()
