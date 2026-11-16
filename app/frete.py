"""Frete do carrinho: monta os dados para o Melhor Envio e guarda o resultado."""
import json
import time

from flask import current_app

from app import melhor_envio
from app.db import get_db

CACHE_SEGUNDOS = 600
MAX_OPCOES = 6
_cache = {}


def assinatura(itens):
    """Resumo do carrinho, para saber se ele mudou entre a cotacao e o pedido."""
    return sorted((i["produto_id"], i["quantidade"], bool(i.get("descricao"))) for i in itens)


def _produtos_para_cotacao(itens):
    """Retorna (produtos, estimado). produtos e None se faltar peso ou medidas."""
    ids = sorted({i["produto_id"] for i in itens})
    with get_db().cursor() as cur:
        cur.execute(
            """
            SELECT id, preco, modalidade, peso_g, altura_cm, largura_cm, comprimento_cm
            FROM produtos WHERE id = ANY(%s)
            """,
            (ids,),
        )
        por_id = {p["id"]: p for p in cur.fetchall()}

    quantidades = {}
    for item in itens:
        quantidades[item["produto_id"]] = quantidades.get(item["produto_id"], 0) + item["quantidade"]

    produtos = []
    estimado = False
    for produto_id in sorted(quantidades):
        p = por_id.get(produto_id)
        if p is None or None in (p["peso_g"], p["altura_cm"], p["largura_cm"], p["comprimento_cm"]):
            return None, False
        if p["modalidade"] == "personalizavel":
            estimado = True
        produtos.append(
            {
                "id": f"p{produto_id}",
                "width": float(p["largura_cm"]),
                "height": float(p["altura_cm"]),
                "length": float(p["comprimento_cm"]),
                "weight": round(p["peso_g"] / 1000, 3),
                "insurance_value": float(p["preco"]),
                "quantity": quantidades[produto_id],
            }
        )
    return produtos, estimado


def _confirmar(motivo):
    return {"status": "confirmar", "motivo": motivo, "estimado": False, "opcoes": []}


def cotar_carrinho(itens, cep):
    """Cota o frete do carrinho. Nunca levanta erro: no pior caso o frete
    fica 'a confirmar' e o pedido segue normalmente."""
    if not itens:
        return _confirmar("carrinho_vazio")
    if melhor_envio.faltando():
        return _confirmar("nao_configurado")

    produtos, estimado = _produtos_para_cotacao(itens)
    if produtos is None:
        return _confirmar("sem_medidas")

    chave = cep + json.dumps(produtos, sort_keys=True)
    agora = time.monotonic()
    guardado = _cache.get(chave)
    if guardado and guardado[0] > agora:
        return guardado[1]

    try:
        opcoes = melhor_envio.cotar(cep, produtos)
    except melhor_envio.NaoConectado:
        return _confirmar("nao_conectado")
    except melhor_envio.ErroMelhorEnvio as erro:
        current_app.logger.warning("Cotacao de frete falhou: %s", erro)
        return _confirmar("indisponivel")

    if not opcoes:
        return _confirmar("sem_opcoes")

    resultado = {
        "status": "ok",
        "motivo": None,
        "estimado": estimado,
        "opcoes": opcoes[:MAX_OPCOES],
    }
    if len(_cache) > 500:
        _cache.clear()
    _cache[chave] = (agora + CACHE_SEGUNDOS, resultado)
    return resultado


def limpar_cache():
    _cache.clear()
