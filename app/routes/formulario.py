import re

from flask import Blueprint, abort, redirect, render_template, request, url_for
from psycopg2 import errors

from app.db import get_db

bp = Blueprint("formulario", __name__)

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class ErroPedido(Exception):
    """Problema que o cliente precisa saber (estoque, link ja usado...)."""


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[n]) * (i + 1 - n) for n in range(i))
        if (soma * 10 % 11) % 10 != int(cpf[i]):
            return False
    return True


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

    nome = texto("nome", "Nome", 120)

    telefone = so_digitos(f.get("telefone", ""))
    if len(telefone) in (12, 13) and telefone.startswith("55"):
        telefone = telefone[2:]
    if len(telefone) not in (10, 11):
        erros.append("Informe o telefone com DDD. Exemplo: (61) 91234-5678")

    instagram = f.get("instagram", "").strip().lstrip("@")
    if instagram and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", instagram):
        erros.append("O @ do Instagram parece inválido.")

    cpf = so_digitos(f.get("cpf", "")) or None
    if cpf and not cpf_valido(cpf):
        erros.append("CPF inválido. Se preferir, deixe o campo em branco.")

    cep = so_digitos(f.get("cep", ""))
    if len(cep) != 8:
        erros.append("CEP inválido. Ele tem 8 números.")

    rua = texto("rua", "Rua", 150)
    numero = texto("numero", "Número", 10)
    complemento = texto("complemento", "Complemento", 80, obrigatorio=False)
    bairro = texto("bairro", "Bairro", 80)
    cidade = texto("cidade", "Cidade", 80)

    estado = f.get("estado", "").strip().upper()
    if estado not in UFS:
        erros.append('Informe a sigla do estado no campo "Estado". Exemplo: DF')

    if not f.get("consentimento"):
        erros.append("Para continuar, marque a autorização do uso dos seus dados.")

    dados = {
        "nome": nome,
        "telefone": telefone,
        "instagram": instagram or None,
        "cpf": cpf,
        "cep": cep,
        "rua": rua,
        "numero": numero,
        "complemento": complemento,
        "bairro": bairro,
        "cidade": cidade,
        "estado": estado,
    }
    return dados, erros


def finalizar(db, token, dados):
    """Grava cliente e endereco, reserva o estoque e confirma o pedido.

    Tudo acontece numa unica transacao: se algo falhar, nada e salvo.
    """
    with db.cursor() as cur:
        # Trava o pedido para evitar envio duplicado do mesmo link
        cur.execute(
            "SELECT id, status FROM pedidos WHERE token = %s FOR UPDATE", (token,)
        )
        pedido = cur.fetchone()
        if pedido is None or pedido["status"] != "aguardando_dados":
            raise ErroPedido("Este pedido já foi preenchido ou não está mais disponível.")

        # Reserva o estoque das pecas de pronta entrega
        cur.execute(
            """
            SELECT produto_id, SUM(quantidade) AS qtd
            FROM itens_pedido
            WHERE pedido_id = %s AND tipo = 'pronta_entrega'
            GROUP BY produto_id
            ORDER BY produto_id
            """,
            (pedido["id"],),
        )
        for linha in cur.fetchall():
            cur.execute(
                """
                UPDATE produtos
                SET estoque = estoque - %s
                WHERE id = %s AND estoque >= %s
                RETURNING id
                """,
                (linha["qtd"], linha["produto_id"], linha["qtd"]),
            )
            if cur.fetchone() is None:
                raise ErroPedido(
                    "Uma das peças acabou de esgotar. "
                    "Fale comigo pelo Instagram para combinarmos."
                )

        # Cliente: o telefone identifica quem ja comprou antes
        cur.execute(
            """
            INSERT INTO clientes (nome, instagram, telefone, cpf)
            VALUES (%(nome)s, %(instagram)s, %(telefone)s, %(cpf)s)
            ON CONFLICT (telefone) DO UPDATE
            SET instagram = COALESCE(clientes.instagram, EXCLUDED.instagram),
                cpf = COALESCE(clientes.cpf, EXCLUDED.cpf)
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
              AND numero = %(numero)s
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
                    (cliente_id, cep, rua, numero, complemento, bairro, cidade, estado)
                VALUES
                    (%(cliente_id)s, %(cep)s, %(rua)s, %(numero)s, %(complemento)s,
                     %(bairro)s, %(cidade)s, %(estado)s)
                RETURNING id
                """,
                params,
            )
            endereco_id = cur.fetchone()["id"]

        cur.execute(
            """
            UPDATE pedidos
            SET cliente_id = %s, endereco_id = %s,
                status = 'confirmado', dados_preenchidos_em = NOW()
            WHERE id = %s
            """,
            (cliente_id, endereco_id, pedido["id"]),
        )


@bp.route("/pedido/<token>", methods=["GET", "POST"])
def pedido(token):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, status FROM pedidos WHERE token = %s", (token,))
        registro = cur.fetchone()
        if registro is None:
            abort(404)

        if registro["status"] == "cancelado":
            return render_template("formulario/encerrado.html")
        if registro["status"] != "aguardando_dados":
            return render_template("formulario/recebido.html")

        cur.execute(
            """
            SELECT i.tipo, i.quantidade, i.valor_unitario, i.descricao,
                   p.nome AS produto_nome, t.nome AS tipo_nome
            FROM itens_pedido i
            LEFT JOIN produtos p ON p.id = i.produto_id
            LEFT JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
            WHERE i.pedido_id = %s
            ORDER BY i.id
            """,
            (registro["id"],),
        )
        itens = cur.fetchall()

    if not itens:
        abort(404)

    erros = []
    if request.method == "POST":
        dados, erros = ler_formulario()
        if not erros:
            try:
                finalizar(db, token, dados)
                db.commit()
            except ErroPedido as e:
                db.rollback()
                erros.append(str(e))
            except errors.UniqueViolation:
                db.rollback()
                erros.append(
                    "Este CPF já está cadastrado com outro telefone. "
                    "Fale comigo pelo Instagram."
                )
            else:
                return redirect(url_for("formulario.pedido", token=token))

    total = sum(i["quantidade"] * i["valor_unitario"] for i in itens)
    return render_template(
        "formulario/pedido.html",
        itens=itens,
        total=total,
        erros=erros,
        valores=request.form,
    )
