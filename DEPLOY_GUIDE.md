# Guia de Publicação e Link Permanente Gratuito do Sistema

Este guia explica as soluções disponíveis para você ter um **link permanente e 100% gratuito** acessível para qualquer usuário na internet.

---

## 🌟 Solução 1: Nuvem 24/7 Permanente (Mais Recomendada - Totalmente Gratuita)

Nesta opção, o sistema fica hospedado nos servidores da **Render.com** (plano gratuito), o que significa que:
- O link é **100% permanente** (ex: `https://siap-gestao-de-pessoas.onrender.com`).
- **Nunca muda de endereço.**
- Funciona 24 horas por dia, 7 dias por semana, **mesmo com o seu computador pessoal desligado**.
- Possui certificado SSL/HTTPS oficial automático sem telas intermediárias.

### Passo a passo (2 minutos):
1. Acesse **[https://dashboard.render.com](https://dashboard.render.com)** e crie uma conta gratuita (pode entrar com sua conta do GitHub).
2. Clique no botão azul **"New +"** no canto superior direito e selecione **"Web Service"**.
3. Escolha **"Build and deploy from a Git repository"** e conecte o repositório do projeto:
   `https://github.com/JSAdvocacia/Gestao-de-Pessoas-Flow`
4. O Render detectará automaticamente o arquivo `render.yaml` já configurado no projeto:
   - **Name:** `siap-gestao-de-pessoas`
   - **Environment:** `Python 3`
   - **Plan:** `Free`
5. Clique em **"Deploy Web Service"**.
6. Pronto! O Render disponibilizará o link definitivo e permanente:
   👉 `https://siap-gestao-de-pessoas.onrender.com`

---

## 🚀 Solução 2: Link Permanente no seu Próprio Computador (Localtunnel)

Se você preferir rodar o sistema no seu computador, já configuramos e ativamos um **subdomínio fixo permanente** via Localtunnel:

- 🌐 **Link Fixo:** **[https://siap-auditoria-pessoal.loca.lt](https://siap-auditoria-pessoal.loca.lt)**
- Este link **não muda de nome**, pois o endereço `siap-auditoria-pessoal` está reservado no comando.

*Observação sobre o primeiro acesso:* No primeiro acesso pelo navegador, o Localtunnel exibe uma tela de proteção antifraude com um botão para submeter o IP público. Basta clicar nele para entrar diretamente no sistema.

---

## ⚡ Solução 3: Link Cloudflare Rápido (Sem Telas Intermediárias)

Enquanto o computador estiver ligado, o Cloudflare Tunnel também permanece ativo sem qualquer tela intermediária:
- 🌐 **Link Cloudflare:** **[https://bulletin-estimates-ministries-symbol.trycloudflare.com](https://bulletin-estimates-ministries-symbol.trycloudflare.com)**
