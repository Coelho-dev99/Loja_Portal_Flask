"""Acompanhamento do pedido pelo cliente (sem login).

O cliente informa o numero do pedido e o telefone usado na compra. Os dois
precisam bater. A tela mostra so o andamento e os itens: nunca nome,
endereco ou outros dados pessoais.
"""
import re

from flask import Blueprint, redirect, render_template, request, session, url_for

from app import limitador
from app.db import get_db
from app.status import ROTULOS
from app.util import ler_inteiro, normalizar_telefone

bp = Blueprint("acompanhar", __name__)

ETAPAS = ["aguardando_pagamento", "pago", "processando", "enviado", "concluido"]

MENSAGENS = {
    "aguardando_pagamento": "Recebemos o seu pedido. Estamos aguardando o pagamento, que combinamos pelo Instagram.",
    "pago": "Pagamento confirmado. Em breve começamos a preparar o seu pedido.",
    "processando": "Estamos preparando o seu pedido. Peças feitas à mão levam um tempinho.",
    "enviado": "Seu pedido foi enviado!",
    "concluido": "Pedido concluído. Obrigado por comprar com a gente!",
    "cancelado": "Este pedido foi cancelado. Se tiver dúvidas, fale com a gente pelo Instagram.",
}

NAO_ENCONTRADO = (
    "Não encontramos um pedido com esses dados. "
    "Confira o número do pedido e o telefone usados na compra."
)
MUITAS_TENTATIVAS = "Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo."
MAX_PEDIDOS_NA_SESSAO = 10


def _autorizar(pedido_id):
    """Guarda na sessao os pedidos que este visitante comprovou ser dele."""
    lista = [p for p in session.get("acompanhar", []) if p != pedido_id]
    lista.append(pedido_id)
    session["acompanhar"] = lista[-MAX_PEDIDOS_NA_SESSAO:]


@bp.route("/acompanhar", methods=["GET", "POST"])
def formulario():
    erro = None
    numero_digitado = ""
    telefone_digitado = ""
    status_http = 200

    if request.method == "GET":
        numero_digitado = re.sub(r"\D", "", request.args.get("pedido", ""))[:9]
    else:
        numero_digitado = request.form.get("pedido", "").strip()[:20]
        telefone_digitado = request.form.get("telefone", "").strip()[:30]
        numero = ler_inteiro(re.sub(r"\D", "", numero_digitado), 1, 2**31 - 1)
        telefone = normalizar_telefone(telefone_digitado)

        if numero is None or len(telefone) not in (10, 11):
            erro = "Informe o número do pedido e o telefone com DDD."
            status_http = 400
        elif not limitador.permitir(
            f"acompanhar-ip:{request.remote_addr}", 10, 600
        ) or not limitador.permitir(f"acompanhar-tel:{telefone}", 10, 1800):
            erro = MUITAS_TENTATIVAS
            status_http = 429
        else:
            with get_db().cursor() as cur:
                cur.execute(
                    """
                    SELECT pe.id
                    FROM pedidos pe JOIN clientes c ON c.id = pe.cliente_id
                    WHERE pe.id = %s AND c.telefone = %s
                    """,
                    (numero, telefone),
                )
                encontrado = cur.fetchone()
            if encontrado:
                _autorizar(encontrado["id"])
                return redirect(url_for("acompanhar.pedido", pedido_id=encontrado["id"]))
            erro = NAO_ENCONTRADO  # mesma mensagem para numero ou telefone errado
            status_http = 404

    return (
        render_template(
            "loja/acompanhar.html",
            erro=erro,
            numero=numero_digitado,
            telefone=telefone_digitado,
        ),
        status_http,
    )


@bp.route("/acompanhar/<int:pedido_id>")
def pedido(pedido_id):
    if pedido_id not in session.get("acompanhar", []):
        return redirect(url_for("acompanhar.formulario"))

    with get_db().cursor() as cur:
        cur.execute(
            """
            SELECT id, status, criado_em, frete_valor, frete_servico,
                   frete_prazo_dias, codigo_rastreio
            FROM pedidos WHERE id = %s
            """,
            (pedido_id,),
        )
        dados = cur.fetchone()
        if dados is None:
            return redirect(url_for("acompanhar.formulario"))

        cur.execute(
            """
            SELECT i.tipo, i.quantidade, i.valor_unitario, i.descricao,
                   p.nome AS produto_nome, t.nome AS tipo_nome
            FROM itens_pedido i
            LEFT JOIN produtos p ON p.id = i.produto_id
            LEFT JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
            WHERE i.pedido_id = %s ORDER BY i.id
            """,
            (pedido_id,),
        )
        itens = cur.fetchall()

        cur.execute(
            """
            SELECT status, criado_em FROM pedido_status_historico
            WHERE pedido_id = %s ORDER BY criado_em, id
            """,
            (pedido_id,),
        )
        historico = cur.fetchall()

    status = dados["status"]
    datas = {}
    for h in historico:
        datas.setdefault(h["status"], h["criado_em"])

    etapas = []
    if status != "cancelado":
        posicao = ETAPAS.index(status)
        for i, chave in enumerate(ETAPAS):
            estado = "atual" if i == posicao else "feito" if i < posicao else "pendente"
            etapas.append(
                {"chave": chave, "rotulo": ROTULOS[chave], "data": datas.get(chave), "estado": estado}
            )

    subtotal = sum(
        (i["quantidade"] * i["valor_unitario"] for i in itens if i["valor_unitario"] is not None),
        0,
    )
    tem_a_combinar = any(i["valor_unitario"] is None for i in itens)
    total = None
    if not tem_a_combinar and dados["frete_valor"] is not None:
        total = subtotal + dados["frete_valor"]

    mostrar_rastreio = bool(dados["codigo_rastreio"]) and status in ("enviado", "concluido")
    correios = bool(dados["frete_servico"]) and dados["frete_servico"].lower().startswith("correios")

    return render_template(
        "loja/acompanhar_pedido.html",
        pedido=dados,
        mensagem=MENSAGENS[status],
        rotulo=ROTULOS[status],
        etapas=etapas,
        historico=historico,
        itens=itens,
        subtotal=subtotal,
        tem_a_combinar=tem_a_combinar,
        total=total,
        mostrar_rastreio=mostrar_rastreio,
        correios=correios,
    )
