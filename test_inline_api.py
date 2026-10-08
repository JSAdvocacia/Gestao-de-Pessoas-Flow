import requests

s = requests.Session()
s.cookies.set('user_session', 'prof.jan100@gmail.com')

r = s.get('http://127.0.0.1:8000/certames/1/acompanhamento')
print('Page fetch status:', r.status_code, 'len:', len(r.text))

# Test 1: Set candidate 26 as EMPOSSADO with data_posse 2026-10-07
payload = {
    'edital_convocacao': '005/2022',
    'data_posse': '2026-10-07',
    'data_exoneracao': '',
    'edital_desistencia': '',
    'sub_judice': 'NÃO'
}
r_api = s.post('http://127.0.0.1:8000/api/candidatos/26/atualizar-provimento', json=payload)
print('\nTest 1 (EMPOSSADO) status:', r_api.status_code)
print('API json:', r_api.json())

# Test 2: Set candidate 26 as EXCLUÍDO / EXONERADO with data_exoneracao 2026-10-08
payload2 = {
    'edital_convocacao': '005/2022',
    'data_posse': '2026-10-07',
    'data_exoneracao': '2026-10-08',
    'edital_desistencia': '',
    'sub_judice': 'NÃO'
}
r_api2 = s.post('http://127.0.0.1:8000/api/candidatos/26/atualizar-provimento', json=payload2)
print('\nTest 2 (EXCLUÍDO / EXONERADO) status:', r_api2.status_code)
print('API json:', r_api2.json())
