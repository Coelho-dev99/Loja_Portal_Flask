"""Carrinho de compras sem login.

O visitante recebe um cookie com um codigo aleatorio e o conteudo do carrinho
fica guardado no banco (tabela carrinhos). Assim o carrinho nao estoura o
limite de tamanho do cookie e sobrevive se o navegador for fechado.
"""
import re
import secrets
from decimal import Decimal

from flask import g, request
from psycopg2.extras import Json

from app.db import get_db

COOKIE = "carrinho"
VALIDADE_SEGUNDOS = 30 * 24 * 3600
MAX_LINHAS = 15
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")

FOTO_PRINCIPAL_SQL = """(SELECT f.arquivo FROM produto_fotos f
                         WHERE f.produto_id = p.id
                         ORDER BY f.ordem, f.id LIMIT 1)"""


def _token():
    token = request.cookies.get(COOKIE, "")
    return token if _TOKEN.match(token) else None


def token_atual():
    """Codigo do carrinho do visitante (ou None)."""
    return _token()


def marcar_limpo():
    """Apos finalizar o pedido: o carrinho ja foi apagado do banco na mesma
    transacao; aqui so removemos o cookie do navegador."""
    g.carrinho_itens = []
    g.carrinho_limpar = True


def carregar():
    """Itens do carrinho do visitante (lista vazia se ele nao tiver carrinho)."""
    if "carrinho_itens" in g:
        return g.carrinho_itens

    itens = []
    token = _token()
    if token:
        with get_db().cursor() as cur:
            cur.execute("SELECT itens FROM carrinhos WHERE token = %s", (token,))
            linha = cur.fetchone()
            if linha:
                itens = linha["itens"]
    g.carrinho_itens = itens
    return itens


def salvar(itens):
    db = get_db()
    token = _token()
    with db.cursor() as cur:
        if token is None:
            token = secrets.token_urlsafe(32)
            # Aproveita para limpar carrinhos abandonados ha mais de 30 dias
            cur.execute(
                "DELETE FROM carrinhos WHERE atualizado_em < NOW() - INTERVAL '30 days'"
            )
        cur.execute(
            """
            INSERT INTO carrinhos (token, itens) VALUES (%s, %s)
            ON CONFLICT (token) DO UPDATE
            SET itens = EXCLUDED.itens, atualizado_em = NOW()
            """,
            (token, Json(itens)),
        )
    db.commit()
    g.carrinho_itens = itens
    g.carrinho_cookie = token


def limpar():
    """Esvazia o carrinho (usado depois que o pedido e finalizado)."""
    token = _token()
    if token:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("DELETE FROM carrinhos WHERE token = %s", (token,))
        db.commit()
    g.carrinho_itens = []
    g.carrinho_limpar = True


def novo_id():
    return secrets.token_hex(4)


def quantidade_total():
    return sum(item.get("quantidade", 0) for item in carregar())


def detalhar(itens):
    """Junta cada item do carrinho com os dados atuais do produto.

    Retorna as linhas, o subtotal das pecas com valor fechado e se o
    carrinho esta pronto para finalizar (sem produto indisponivel ou
    quantidade acima do estoque).
    """
    ids = sorted({item["produto_id"] for item in itens})
    produtos = {}
    if ids:
        with get_db().cursor() as cur:
            cur.execute(
                f"""
                SELECT p.id, p.nome, p.slug, p.modalidade, p.preco, p.estoque,
                       p.ativo, {FOTO_PRINCIPAL_SQL} AS foto
                FROM produtos p
                WHERE p.id = ANY(%s)
                """,
                (ids,),
            )
            produtos = {p["id"]: p for p in cur.fetchall()}

    linhas = []
    subtotal = Decimal("0")
    tem_personalizado = False
    pode_finalizar = bool(itens)

    for item in itens:
        produto = produtos.get(item["produto_id"])
        problema = None
        subtotal_linha = None

        if produto is None or not produto["ativo"]:
            problema = "Este produto não está mais disponível. Remova-o do carrinho."
        elif produto["modalidade"] == "pronta_entrega":
            subtotal_linha = produto["preco"] * item["quantidade"]
            if produto["estoque"] == 0:
                problema = "Esgotado. Remova-o do carrinho."
            elif produto["estoque"] < item["quantidade"]:
                problema = f"Só há {produto['estoque']} em estoque. Ajuste a quantidade."
        else:
            tem_personalizado = True

        if problema:
            pode_finalizar = False
        if subtotal_linha is not None:
            subtotal += subtotal_linha

        linhas.append(
            {
                "item": item,
                "produto": produto,
                "problema": problema,
                "subtotal": subtotal_linha,
            }
        )

    return {
        "linhas": linhas,
        "subtotal": subtotal,
        "tem_personalizado": tem_personalizado,
        "pode_finalizar": pode_finalizar,
    }
