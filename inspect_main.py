import re

with open('main.py', encoding='utf-8') as f:
    lines = f.readlines()

print("--- DB MODELS ---")
for i, line in enumerate(lines):
    if line.strip().startswith('class ') and '(Base)' in line:
        print(f"Line {i+1}: {line.strip()}")

print("\n--- FASE OFICIAL & PARECER & ACOMPANHAMENTO ENDPOINTS ---")
for i, line in enumerate(lines):
    if '@app.' in line and any(k in line for k in ['fase-oficial', 'parecer', 'acompanhamento', 'lotacionograma']):
        print(f"Line {i+1}: {line.strip()}")
        for j in range(i+1, min(i+6, len(lines))):
            if lines[j].strip().startswith('def '):
                print(f"   -> {lines[j].strip()}")
