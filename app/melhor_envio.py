"""Integracao com o Melhor Envio (cotacao de frete).

A autenticacao e OAuth2: voce autoriza o aplicativo uma vez no painel e o
site guarda o token no banco. O token vale 30 dias e e renovado sozinho.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from flask import current_app

from app.db import get_db

NOME = "melhor_envio"
ESCOPO = "shipping-calculate"
MARGEM_RENOVACAO = timedelta(days=5)
TIMEOUT = 15
CHAVES_OBRIGATORIAS = (
    "MELHOR_ENVIO_CLIENT_ID",
    "MELHOR_ENVIO_CLIENT_SECRET",
    "MELHOR_ENVIO_REDIRECT_URI",
    "CEP_ORIGEM",
    "CONTATO_API_EMAIL",
)


class ErroMelhorEnvio(Exception):
    """Falha ao falar com o Melhor Envio (a mensagem pode ser mostrada ao administrador)."""


class NaoConectado(ErroMelhorEnvio):
    """A loja ainda nao foi autorizada (ou a autorizacao expirou)."""


def _cfg(chave):
    return current_app.config[chave]


def agora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def base_url():
    if _cfg("MELHOR_ENVIO_AMBIENTE") == "sandbox":
        return "https://sandbox.melhorenvio.com.br"
    return "https://melhorenvio.com.br"


def _cabecalhos():
    return {
        "Accept": "application/json",
        # O Melhor Envio exige o nome da aplicacao e um e-mail de contato
        "User-Agent": f"Portal Lab Loja ({_cfg('CONTATO_API_EMAIL')})",
    }


def faltando():
    """Nomes das configuracoes do .env que ainda nao foram preenchidas."""
    return [chave for chave in CHAVES_OBRIGATORIAS if not _cfg(chave)]


# ---------------------------------------------------------------
# Autorizacao (OAuth2)
# ---------------------------------------------------------------
def url_de_autorizacao(state):
    parametros = {
        "client_id": _cfg("MELHOR_ENVIO_CLIENT_ID"),
        "redirect_uri": _cfg("MELHOR_ENVIO_REDIRECT_URI"),
        "response_type": "code",
        "state": state,
        "scope": ESCOPO,
    }
    return f"{base_url()}/oauth/authorize?{urlencode(parametros)}"


def extrair_retorno(texto):
    """Le o endereco da pagina para onde o Melhor Envio levou o navegador.

    Retorna (codigo, state, erro). Os tres sao strings vazias se nao existirem.
    """
    consulta = parse_qs(urlparse((texto or "").strip()).query)
    return (
        (consulta.get("code") or [""])[0],
        (consulta.get("state") or [""])[0],
        (consulta.get("error") or [""])[0],
    )


class _Recusado(ErroMelhorEnvio):
    """O Melhor Envio respondeu 400/401 ao pedir o token."""


def _pedir_token(corpo):
    try:
        resposta = requests.post(
            f"{base_url()}/oauth/token", data=corpo, headers=_cabecalhos(), timeout=TIMEOUT
        )
    except requests.RequestException:
        raise ErroMelhorEnvio(
            "Não consegui falar com o Melhor Envio agora. Tente de novo em instantes."
        )

    if resposta.status_code in (400, 401):
        raise _Recusado(
            "O Melhor Envio recusou a autorização. Confira o Client ID, o Secret e o "
            "endereço de retorno cadastrados no aplicativo."
        )
    if resposta.status_code != 200:
        raise ErroMelhorEnvio(f"O Melhor Envio respondeu com erro ({resposta.status_code}).")

    try:
        dados = resposta.json()
        return (
            str(dados["access_token"]),
            str(dados["refresh_token"]),
            int(dados.get("expires_in", 2592000)),
        )
    except (ValueError, KeyError, TypeError):
        raise ErroMelhorEnvio("Resposta inesperada do Melhor Envio ao pedir o token.")


def _guardar(cur, access, refresh, expira_em_segundos):
    expira = agora_utc() + timedelta(seconds=expira_em_segundos)
    cur.execute(
        """
        INSERT INTO integracoes (nome, access_token, refresh_token, expira_em, atualizado_em)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (nome) DO UPDATE
        SET access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expira_em = EXCLUDED.expira_em,
            atualizado_em = NOW()
        """,
        (NOME, access, refresh, expira),
    )


def trocar_codigo(codigo):
    """Troca o codigo recebido no retorno da autorizacao pelo primeiro token."""
    access, refresh, segundos = _pedir_token(
        {
            "grant_type": "authorization_code",
            "client_id": _cfg("MELHOR_ENVIO_CLIENT_ID"),
            "client_secret": _cfg("MELHOR_ENVIO_CLIENT_SECRET"),
            "redirect_uri": _cfg("MELHOR_ENVIO_REDIRECT_URI"),
            "code": codigo,
        }
    )
    db = get_db()
    with db.cursor() as cur:
        _guardar(cur, access, refresh, segundos)
    db.commit()


def desconectar():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM integracoes WHERE nome = %s", (NOME,))
    db.commit()


def _renovar(forcar):
    """Renova o token. A linha fica travada para nao haver duas renovacoes ao mesmo tempo."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT access_token, refresh_token, expira_em FROM integracoes WHERE nome = %s FOR UPDATE",
            (NOME,),
        )
        linha = cur.fetchone()
        if linha is None:
            db.rollback()
            raise NaoConectado("A loja ainda não está conectada ao Melhor Envio.")

        if not forcar and linha["expira_em"] - agora_utc() > MARGEM_RENOVACAO:
            db.rollback()  # outra requisicao ja renovou
            return linha["access_token"]

        try:
            access, refresh, segundos = _pedir_token(
                {
                    "grant_type": "refresh_token",
                    "client_id": _cfg("MELHOR_ENVIO_CLIENT_ID"),
                    "client_secret": _cfg("MELHOR_ENVIO_CLIENT_SECRET"),
                    "refresh_token": linha["refresh_token"],
                }
            )
        except _Recusado:
            cur.execute("DELETE FROM integracoes WHERE nome = %s", (NOME,))
            db.commit()
            raise NaoConectado(
                "A conexão com o Melhor Envio expirou. Conecte de novo no painel."
            )
        except ErroMelhorEnvio:
            db.rollback()
            raise

        _guardar(cur, access, refresh, segundos)
    db.commit()
    return access


