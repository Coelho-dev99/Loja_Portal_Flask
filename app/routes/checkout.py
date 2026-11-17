import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app import carrinho, frete, limitador
from app.db import get_db
from app.util import ip_cliente, ler_inteiro

bp = Blueprint("checkout", __name__)

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class ErroPedido(Exception):
    """Problema que o cliente precisa saber (estoque, item indisponivel...)."""


MENSAGEM_CONFIRMAR = (
    "O frete será calculado e confirmado na conversa do Instagram, antes do pagamento."
)
MENSAGEM_ESCOLHA = "Escolha como prefere receber:"
MENSAGEM_ESTIMADO = (
    "Estimativa: o valor final do frete é confirmado na conversa, quando a peça "
    "personalizada estiver definida. Escolha uma opção:"
)


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def brl(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cotacao_em_json(cotacao):
    """Dados da cotacao no formato usado pela tela (so o que o cliente pode ver)."""
    if cotacao["status"] == "ok":
        mensagem = MENSAGEM_ESTIMADO if cotacao["estimado"] else MENSAGEM_ESCOLHA
    else:
        mensagem = MENSAGEM_CONFIRMAR
    return {
        "status": cotacao["status"],
        "estimado": cotacao["estimado"],
        "mensagem": mensagem,
        "opcoes": [
            {
                "id": o["id"],
                "nome": o["nome"],
                "empresa": o["empresa"],
                "valor": str(o["valor"]),
                "valor_texto": f"R$ {brl(o['valor'])}",
                "prazo": o["prazo"],
            }
            for o in cotacao["opcoes"]
        ],
    }


# ---------------------------------------------------------------
# Validacao do formulario
# ---------------------------------------------------------------
def ler_formulario():
    """Le e valida os dados do cliente. Retorna (dados, erros)."""
    f = request.form
    erros = []

    def texto(chave, rotulo, maximo, obrigatorio=True):
        valor = f.get(chave, "").strip()
        if obrigatorio and not valor:
            erros.append(f'Preencha o campo "{rotulo}".')
        elif len(valor) > maximo:
            erros.append(f'O campo "{rotulo}" aceita no máximo {maximo} caracteres.')
        return valor or None

    nome = texto("nome", "Nome completo", 120)

    telefone = so_digitos(f.get("telefone", ""))
    if len(telefone) in (12, 13) and telefone.startswith("55"):
        telefone = telefone[2:]
    if len(telefone) not in (10, 11):
        erros.append("Informe o telefone com DDD. Exemplo: (61) 91234-5678")

    instagram = f.get("instagram", "").strip().lstrip("@")
    if instagram and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", instagram):
        erros.append("O @ do Instagram parece inválido.")

    cep = so_digitos(f.get("cep", ""))
    if len(cep) != 8:
        erros.append("CEP inválido. Ele tem 8 números.")

    rua = texto("rua", "Rua", 150)
    numero = texto("numero", "Número", 10)
    bairro = texto("bairro", "Bairro", 80)
    cidade = texto("cidade", "Cidade", 80)

    estado = f.get("estado", "").strip().upper()
    if estado not in UFS:
        erros.append('Informe a sigla do estado no campo "Estado". Exemplo: DF')

    tipo_moradia = f.get("tipo_moradia", "")
    if tipo_moradia not in ("casa", "apartamento"):
        erros.append("Informe se o endereço é casa ou apartamento.")

    complemento = f.get("complemento", "").strip() or None
    if complemento and len(complemento) > 80:
        erros.append('O campo "Complemento" aceita no máximo 80 caracteres.')
    if tipo_moradia == "apartamento" and not complemento:
        erros.append("Para apartamento, informe o complemento (bloco e número do apartamento).")

    if not f.get("consentimento"):
        erros.append("Para continuar, marque a autorização do uso dos seus dados.")

    dados = {
        "nome": nome,
        "telefone": telefone,
        "instagram": instagram or None,
        "cep": cep,
        "rua": rua,
        "numero": numero,
        "tipo_moradia": tipo_moradia,
        "complemento": complemento,
        "bairro": bairro,
        "cidade": cidade,
        "estado": estado,
    }
    return dados, erros


# ---------------------------------------------------------------
# Criacao do pedido (tudo numa unica transacao)
# ---------------------------------------------------------------
def criar_pedido(db, dados, frete_escolhido=None, assinatura_cotada=None):
    """Cria o pedido a partir do carrinho e reserva o estoque.

    Se qualquer coisa falhar, nada e salvo. O carrinho e travado e apagado
    na mesma transacao, entao um duplo clique no botao nao gera dois pedidos.
    """
    token = carrinho.token_atual()
    if token is None:
        raise ErroPedido("Seu carrinho está vazio.")

    with db.cursor() as cur:
        cur.execute("SELECT itens FROM carrinhos WHERE token = %s FOR UPDATE", (token,))
        linha = cur.fetchone()
        itens = linha["itens"] if linha else []
        if not itens:
            raise ErroPedido("Seu carrinho está vazio.")
        if frete_escolhido is not None and frete.assinatura(itens) != assinatura_cotada:
            raise ErroPedido("Seu carrinho mudou. Volte ao carrinho e confira o frete.")

        ids = sorted({i["produto_id"] for i in itens})
        cur.execute(
            """
            SELECT id, nome, modalidade, preco, ativo, tipo_personalizado_id
            FROM produtos WHERE id = ANY(%s)
            """,
            (ids,),
        )
        produtos = {p["id"]: p for p in cur.fetchall()}

        linhas = []
        reservas = {}
        for item in itens:
            p = produtos.get(item["produto_id"])
            if p is None or not p["ativo"]:
                raise ErroPedido(
                    "Um dos itens não está mais disponível. Volte ao carrinho e remova-o."
                )
            if p["modalidade"] == "pronta_entrega":
                reservas[p["id"]] = reservas.get(p["id"], 0) + item["quantidade"]
                linhas.append(
                    ("pronta_entrega", p["id"], None, None, item["quantidade"], p["preco"])
                )
            else:
                descricao = (item.get("descricao") or "").strip()
                if not descricao:
                    raise ErroPedido("Uma peça personalizada está sem descrição. Volte ao carrinho.")
                linhas.append(
                    (
                        "personalizado",
                        p["id"],
                        p["tipo_personalizado_id"],
                        descricao,
                        item["quantidade"],
                        None,  # valor a combinar no chat
                    )
                )

        # Reserva o estoque das pecas de pronta entrega
        for produto_id in sorted(reservas):
            cur.execute(
                """
                UPDATE produtos SET estoque = estoque - %s
                WHERE id = %s AND ativo AND estoque >= %s
                RETURNING id
                """,
                (reservas[produto_id], produto_id, reservas[produto_id]),
            )
            if cur.fetchone() is None:
                raise ErroPedido(
                    f'Não há mais estoque suficiente de "{produtos[produto_id]["nome"]}". '
                    "Volte ao carrinho para ajustar a quantidade."
                )

        # Cliente: o telefone identifica quem ja comprou antes.
        # Em cliente existente, mantem o nome e completa o que estava vazio.
        cur.execute(
            """
            INSERT INTO clientes (nome, instagram, telefone)
            VALUES (%(nome)s, %(instagram)s, %(telefone)s)
            ON CONFLICT (telefone) DO UPDATE
            SET instagram = COALESCE(clientes.instagram, EXCLUDED.instagram)
            RETURNING id
            """,
            dados,
        )
        cliente_id = cur.fetchone()["id"]

        # Endereco: reaproveita se o cliente ja tem o mesmo cadastrado
        params = {**dados, "cliente_id": cliente_id}
        cur.execute(
            """
            SELECT id FROM enderecos
            WHERE cliente_id = %(cliente_id)s AND cep = %(cep)s AND rua = %(rua)s
              AND numero = %(numero)s AND tipo_moradia = %(tipo_moradia)s
              AND complemento IS NOT DISTINCT FROM %(complemento)s
              AND bairro = %(bairro)s AND cidade = %(cidade)s AND estado = %(estado)s
            """,
            params,
        )
        existente = cur.fetchone()
        if existente:
            endereco_id = existente["id"]
        else:
            cur.execute(
                """
                INSERT INTO enderecos
                    (cliente_id, cep, rua, numero, tipo_moradia, complemento,
                     bairro, cidade, estado)
                VALUES
                    (%(cliente_id)s, %(cep)s, %(rua)s, %(numero)s, %(tipo_moradia)s,
                     %(complemento)s, %(bairro)s, %(cidade)s, %(estado)s)
                RETURNING id
                """,
                params,
            )
            endereco_id = cur.fetchone()["id"]

        if frete_escolhido is not None:
            servico = f"{frete_escolhido['empresa']} {frete_escolhido['nome']}".strip()[:60] or None
            valor_frete, prazo_frete = frete_escolhido["valor"], frete_escolhido["prazo"]
        else:
            servico = valor_frete = prazo_frete = None
        cur.execute(
            """
            INSERT INTO pedidos
                (cliente_id, endereco_id, frete_valor, frete_servico, frete_prazo_dias)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (cliente_id, endereco_id, valor_frete, servico, prazo_frete),
        )
        pedido_id = cur.fetchone()["id"]

        for tipo, produto_id, tipo_id, descricao, quantidade, valor in linhas:
            cur.execute(
                """
                INSERT INTO itens_pedido
                    (pedido_id, tipo, produto_id, tipo_personalizado_id, descricao,
                     quantidade, valor_unitario)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (pedido_id, tipo, produto_id, tipo_id, descricao, quantidade, valor),
            )

        cur.execute(
            "INSERT INTO pedido_status_historico (pedido_id, status) VALUES (%s, 'aguardando_pagamento')",
            (pedido_id,),
        )
        cur.execute("DELETE FROM carrinhos WHERE token = %s", (token,))

    return pedido_id


# ---------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------
@bp.route("/finalizar", methods=["GET", "POST"])
def finalizar():
    itens = carrinho.carregar()
    dados_carrinho = carrinho.detalhar(itens)
    if not dados_carrinho["linhas"]:
        return redirect(url_for("loja.ver_carrinho"))
    if not dados_carrinho["pode_finalizar"]:
        flash("Ajuste os itens com aviso antes de finalizar.", "erro")
        return redirect(url_for("loja.ver_carrinho"))

    erros = []
    frete_inicial = None
    if request.method == "POST":
        dados, erros = ler_formulario()

        # O frete e cotado de novo no servidor: o preco nunca vem do navegador
        frete_escolhido = None
        if not erros:
            cotacao = frete.cotar_carrinho(itens, dados["cep"])
            if cotacao["status"] == "ok":
                escolha = ler_inteiro(request.form.get("frete_opcao", ""), 1, 2**31 - 1)
                frete_escolhido = next(
                    (o for o in cotacao["opcoes"] if o["id"] == escolha), None
                )
                if frete_escolhido is None:
                    frete_inicial = cotacao_em_json(cotacao)
                    erros.append(
                        "Escolha uma das opções de frete."
                        if escolha is None
                        else "A opção de frete escolhida não está mais disponível. Escolha novamente."
                    )

        if not erros:
            db = get_db()
            try:
                pedido_id = criar_pedido(db, dados, frete_escolhido, frete.assinatura(itens))
                db.commit()
            except ErroPedido as e:
                db.rollback()
                if "carrinho está vazio" in str(e):
                    return redirect(url_for("loja.ver_carrinho"))
                erros.append(str(e))
            else:
                carrinho.marcar_limpo()
                session["pedido_enviado"] = pedido_id
                return redirect(url_for("checkout.enviado"))

    return render_template(
        "loja/finalizar.html",
        **dados_carrinho,
        erros=erros,
        valores=request.form,
        frete_inicial=frete_inicial,
    )


@bp.route("/frete/cotar")
def cotar_frete():
    """Opcoes de frete do carrinho do visitante para um CEP (usada pela tela de finalizar)."""
    cep = so_digitos(request.args.get("cep", ""))
    if len(cep) != 8:
        return jsonify(status="erro", mensagem="CEP inválido."), 400
    if not limitador.permitir(f"frete:{ip_cliente()}", 30, 600):
        return (
            jsonify(status="erro", mensagem="Muitas consultas seguidas. Tente de novo em alguns minutos."),
            429,
        )
    itens = carrinho.carregar()
    if not itens:
        return jsonify(status="erro", mensagem="Seu carrinho está vazio."), 400
    return jsonify(cotacao_em_json(frete.cotar_carrinho(itens, cep)))


def montar_resumo(pedido, itens, subtotal, tem_a_combinar):
    linhas = [f"Olá! Fiz o pedido nº {pedido['id']} no site Portal Lãb.", "", "Itens:"]
    for i in itens:
        if i["tipo"] == "pronta_entrega":
            linhas.append(f"- {i['quantidade']}x {i['produto_nome']}")
        else:
            linhas.append(
                f"- {i['quantidade']}x {i['tipo_nome']} personalizado: {i['descricao']}"
            )
    texto_subtotal = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if subtotal > 0:
        valor = f"Peças com valor fechado: {texto_subtotal}" + (
            " (mais peças personalizadas a combinar)" if tem_a_combinar else ""
        )
    else:
        valor = "Valor: a combinar no chat"

    if pedido["frete_valor"] is not None:
        detalhe = ", ".join(
            parte
            for parte in (
                pedido["frete_servico"],
                f"{pedido['frete_prazo_dias']} dias úteis"
                if pedido["frete_prazo_dias"] is not None
                else None,
            )
            if parte
        )
        linha_frete = f"Frete: R$ {brl(pedido['frete_valor'])}" + (f" ({detalhe})" if detalhe else "")
        if tem_a_combinar:
            linha_frete += " - estimativa"
    else:
        linha_frete = "Frete: a confirmar"

    linhas += [
        "",
        valor,
        linha_frete,
        *(
            [f"Total com frete: R$ {brl(subtotal + pedido['frete_valor'])}"]
            if pedido["frete_valor"] is not None and not tem_a_combinar and subtotal > 0
            else []
        ),
        f"Nome: {pedido['cliente_nome']}",
        f"Telefone: {pedido['telefone']}",
    ]
    return "\n".join(linhas)


@bp.route("/pedido-enviado")
def enviado():
    pedido_id = session.get("pedido_enviado")
    if not pedido_id:
        return redirect(url_for("loja.catalogo"))

    with get_db().cursor() as cur:
        cur.execute(
            """
            SELECT pe.id, pe.frete_valor, pe.frete_servico, pe.frete_prazo_dias,
                   c.nome AS cliente_nome, c.telefone
            FROM pedidos pe JOIN clientes c ON c.id = pe.cliente_id
            WHERE pe.id = %s
            """,
            (pedido_id,),
        )
        pedido = cur.fetchone()
        if pedido is None:
            session.pop("pedido_enviado", None)
            return redirect(url_for("loja.catalogo"))

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

    subtotal = sum(
        (i["quantidade"] * i["valor_unitario"] for i in itens if i["valor_unitario"] is not None),
        0,
    )
    tem_a_combinar = any(i["valor_unitario"] is None for i in itens)
    texto = montar_resumo(pedido, itens, subtotal, tem_a_combinar)

    return render_template(
        "loja/enviado.html",
        pedido=pedido,
        itens=itens,
        subtotal=subtotal,
        tem_a_combinar=tem_a_combinar,
        texto=texto,
    )
