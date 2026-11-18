from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import carrinho, limitador
from app.db import get_db
from app.util import ip_cliente, ler_inteiro

bp = Blueprint("loja", __name__)

MODALIDADES = ("pronta_entrega", "personalizavel")
MAX_PERSONALIZADO = 10

# Pecas por pagina no catalogo
POR_PAGINA = 24

# Carrinhos NOVOS (visitante ainda sem cookie) que um mesmo IP pode abrir por hora.
# Cada carrinho novo vira uma linha no banco; o limite barra robos que encheriam a tabela.
MAX_CARRINHOS_NOVOS_POR_IP = 30
JANELA_CARRINHOS_NOVOS = 3600


@bp.route("/privacidade")
def privacidade():
    return render_template("loja/privacidade.html")


# ---------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------
@bp.route("/")
@bp.route("/colecao/<slug>")
def catalogo(slug=None):
    modalidade = request.args.get("modalidade", "")
    if modalidade not in MODALIDADES:
        modalidade = ""
    pagina = ler_inteiro(request.args.get("pagina", "1"), 1, 1000) or 1

    db = get_db()
    with db.cursor() as cur:
        categoria = None
        if slug:
            cur.execute("SELECT id, nome, slug FROM categorias WHERE slug = %s", (slug,))
            categoria = cur.fetchone()
            if categoria is None:
                abort(404)

        cur.execute(
            f"""
            SELECT p.id, p.nome, p.slug, p.modalidade, p.preco, p.estoque,
                   {carrinho.FOTO_PRINCIPAL_SQL} AS foto
            FROM produtos p
            WHERE p.ativo
              AND (%(categoria)s IS NULL OR p.categoria_id = %(categoria)s)
              AND (%(modalidade)s = '' OR p.modalidade = %(modalidade)s)
            ORDER BY (p.modalidade = 'pronta_entrega' AND p.estoque = 0),
                     p.criado_em DESC, p.id DESC
            LIMIT %(limite)s OFFSET %(deslocamento)s
            """,
            {
                "categoria": categoria["id"] if categoria else None,
                "modalidade": modalidade,
                # Pede 1 a mais so para saber se existe uma proxima pagina
                "limite": POR_PAGINA + 1,
                "deslocamento": (pagina - 1) * POR_PAGINA,
            },
        )
        produtos = cur.fetchall()
        tem_proxima = len(produtos) > POR_PAGINA
        produtos = produtos[:POR_PAGINA]

        cur.execute(
            """
            SELECT c.nome, c.slug FROM categorias c
            WHERE EXISTS (SELECT 1 FROM produtos p
                          WHERE p.categoria_id = c.id AND p.ativo)
            ORDER BY c.nome
            """
        )
        categorias = cur.fetchall()

    return render_template(
        "loja/catalogo.html",
        produtos=produtos,
        categorias=categorias,
        categoria=categoria,
        modalidade=modalidade,
        pagina=pagina,
        tem_proxima=tem_proxima,
    )