def obter_token(forcar_renovacao=False):
    with get_db().cursor() as cur:
        cur.execute(
            "SELECT access_token, expira_em FROM integracoes WHERE nome = %s", (NOME,)
        )
        linha = cur.fetchone()
    if linha is None:
        raise NaoConectado("A loja ainda não está conectada ao Melhor Envio.")
    if not forcar_renovacao and linha["expira_em"] - agora_utc() > MARGEM_RENOVACAO:
        return linha["access_token"]
    return _renovar(forcar_renovacao)


def estado():
    """Situacao da integracao para o painel (nunca devolve segredos)."""
    with get_db().cursor() as cur:
        cur.execute("SELECT expira_em FROM integracoes WHERE nome = %s", (NOME,))
        linha = cur.fetchone()
    return {
        "faltando": faltando(),
        "conectado": linha is not None,
        "expira_em": linha["expira_em"] if linha else None,
        "ambiente": _cfg("MELHOR_ENVIO_AMBIENTE"),
        "redirect_uri": _cfg("MELHOR_ENVIO_REDIRECT_URI"),
        "cep_origem": _cfg("CEP_ORIGEM"),
    }


# ---------------------------------------------------------------
# Cotacao de frete
# ---------------------------------------------------------------
def _post_cotacao(token, corpo):
    try:
        return requests.post(
            f"{base_url()}/api/v2/me/shipment/calculate",
            json=corpo,
            headers={
                **_cabecalhos(),
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise ErroMelhorEnvio("Não consegui falar com o Melhor Envio agora.")


def _normalizar(dados):
    if not isinstance(dados, list):
        raise ErroMelhorEnvio("Resposta inesperada do Melhor Envio na cotação.")

    opcoes = []
    for item in dados:
        if not isinstance(item, dict) or item.get("error"):
            continue  # servico indisponivel para este envio
        try:
            ident = int(item["id"])
            valor = Decimal(str(item.get("custom_price") or item.get("price")))
            prazo = item.get("custom_delivery_time") or item.get("delivery_time")
            prazo = int(prazo) if prazo is not None else None
        except (KeyError, ValueError, TypeError, InvalidOperation):
            continue
        empresa = (item.get("company") or {}).get("name") or ""
        opcoes.append(
            {
                "id": ident,
                "nome": str(item.get("name") or ""),
                "empresa": str(empresa),
                "valor": valor.quantize(Decimal("0.01")),
                "prazo": prazo,
            }
        )
    opcoes.sort(key=lambda o: (o["valor"], o["prazo"] or 999))
    return opcoes


def cotar(cep_destino, produtos):
    """Cota o frete. `produtos` usa peso em kg e medidas em cm (formato da API)."""
    if faltando():
        raise NaoConectado("Configure o Melhor Envio no arquivo .env.")

    corpo = {
        "from": {"postal_code": _cfg("CEP_ORIGEM")},
        "to": {"postal_code": cep_destino},
        "products": produtos,
        "options": {"receipt": False, "own_hand": False},
    }

    resposta = _post_cotacao(obter_token(), corpo)
    if resposta.status_code == 401:  # token recusado: renova uma vez e tenta de novo
        resposta = _post_cotacao(obter_token(forcar_renovacao=True), corpo)

    if resposta.status_code == 401:
        raise NaoConectado("O Melhor Envio recusou o acesso. Conecte de novo no painel.")
    if resposta.status_code != 200:
        detalhe = ""
        try:
            detalhe = str(resposta.json().get("message") or "")[:200]
        except (ValueError, AttributeError):
            pass
        raise ErroMelhorEnvio(
            f"O Melhor Envio não conseguiu cotar ({resposta.status_code}). {detalhe}".strip()
        )

    try:
        dados = resposta.json()
    except ValueError:
        raise ErroMelhorEnvio("Resposta inesperada do Melhor Envio na cotação.")
    return _normalizar(dados)
