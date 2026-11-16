import os
import re
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP"}
LADO_MAXIMO = 1600
NOME_VALIDO = re.compile(r"^[0-9a-f]{32}\.jpg$")


class ErroImagem(Exception):
    """Foto invalida (formato, arquivo corrompido...)."""


def pasta_fotos():
    pasta = os.path.join(current_app.static_folder, "uploads", "produtos")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_foto(arquivo):
    """Valida, reduz e salva a foto como JPEG. Retorna o nome do arquivo.

    Ao regravar a imagem, os dados EXIF (como a localizacao do celular)
    ficam de fora. Para trocar o armazenamento por um servico na nuvem
    no futuro, basta alterar esta funcao e a remocao abaixo.
    """
    try:
        imagem = Image.open(arquivo.stream)
        if imagem.format not in FORMATOS_ACEITOS:
            raise ErroImagem("Use fotos nos formatos JPG, PNG ou WebP.")
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
        imagem.save(os.path.join(pasta_fotos(), nome), "JPEG", quality=85, optimize=True)
        return nome
    except ErroImagem:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ErroImagem("Não consegui ler uma das fotos. Tente outro arquivo JPG, PNG ou WebP.")


def apagar_fotos(nomes):
    """Apaga arquivos de foto do disco (ignora nomes fora do padrao)."""
    for nome in nomes:
        if NOME_VALIDO.match(nome or ""):
            try:
                os.remove(os.path.join(pasta_fotos(), nome))
            except FileNotFoundError:
                pass
