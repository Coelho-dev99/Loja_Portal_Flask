"""Aviso de pedido novo no Telegram.

Precisa das variáveis de ambiente (no .env local e no Environment do Render):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Se alguma estiver faltando ou o Telegram falhar, o aviso é ignorado e o
pedido do cliente continua normalmente.
"""
import logging
import os
import threading

import requests

log = logging.getLogger(__name__)


def _brl(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _enviar(texto):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram não configurado (faltam token ou chat id).")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto[:4000]},
            timeout=8,
        )
        if not resp.ok:
            log.warning("Telegram respondeu %s", resp.status_code)
    except requests.RequestException as erro:
        # Não registra o erro completo: a URL dele contém o token do bot
        log.warning("Falha ao enviar aviso no Telegram (%s).", type(erro).__name__)


def montar_mensagem(pedido_id, dados, resumo_carrinho, frete_escolhido=None):
    """Monta o texto do aviso a partir dos dados já validados do checkout."""
    linhas = [f"🛒 Novo pedido #{pedido_id}", ""]

    linhas.append(f"👤 {dados['nome']}")
    linhas.append(f"📞 {dados['telefone']}")
    if dados.get("instagram"):
        linhas.append(f"📸 @{dados['instagram']}")
    linhas.append(f"📍 {dados['cidade']}/{dados['estado']}")

    linhas += ["", "Itens:"]
    for linha in resumo_carrinho["linhas"]:
        item = linha["item"]
        produto = linha["produto"]
        nome = produto["nome"] if produto else "Produto"
        if item.get("descricao"):
            descricao = item["descricao"].strip().replace("\n", " ")[:120]
            linhas.append(f"• {item['quantidade']}x {nome} (personalizado): {descricao}")
        else:
            linhas.append(f"• {item['quantidade']}x {nome}")

    subtotal = resumo_carrinho["subtotal"]
    if resumo_carrinho["tem_personalizado"]:
        if subtotal > 0:
            linhas.append(f"\n💰 Peças fechadas: R$ {_brl(subtotal)} (+ personalizadas a combinar)")
        else:
            linhas.append("\n💰 Valor: a combinar no chat")
    else:
        linhas.append(f"\n💰 Peças: R$ {_brl(subtotal)}")

    if frete_escolhido is not None:
        servico = f"{frete_escolhido['empresa']} {frete_escolhido['nome']}".strip()
        linhas.append(f"🚚 Frete: R$ {_brl(frete_escolhido['valor'])} ({servico})")
    else:
        linhas.append("🚚 Frete: a confirmar")

    return "\n".join(linhas)


def avisar_pedido_novo(pedido_id, dados, resumo_carrinho, frete_escolhido=None):
    """Envia o aviso em segundo plano, sem atrasar nem quebrar o pedido."""
    try:
        texto = montar_mensagem(pedido_id, dados, resumo_carrinho, frete_escolhido)
    except Exception as erro:  # nunca derruba o checkout
        log.warning("Não foi possível montar o aviso do Telegram (%s).", type(erro).__name__)
        return
    threading.Thread(target=_enviar, args=(texto,), daemon=True).start()
