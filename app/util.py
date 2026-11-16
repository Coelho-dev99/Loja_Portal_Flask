import re
import unicodedata
from decimal import Decimal, InvalidOperation


def slugify(texto):
    """'Almofada Coração' -> 'almofada-coracao' (usado nos enderecos do site)."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()


def ler_decimal(texto, minimo, maximo, casas=2):
    """Converte '12,50' em Decimal dentro dos limites. Retorna None se invalido."""
    try:
        valor = Decimal((texto or "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    if (
        not valor.is_finite()
        or valor < Decimal(str(minimo))
        or valor > Decimal(str(maximo))
    ):
        return None
    return valor.quantize(Decimal(1).scaleb(-casas))


def ler_inteiro(texto, minimo, maximo):
    """Converte texto em inteiro dentro dos limites. Retorna None se invalido."""
    try:
        valor = int((texto or "").strip())
    except ValueError:
        return None
    return valor if minimo <= valor <= maximo else None
