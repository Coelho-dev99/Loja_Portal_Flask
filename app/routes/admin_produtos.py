from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth import login_required
from app.db import get_db
from app.imagens import ErroImagem, apagar_fotos, salvar_foto
from app.util import ler_decimal, ler_inteiro, slugify

bp = Blueprint("admin_produtos", __name__, url_prefix="/admin/produtos")

MAX_FOTOS = 8
MODALIDADES = {"pronta_entrega", "personalizavel"}
MEDIDAS = (
    ("altura_cm", "altura"),
    ("largura_cm", "largura"),
    ("comprimento_cm", "comprimento"),
)


# ---------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------
def listas_do_formulario(cur):
    cur.execute("SELECT id, nome FROM categorias ORDER BY nome")
    categorias = cur.fetchall()
    cur.execute("SELECT id, nome FROM tipos_personalizado ORDER BY nome")
    tipos = cur.fetchall()
    return categorias, tipos


def gerar_slug(cur, nome):
    """Cria o endereco do produto no site, sem repetir um que ja exista."""
    base = (slugify(nome) or "produto")[:120]
    slug, numero = base, 2
    while True:
        cur.execute("SELECT 1 FROM produtos WHERE slug = %s", (slug,))
        if cur.fetchone() is None:
            return slug
        slug = f"{base}-{numero}"
        numero += 1


def ler_formulario(cur):
    """Le e valida os campos do produto. Retorna (dados, erros)."""
    f = request.form
    erros = []

    nome = f.get("nome", "").strip()
    if not nome:
        erros.append("Informe o nome do produto.")
    elif len(nome) > 120:
        erros.append("O nome pode ter no máximo 120 caracteres.")

    descricao = f.get("descricao", "").strip() or None
    if descricao and len(descricao) > 3000:
        erros.append("A descrição pode ter no máximo 3000 caracteres.")

    modalidade = f.get("modalidade", "")
    if modalidade not in MODALIDADES:
        erros.append("Escolha se o produto é de pronta entrega ou personalizável.")

    categoria_id = None
    texto_categoria = f.get("categoria_id", "").strip()
    if texto_categoria:
        categoria_id = ler_inteiro(texto_categoria, 1, 2**31 - 1)
        cur.execute("SELECT 1 FROM categorias WHERE id = %s", (categoria_id,))
        if categoria_id is None or cur.fetchone() is None:
            categoria_id = None
            erros.append("Categoria não encontrada.")

    tipo_personalizado_id = None
    if modalidade == "personalizavel":
        tipo_personalizado_id = ler_inteiro(
            f.get("tipo_personalizado_id", ""), 1, 2**31 - 1
        )
        cur.execute(
            "SELECT 1 FROM tipos_personalizado WHERE id = %s", (tipo_personalizado_id,)
        )
        if tipo_personalizado_id is None or cur.fetchone() is None:
            tipo_personalizado_id = None
            erros.append("Escolha o tipo da peça personalizável.")

    preco = ler_decimal(f.get("preco", ""), 0, 99999999.99)
    if preco is None:
        erros.append("Preço inválido. Exemplo: 12,50")

    estoque = 0
    if modalidade == "pronta_entrega":
        texto_estoque = f.get("estoque", "").strip() or "0"
        estoque = ler_inteiro(texto_estoque, 0, 1_000_000)
        if estoque is None:
            erros.append("Estoque inválido. Use um número inteiro, 0 ou maior.")

    # Peso e medidas da embalagem (usados no calculo do frete)
    peso_g = None
    texto_peso = f.get("peso_g", "").strip()
    if texto_peso:
        peso_g = ler_inteiro(texto_peso, 1, 30000)
        if peso_g is None:
            erros.append("Peso inválido. Informe em gramas, de 1 a 30000.")

    medidas = {}
    for campo, _ in MEDIDAS:
        texto = f.get(campo, "").strip()
        medidas[campo] = None
        if texto:
            medidas[campo] = ler_decimal(texto, 0.1, 200, 1)
            if medidas[campo] is None:
                erros.append("Medida inválida. Informe em centímetros, de 0,1 a 200.")
                break

    if modalidade == "pronta_entrega" and (
        peso_g is None or any(v is None for v in medidas.values())
    ):
        if not texto_peso or not all(f.get(c, "").strip() for c, _ in MEDIDAS):
            erros.append(
                "Informe o peso e as medidas da embalagem. "
                "Eles são usados para calcular o frete."
            )

    dados = {
        "nome": nome,
        "descricao": descricao,
        "categoria_id": categoria_id,
        "modalidade": modalidade,
        "tipo_personalizado_id": tipo_personalizado_id,
        "preco": preco,
        "estoque": estoque,
        "peso_g": peso_g,
        **medidas,
    }
    return dados, erros


