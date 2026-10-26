@echo off
chcp 65001 > nul
title Sistema de Auditoria de Pessoal - Publicação Online
echo =========================================================================
echo  INICIANDO SISTEMA DE AUDITORIA DE PESSOAL E PUBLICACAO NA INTERNET
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
echo [2/3] Iniciando túnel seguro HTTPS na Internet (Cloudflare Tunnel)...
if exist cloudflared.log del /f /q cloudflared.log

start /b "" "%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000 --logfile cloudflared.log

echo Aguardando geração do link público...
set /a tentativas=0

:LOOP_BUSCA_URL
timeout /t 2 /nobreak > nul
set /a tentativas+=1

powershell -Command "$m = Select-String -Path 'cloudflared.log' -Pattern 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) { $url = [regex]::Match($m.Line, 'https://[a-zA-Z0-9-]+\.trycloudflare\.com').Value; Set-Content -Path 'LINK_ACESSO_INTERNET.txt' -Value $url; Write-Host $url; exit 0 } else { exit 1 }" > temp_url.txt

if %errorlevel% equ 0 (
    set /p PUBLIC_URL=<temp_url.txt
    del temp_url.txt
    goto SUCESSO
)

if %tentativas% geq 15 (
    echo [ERRO] Tempo limite para obter o link público. Verifique o arquivo cloudflared.log.
    pause
    exit /b 1
)
goto LOOP_BUSCA_URL

:SUCESSO
echo.
echo =========================================================================
echo  [SUCESSO] SISTEMA PUBLICADO NA INTERNET!
echo =========================================================================
echo.
echo  Link de Acesso Público Seguro (HTTPS):
echo  %PUBLIC_URL%
echo.
echo  O link acima foi salvo em: LINK_ACESSO_INTERNET.txt
echo  Compartilhe esse link com qualquer usuário em qualquer dispositivo!
echo =========================================================================
echo.
echo Abrindo o sistema no seu navegador padrão...
start "" "%PUBLIC_URL%"

echo.
echo Mantenha esta janela aberta para manter o sistema online.
echo Pressione Ctrl+C para encerrar o túnel.
pause > nul
