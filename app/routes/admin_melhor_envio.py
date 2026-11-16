import hmac
import re
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import melhor_envio
from app.auth import login_required

bp = Blueprint("admin_melhor_envio", __name__, url_prefix="/admin/melhor-envio")

# Embalagem usada no teste de cotacao: 300 g, 20 x 20 x 10 cm, valor de R$ 50
PACOTE_TESTE = [
    {
        "id": "teste",
        "width": 20,
        "height": 10,
        "length": 20,
        "weight": 0.3,
        "insurance_value": 50.0,
        "quantity": 1,
    }
]


def _painel(teste=None):
    return render_template("admin/melhor_envio.html", teste=teste, **melhor_envio.estado())


@bp.route("")
@login_required
def painel():
    return _painel()


@bp.route("/conectar", methods=["POST"])
@login_required
def conectar():
    if melhor_envio.faltando():
        flash("Preencha as configurações do Melhor Envio no arquivo .env antes de conectar.", "erro")
        return redirect(url_for("admin_melhor_envio.painel"))

    state = secrets.token_urlsafe(24)
    session["melhor_envio_state"] = state
    return redirect(melhor_envio.url_de_autorizacao(state))


def _concluir(codigo, state_recebido, erro_recebido):
    """Valida o retorno da autorizacao e troca o codigo pelo token."""
    state_esperado = session.pop("melhor_envio_state", None)

    if erro_recebido:
        flash("A autorização foi negada ou cancelada no Melhor Envio.", "erro")
    elif not state_esperado or not hmac.compare_digest(
        state_esperado.encode(), state_recebido.encode()
    ):
        flash(
            "Não consegui confirmar a origem da autorização. "
            "Clique em Conectar e autorize de novo.",
            "erro",
        )
    elif not codigo:
        flash("O endereço não tem o código de autorização.", "erro")
    else:
        try:
            melhor_envio.trocar_codigo(codigo)
        except melhor_envio.ErroMelhorEnvio as erro:
            flash(str(erro), "erro")
        else:
            flash("Loja conectada ao Melhor Envio.", "ok")
    return redirect(url_for("admin_melhor_envio.painel"))


@bp.route("/callback")
@login_required
def callback():
    """Retorno automatico, usado quando o aplicativo aponta para este site (endereco publico)."""
    return _concluir(
        request.args.get("code", ""),
        request.args.get("state", ""),
        request.args.get("error", ""),
    )


@bp.route("/colar", methods=["POST"])
@login_required
def colar():
    """Retorno manual: voce cola o endereco da pagina para onde o Melhor Envio levou o navegador."""
    endereco = request.form.get("endereco", "").strip()
    if not endereco.lower().startswith("http") or "code=" not in endereco and "error=" not in endereco:
        flash(
            "Cole o endereço completo da página (começa com https:// e tem ?code= no meio).",
            "erro",
        )
        return redirect(url_for("admin_melhor_envio.painel"))

    codigo, state, erro = melhor_envio.extrair_retorno(endereco)
    return _concluir(codigo, state, erro)


@bp.route("/desconectar", methods=["POST"])
@login_required
def desconectar():
    melhor_envio.desconectar()
    flash("Conexão com o Melhor Envio removida.", "ok")
    return redirect(url_for("admin_melhor_envio.painel"))


@bp.route("/testar", methods=["POST"])
@login_required
def testar():
    cep = re.sub(r"\D", "", request.form.get("cep", ""))
    if len(cep) != 8:
        flash("CEP inválido. Ele tem 8 números.", "erro")
        return redirect(url_for("admin_melhor_envio.painel"))

    try:
        opcoes = melhor_envio.cotar(cep, PACOTE_TESTE)
        teste = {"cep": cep, "opcoes": opcoes, "erro": None}
    except melhor_envio.ErroMelhorEnvio as erro:
        teste = {"cep": cep, "opcoes": [], "erro": str(erro)}
    return _painel(teste)
