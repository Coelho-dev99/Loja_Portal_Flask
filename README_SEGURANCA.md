# Como rodar com segurança

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

## Depois de atualizar
Rode `pip install -r requirements.txt` (entraram `Flask-WTF` e `waitress`).
