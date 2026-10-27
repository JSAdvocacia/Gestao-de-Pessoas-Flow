@echo off
chcp 65001 > nul
title Sistema de Auditoria de Pessoal - Publicação Online Permanente
echo =========================================================================
echo  INICIANDO SISTEMA DE AUDITORIA DE PESSOAL (SIAP) - LINKS ONLINE
echo =========================================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando servidor local FastAPI...
netstat -ano | findstr :8000 | findstr LISTENING > nul
if %errorlevel% neq 0 (
    echo [INFO] Iniciando servidor FastAPI local na porta 8000...
    start /b "" uvicorn main:app --host 0.0.0.0 --port 8000
    timeout /t 3 /nobreak > nul
) else (
    echo [OK] Servidor FastAPI local já está ativo na porta 8000.
)

echo.
echo [2/3] Iniciando Link Fixo Permanente (siap-auditoria-pessoal.loca.lt)...
start /b "" cmd /c npx --yes localtunnel --port 8000 --subdomain siap-auditoria-pessoal

echo.
echo [3/3] Iniciando Link Direto Cloudflare...
if exist cloudflared.log del /f /q cloudflared.log
start /b "" "%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000 --logfile cloudflared.log

echo Aguardando inicialização dos túneis...
timeout /t 5 /nobreak > nul

echo.
echo =========================================================================
echo  [SUCESSO] SISTEMA PUBLICADO NA INTERNET!
echo =========================================================================
echo.
echo  1. LINK FIXO PERMANENTE (Não muda de nome):
echo     https://siap-auditoria-pessoal.loca.lt
echo.
echo  2. LINK DIRETO CLOUDFLARE:
powershell -Command "$m = Select-String -Path 'cloudflared.log' -Pattern 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) { Write-Host '    ' ([regex]::Match($m.Line, 'https://[a-zA-Z0-9-]+\.trycloudflare\.com').Value) }"
echo.
echo =========================================================================
echo Abrindo o link fixo no seu navegador...
start "" "https://siap-auditoria-pessoal.loca.lt"

echo.
echo Mantenha esta janela aberta para manter o sistema online.
pause > nul