def ler_arquivos_de_fotos():
    return [a for a in request.files.getlist("fotos") if a and a.filename]


def processar_fotos(arquivos, erros):
    """Salva as fotos enviadas. Retorna a lista de nomes (vazia se houver erro)."""
    novas = []
    try:
        for arquivo in arquivos:
            novas.append(salvar_foto(arquivo))
    except ErroImagem as e:
        apagar_fotos(novas)
        erros.append(str(e))
        return []
    return novas


# ---------------------------------------------------------------
# Lista
# ---------------------------------------------------------------
@bp.route("")
@login_required
def produtos():
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.nome, p.modalidade, p.preco, p.estoque, p.ativo,
                   c.nome AS categoria,
                   (SELECT f.arquivo FROM produto_fotos f
                    WHERE f.produto_id = p.id
                    ORDER BY f.ordem, f.id LIMIT 1) AS foto
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            ORDER BY p.ativo DESC, p.nome
            """
        )
        lista = cur.fetchall()
    return render_template("admin/produtos.html", produtos=lista)


# ---------------------------------------------------------------
# Novo produto
# ---------------------------------------------------------------
@bp.route("/novo", methods=["GET", "POST"])
@login_required
def produto_novo():
    db = get_db()
    produto = {}

    with db.cursor() as cur:
        categorias, tipos = listas_do_formulario(cur)

        if request.method == "POST":
            dados, erros = ler_formulario(cur)
            arquivos = ler_arquivos_de_fotos()
            if len(arquivos) > MAX_FOTOS:
                erros.append(f"Envie no máximo {MAX_FOTOS} fotos por produto.")

            novas = processar_fotos(arquivos, erros) if not erros else []

            if not erros:
                try:
                    dados["slug"] = gerar_slug(cur, dados["nome"])
                    cur.execute(
                        """
                        INSERT INTO produtos
                            (nome, slug, descricao, categoria_id, modalidade,
                             tipo_personalizado_id, preco, estoque, peso_g,
                             altura_cm, largura_cm, comprimento_cm)
                        VALUES
                            (%(nome)s, %(slug)s, %(descricao)s, %(categoria_id)s,
                             %(modalidade)s, %(tipo_personalizado_id)s, %(preco)s,
                             %(estoque)s, %(peso_g)s, %(altura_cm)s, %(largura_cm)s,
                             %(comprimento_cm)s)
                        RETURNING id
                        """,
                        dados,
                    )
                    produto_id = cur.fetchone()["id"]
                    for ordem, arquivo in enumerate(novas):
                        cur.execute(
                            """
                            INSERT INTO produto_fotos (produto_id, arquivo, ordem)
                            VALUES (%s, %s, %s)
                            """,
                            (produto_id, arquivo, ordem),
                        )
                    db.commit()
                except Exception:
                    db.rollback()
                    apagar_fotos(novas)
                    raise
                flash("Produto cadastrado.", "ok")
                return redirect(url_for("admin_produtos.produtos"))

            for erro in erros:
                flash(erro, "erro")
            produto = dados

    return render_template(
        "admin/produto_form.html",
        produto=produto,
        fotos=[],
        categorias=categorias,
        tipos=tipos,
        titulo="Novo produto",
        max_fotos=MAX_FOTOS,
    )


# ---------------------------------------------------------------
# Editar produto
# ---------------------------------------------------------------
@bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
def produto_editar(produto_id):
    db = get_db()

    with db.cursor() as cur:
        cur.execute("SELECT * FROM produtos WHERE id = %s", (produto_id,))
        produto = cur.fetchone()
        if produto is None:
            abort(404)

        cur.execute(
            "SELECT id, arquivo FROM produto_fotos WHERE produto_id = %s ORDER BY ordem, id",
            (produto_id,),
        )
        fotos = cur.fetchall()
        categorias, tipos = listas_do_formulario(cur)

        if request.method == "POST":
            dados, erros = ler_formulario(cur)

            # Fotos que ficam, na ordem escolhida (a principal vai para o inicio)
            ids_remover = {
                int(x) for x in request.form.getlist("remover_foto") if x.isdigit()
            }
            mantidas = [f for f in fotos if f["id"] not in ids_remover]
            texto_principal = request.form.get("principal", "")
            if texto_principal.isdigit():
                principal = [f for f in mantidas if f["id"] == int(texto_principal)]
                if principal:
                    mantidas = principal + [f for f in mantidas if f not in principal]

            arquivos = ler_arquivos_de_fotos()
            if len(mantidas) + len(arquivos) > MAX_FOTOS:
                erros.append(f"Cada produto aceita no máximo {MAX_FOTOS} fotos.")

            novas = processar_fotos(arquivos, erros) if not erros else []

            if not erros:
                dados["id"] = produto_id
                removidas = [f["arquivo"] for f in fotos if f["id"] in ids_remover]
                try:
                    cur.execute(
                        """
                        UPDATE produtos
                        SET nome = %(nome)s, descricao = %(descricao)s,
                            categoria_id = %(categoria_id)s,
                            modalidade = %(modalidade)s,
                            tipo_personalizado_id = %(tipo_personalizado_id)s,
                            preco = %(preco)s, estoque = %(estoque)s,
                            peso_g = %(peso_g)s, altura_cm = %(altura_cm)s,
                            largura_cm = %(largura_cm)s,
                            comprimento_cm = %(comprimento_cm)s
                        WHERE id = %(id)s
                        """,
                        dados,
                    )
                    if ids_remover:
                        cur.execute(
                            "DELETE FROM produto_fotos WHERE produto_id = %s AND id = ANY(%s)",
                            (produto_id, list(ids_remover)),
                        )
                    for ordem, foto in enumerate(mantidas):
                        cur.execute(
                            "UPDATE produto_fotos SET ordem = %s WHERE id = %s",
                            (ordem, foto["id"]),
                        )
                    for deslocamento, arquivo in enumerate(novas):
                        cur.execute(
                            """
                            INSERT INTO produto_fotos (produto_id, arquivo, ordem)
                            VALUES (%s, %s, %s)
                            """,
                            (produto_id, arquivo, len(mantidas) + deslocamento),
                        )
                    db.commit()
                except Exception:
                    db.rollback()
                    apagar_fotos(novas)
                    raise
                apagar_fotos(removidas)
                flash("Produto atualizado.", "ok")
                return redirect(url_for("admin_produtos.produtos"))

            for erro in erros:
                flash(erro, "erro")
            produto = {**dados, "id": produto_id}

    return render_template(
        "admin/produto_form.html",
        produto=produto,
        fotos=fotos,
        categorias=categorias,
        tipos=tipos,
        titulo="Editar produto",
        max_fotos=MAX_FOTOS,
    )


@bp.route("/<int:produto_id>/alternar", methods=["POST"])
@login_required
def produto_alternar(produto_id):
    """Oculta ou mostra o produto no catalogo (nao apaga, para manter o historico)."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE produtos SET ativo = NOT ativo WHERE id = %s", (produto_id,)
        )
    db.commit()
    return redirect(url_for("admin_produtos.produtos"))
