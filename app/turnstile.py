"""Verificacao anti-robo opcional com o Cloudflare Turnstile (gratuito).

So fica ativa se TURNSTILE_SITE_KEY e TURNSTILE_SECRET_KEY estiverem no .env.
Funciona em qualquer hospedagem, nao precisa que o site esteja na Cloudflare.
Sem as chaves, o site funciona normalmente, sem a verificacao.
"""
import requests
from flask import current_app

URL_VERIFICACAO = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT = 5


def ativo():
    return bool(
        current_app.config.get("TURNSTILE_SITE_KEY")
        and current_app.config.get("TURNSTILE_SECRET_KEY")
    )


def verificar(resposta_do_widget, ip):
    """True se o Turnstile confirma que quem enviou o formulario nao e um robo.

    Se o Turnstile estiver desligado, devolve True. Se a Cloudflare nao
    responder, devolve False (o cliente tenta de novo), para que ninguem
    consiga pular a verificacao.
    """
    if not ativo():
        return True
    resposta_do_widget = (resposta_do_widget or "").strip()
    if not resposta_do_widget or len(resposta_do_widget) > 2048:
        return False
    try:
        r = requests.post(
            URL_VERIFICACAO,
            data={
                "secret": current_app.config["TURNSTILE_SECRET_KEY"],
                "response": resposta_do_widget,
                "remoteip": ip,
            },
            timeout=TIMEOUT,
        )
        return bool(r.ok and r.json().get("success") is True)
    except (requests.RequestException, ValueError):
        current_app.logger.warning("Nao consegui consultar o Cloudflare Turnstile.")
        return False