# ---------------------------------------------------------------
# Pagina do produto
# ---------------------------------------------------------------
@bp.route("/produto/<slug>")
def produto(slug):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT p.*, c.nome AS categoria_nome, c.slug AS categoria_slug
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.slug = %s AND p.ativo
            """,
            (slug,),
        )
        item = cur.fetchone()
        if item is None:
            abort(404)

        cur.execute(
            "SELECT arquivo FROM produto_fotos WHERE produto_id = %s ORDER BY ordem, id",
            (item["id"],),
        )
        fotos = cur.fetchall()

    return render_template("loja/produto.html", produto=item, fotos=fotos)


# ---------------------------------------------------------------
# Carrinho
# ---------------------------------------------------------------
def buscar_produto(produto_id):
    with get_db().cursor() as cur:
        cur.execute(
            "SELECT id, slug, modalidade, estoque FROM produtos WHERE id = %s AND ativo",
            (produto_id,),
        )
        return cur.fetchone()


@bp.route("/carrinho")
def ver_carrinho():
    dados = carrinho.detalhar(carrinho.carregar())
    return render_template("loja/carrinho.html", **dados)


@bp.route("/carrinho/adicionar", methods=["POST"])
def carrinho_adicionar():
    produto_id = ler_inteiro(request.form.get("produto_id", ""), 1, 2**31 - 1)
    produto = buscar_produto(produto_id) if produto_id else None
    if produto is None:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("loja.catalogo"))

    voltar = redirect(url_for("loja.produto", slug=produto["slug"]))
    itens = list(carrinho.carregar())

    if produto["modalidade"] == "pronta_entrega":
        quantidade = ler_inteiro(request.form.get("quantidade", "1"), 1, 99)
        if quantidade is None:
            flash("Escolha uma quantidade válida.", "erro")
            return voltar

        existente = next(
            (
                i
                for i in itens
                if i["produto_id"] == produto["id"] and not i.get("descricao")
            ),
            None,
        )
        total = quantidade + (existente["quantidade"] if existente else 0)
        if total > produto["estoque"]:
            flash(f"Só há {produto['estoque']} unidade(s) disponível(is).", "erro")
            return voltar

        if existente:
            existente["quantidade"] = total
        else:
            itens.append(
                {
                    "id": carrinho.novo_id(),
                    "produto_id": produto["id"],
                    "quantidade": quantidade,
                    "descricao": None,
                }
            )
    else:
        descricao = request.form.get("descricao", "").strip()
        quantidade = ler_inteiro(request.form.get("quantidade", "1"), 1, MAX_PERSONALIZADO)
        if not descricao:
            flash("Descreva como você quer a sua peça.", "erro")
            return voltar
        if len(descricao) > 1000:
            flash("A descrição pode ter no máximo 1000 caracteres.", "erro")
            return voltar
        if quantidade is None:
            flash(f"Escolha de 1 a {MAX_PERSONALIZADO} peças.", "erro")
            return voltar

        itens.append(
            {
                "id": carrinho.novo_id(),
                "produto_id": produto["id"],
                "quantidade": quantidade,
                "descricao": descricao,
            }
        )

    if len(itens) > carrinho.MAX_LINHAS:
        flash(
            f"O carrinho aceita até {carrinho.MAX_LINHAS} itens. "
            "Finalize este pedido e faça outro depois.",
            "erro",
        )
        return voltar

    # Visitante sem carrinho ainda: este POST criaria uma linha nova no banco
    if carrinho.token_atual() is None and not limitador.permitir(
        f"carrinho-novo:{ip_cliente()}", MAX_CARRINHOS_NOVOS_POR_IP, JANELA_CARRINHOS_NOVOS
    ):
        flash("Muitas tentativas seguidas. Aguarde um pouco e tente de novo.", "erro")
        return voltar

    carrinho.salvar(itens)
    flash("Adicionado ao carrinho.", "ok")
    return redirect(url_for("loja.ver_carrinho"))


@bp.route("/carrinho/<item_id>/atualizar", methods=["POST"])
def carrinho_atualizar(item_id):
    itens = list(carrinho.carregar())
    item = next((i for i in itens if i["id"] == item_id), None)
    if item is None:
        return redirect(url_for("loja.ver_carrinho"))

    quantidade = ler_inteiro(request.form.get("quantidade", ""), 1, 99)
    produto = buscar_produto(item["produto_id"])

    if quantidade is None:
        flash("Quantidade inválida.", "erro")
    elif produto is None:
        flash("Este produto não está mais disponível.", "erro")
    elif produto["modalidade"] == "pronta_entrega" and quantidade > produto["estoque"]:
        flash(f"Só há {produto['estoque']} unidade(s) disponível(is).", "erro")
    elif produto["modalidade"] == "personalizavel" and quantidade > MAX_PERSONALIZADO:
        flash(f"Escolha de 1 a {MAX_PERSONALIZADO} peças.", "erro")
    else:
        item["quantidade"] = quantidade
        carrinho.salvar(itens)
        flash("Quantidade atualizada.", "ok")

    return redirect(url_for("loja.ver_carrinho"))


@bp.route("/carrinho/<item_id>/remover", methods=["POST"])
def carrinho_remover(item_id):
    itens = [i for i in carrinho.carregar() if i["id"] != item_id]
    carrinho.salvar(itens)
    flash("Item removido.", "ok")
    return redirect(url_for("loja.ver_carrinho"))
