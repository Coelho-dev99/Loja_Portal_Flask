"""Limitador simples de requisicoes, guardado na memoria do servidor.

Serve para um site pequeno rodando em um unico processo. Se um dia o site
rodar em varios processos, cada um tera a sua propria contagem.
"""
import threading
import time

_trava = threading.Lock()
_registros = {}


def permitir(chave, maximo, janela_segundos):
    """True se ainda cabe mais uma requisicao dentro da janela de tempo."""
    agora = time.monotonic()
    with _trava:
        recentes = [t for t in _registros.get(chave, []) if agora - t < janela_segundos]
        if len(recentes) >= maximo:
            _registros[chave] = recentes
            return False
        recentes.append(agora)
        _registros[chave] = recentes

        if len(_registros) > 5000:  # limpeza ocasional
            for k in [k for k, v in _registros.items() if not v or agora - v[-1] >= janela_segundos]:
                _registros.pop(k, None)
        return True


def bloqueado(chave, maximo, janela_segundos):
    """True se a chave ja atingiu o maximo de registros dentro da janela.

    Nao conta a consulta em si: use junto com registrar() e esquecer(), por
    exemplo para contar so as tentativas de login que FALHARAM.
    """
    agora = time.monotonic()
    with _trava:
        recentes = [t for t in _registros.get(chave, []) if agora - t < janela_segundos]
        if recentes:
            _registros[chave] = recentes
        else:
            _registros.pop(chave, None)
        return len(recentes) >= maximo


def registrar(chave):
    """Anota uma ocorrencia (ex.: uma senha errada) para a chave."""
    agora = time.monotonic()
    with _trava:
        _registros.setdefault(chave, []).append(agora)

        if len(_registros) > 5000:  # limpeza ocasional: tira o que esta parado ha 1 hora
            for k in [k for k, v in _registros.items() if not v or agora - v[-1] >= 3600]:
                _registros.pop(k, None)


def esquecer(chave):
    """Zera a contagem da chave (ex.: depois de um login correto)."""
    with _trava:
        _registros.pop(chave, None)


def zerar():
    with _trava:
        _registros.clear()
