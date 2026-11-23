"""Os scripts de demonstração e de experimento agem COMO o dono de cada usuário fictício.

Desde a v1.1.0, `src.main.executar` exige o token de quem está em `--usuario` (src/acesso.py).
Estes scripts reproduzem o que a própria pessoa faria, então apresentam o token dela, lido de
dados/tokens_locais.json; um usuário fictício criado só para o experimento (como o titular de
teste do E05) recebe um token na hora. Importar este módulo basta.
"""
import os

from src import acesso
from src import main as _main

_executar = _main.executar


def como(usuario: str) -> None:
    try:
        os.environ["NUTRI_TOKEN"] = acesso.token_local(usuario)
    except (FileNotFoundError, KeyError):
        os.environ["NUTRI_TOKEN"] = acesso.emitir(usuario)


def executar(usuario: str, *args, **kwargs):
    como(usuario)
    return _executar(usuario, *args, **kwargs)


_main.executar = executar   # os experimentos importam `src.main.executar` dentro das funções
