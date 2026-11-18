# Como rodar com segurança

Testado com Python 3.13, Flask 3.1, Flask-WTF 1.3, PostgreSQL 16.

## No seu computador (desenvolvimento)
No `.env` local coloque `FLASK_DEBUG=1` e rode `python run.py`.
Isso liga o modo debug e deixa os cookies funcionarem em `http://localhost`.

## No servidor (produção)
1. **Não** defina `FLASK_DEBUG` nem `COOKIES_SEGUROS` no `.env` do servidor.
2. Gere a `SECRET_KEY` (o site não inicia sem ela):
   `python -c "import secrets; print(secrets.token_hex(32))"`
3. Gere a senha do painel (mínimo 12 caracteres): `python gerar_hash.py`
4. Rode com o servidor de produção, **não** com o `run.py`:
   - Windows ou Linux: `python servidor.py`
   - Linux: `gunicorn -w 1 --threads 8 -b 127.0.0.1:8000 run:app`
   (use 1 processo: o limitador de tentativas guarda a contagem na memória)
5. Publique sempre com **HTTPS** (os cookies só funcionam assim).

## Atrás de proxy (`PROXY_MODO` no .env)
- `nenhum` (padrão): o site é acessado direto.
- `proxy`: há UM proxy confiável na frente (nginx, Render, Railway...) que
  envia `X-Forwarded-For` e `X-Forwarded-Proto`.
- `cloudflare`: o site fica atrás da Cloudflare (proxy ou Tunnel). Usa o IP do
  cabeçalho `CF-Connecting-IP`.

Use `proxy` ou `cloudflare` **somente** se ninguém consegue acessar o site sem
passar por eles. Caso contrário, um visitante poderia falsificar o IP e
escapar dos limites de tentativas.

## Banco de dados
1. **Usuário só da loja:** edite `sql/criar_usuario_loja.sql` (troque a senha),
   rode no pgAdmin como administrador, conectado no banco da loja, e use
   `DB_USER=loja_app` no `.env`. Esse usuário só lê e grava dados: não cria,
   não apaga e não altera tabelas. As migrações continuam sendo rodadas por você.
2. **Remover o CPF (não usado):** rode `sql/migracao_05.sql` uma vez. Se algum
   cliente tiver CPF gravado, ele para sem apagar nada.
3. **Banco em outro servidor (nuvem)?** Use `DB_SSLMODE=require` no `.env`.
4. **Nunca exponha a porta 5432 à internet** e guarde backups do banco em lugar
   privado (nunca no GitHub): eles têm dados de clientes.

## Anti-robô no checkout (opcional)
Cloudflare Turnstile, gratuito, funciona em qualquer hospedagem.
Crie o widget no painel da Cloudflare (Turnstile) com o domínio do seu site e
coloque `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` no `.env`.
Sem as chaves, o site funciona sem a verificação. Depois de ligar, faça um
pedido de teste no navegador para confirmar que o quadradinho aparece.
Independente disso, o checkout limita pedidos por IP (10 por hora) e por
telefone (5 por hora).

## Privacidade (LGPD)
- A página `/privacidade` é um **rascunho** baseado no que o site faz hoje.
  Leia, ajuste (prazo de guarda, seus dados como responsável, forma de envio)
  e, se puder, peça uma conferência de quem entenda de LGPD.
- Quando um cliente pedir para apagar os dados, abra o cliente no painel e use
  **Remover dados pessoais**. Nome, telefone, Instagram, endereço, observações e
  descrições de peças personalizadas são apagados; pedidos, valores e datas ficam,
  sem identificar a pessoa. Cidade e estado ficam (para você saber onde vende);
  para apagar também, mude `MANTER_CIDADE_ESTADO` em `app/routes/admin_clientes.py`.
  Só funciona quando todos os pedidos do cliente estão concluídos ou cancelados.

## Cabeçalhos de segurança (CSP) — leia antes de mexer em layout e imagens
O site agora envia uma política (`app/seguranca.py`) que o navegador cumpre:
- **Imagens** só carregam do próprio site (`app/static/...`) ou de dados embutidos.
  Imagem de outro endereço (link do Instagram, Google Drive etc.) **não aparece**.
  Baixe a imagem e coloque em `app/static/`.
- **Scripts**: todo `<script>` escrito no HTML precisa de `nonce="{{ csp_nonce }}"`.
  Não use `onclick=""`, `onsubmit=""` e parecidos. Para confirmações no painel use
  `data-confirmar="Pergunta?"` no `<form>` (veja `app/static/admin.js`).
- **Estilos**: nada de `style="..."` nas tags nem `<style>` no HTML. Use os arquivos
  `.css` em `app/static/`.
- **Fontes, bibliotecas ou serviços externos** (Google Fonts, Analytics, chat...)
  são bloqueados até serem liberados em `app/seguranca.py`.
Se algo "sumir" depois de uma mudança, abra o console do navegador (F12): ele diz
qual regra bloqueou.

## Fotos dos produtos
As fotos enviadas pelo painel ficam em `app/static/uploads/`, que não vai para o
GitHub. Em hospedagem que apaga arquivos a cada atualização, use um disco
persistente e faça backup dessa pasta.

## Depois de atualizar
Rode `pip install -r requirements.txt`. De vez em quando, rode
`pip list --outdated` para ver atualizações de segurança.
