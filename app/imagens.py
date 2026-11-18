import io
import os
import re
import uuid

import requests
from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP"}
LADO_MAXIMO = 1600
NOME_VALIDO = re.compile(r"^[0-9a-f]{32}\.jpg$")

# Limite de megapixels por foto (largura x altura). Uma foto enorme ocupa muita
# memoria ao ser aberta e pode derrubar o servidor. JPEG aguenta mais porque e
# aberto ja em tamanho reduzido (veja salvar_foto); PNG e WebP, nao.
MAX_PIXELS_JPEG = 100_000_000
MAX_PIXELS_OUTROS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS_JPEG


TIMEOUT_STORAGE = 20  # segundos


class ErroImagem(Exception):
    """Foto invalida (formato, arquivo corrompido...)."""


def usa_supabase():
    """True quando as fotos vao para o Supabase Storage (URL e chave definidas)."""
    cfg = current_app.config
    return bool(cfg["SUPABASE_URL"] and cfg["SUPABASE_SECRET_KEY"])


def _cabecalhos_supabase(extra=None):
    chave = current_app.config["SUPABASE_SECRET_KEY"]
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}"}
    cabecalhos.update(extra or {})
    return cabecalhos


def _url_objeto(nome=""):
    cfg = current_app.config
    base = f"{cfg['SUPABASE_URL']}/storage/v1/object/{cfg['SUPABASE_BUCKET']}"
    return f"{base}/{nome}" if nome else base


def url_foto(nome):
    """Endereco publico da foto (para usar nos templates)."""
    if usa_supabase():
        cfg = current_app.config
        return (
            f"{cfg['SUPABASE_URL']}/storage/v1/object/public/"
            f"{cfg['SUPABASE_BUCKET']}/{nome}"
        )
    return url_for("static", filename=f"uploads/produtos/{nome}")


def _guardar(nome, dados):
    """Grava os bytes do JPEG no Supabase ou no disco local."""
    if not usa_supabase():
        with open(os.path.join(pasta_fotos(), nome), "wb") as f:
            f.write(dados)
        return
    try:
        resposta = requests.post(
            _url_objeto(nome),
            data=dados,
            headers=_cabecalhos_supabase(
                {
                    "Content-Type": "image/jpeg",
                    # O nome e um UUID novo a cada foto: pode ficar 1 ano em cache.
                    "Cache-Control": "max-age=31536000",
                }
            ),
            timeout=TIMEOUT_STORAGE,
        )
        resposta.raise_for_status()
    except requests.RequestException:
        current_app.logger.exception("Falha ao enviar foto ao Supabase Storage")
        raise ErroImagem("Não consegui enviar a foto ao armazenamento. Tente de novo.")


def pasta_fotos():
    pasta = os.path.join(current_app.static_folder, "uploads", "produtos")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_foto(arquivo):
    """Valida, reduz e salva a foto como JPEG. Retorna o nome do arquivo.

    Ao regravar a imagem, os dados EXIF (como a localizacao do celular)
    ficam de fora. Com SUPABASE_URL e SUPABASE_SECRET_KEY no .env, a foto vai
    para o Supabase Storage; sem elas, fica em app/static/uploads.
    """
    try:
        imagem = Image.open(arquivo.stream)
        if imagem.format not in FORMATOS_ACEITOS:
            raise ErroImagem("Use fotos nos formatos JPG, PNG ou WebP.")

        limite = MAX_PIXELS_JPEG if imagem.format == "JPEG" else MAX_PIXELS_OUTROS
        if imagem.width * imagem.height > limite:
            raise ErroImagem(
                "Uma das fotos é grande demais. Reduza o tamanho da imagem e tente de novo."
            )
        if imagem.format == "JPEG":
            # Abre o JPEG ja em tamanho menor (so o necessario), poupando memoria
            imagem.draft("RGB", (LADO_MAXIMO, LADO_MAXIMO))
        imagem = ImageOps.exif_transpose(imagem)

        tem_transparencia = imagem.mode in ("RGBA", "LA") or (
            imagem.mode == "P" and "transparency" in imagem.info
        )
        if tem_transparencia:
            imagem = imagem.convert("RGBA")
            fundo = Image.new("RGB", imagem.size, (255, 255, 255))
            fundo.paste(imagem, mask=imagem.split()[-1])
            imagem = fundo
        else:
            imagem = imagem.convert("RGB")

        imagem.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
        nome = f"{uuid.uuid4().hex}.jpg"
        buffer = io.BytesIO()
        imagem.save(buffer, "JPEG", quality=85, optimize=True)
        _guardar(nome, buffer.getvalue())
        return nome
    except ErroImagem:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ErroImagem("Não consegui ler uma das fotos. Tente outro arquivo JPG, PNG ou WebP.")


def apagar_fotos(nomes):
    """Apaga fotos do Supabase ou do disco (ignora nomes fora do padrao)."""
    validos = [n for n in nomes if NOME_VALIDO.match(n or "")]
    if not validos:
        return
    if usa_supabase():
        try:
            requests.delete(
                _url_objeto(),
                json={"prefixes": validos},
                headers=_cabecalhos_supabase(),
                timeout=TIMEOUT_STORAGE,
            ).raise_for_status()
        except requests.RequestException:
            # Sobrar uma foto no bucket nao deve quebrar o painel.
            current_app.logger.exception("Falha ao apagar fotos no Supabase Storage")
        return
    for nome in validos:
        try:
            os.remove(os.path.join(pasta_fotos(), nome))
        except FileNotFoundError:
            pass
