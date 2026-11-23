"""Controle de acesso local (ASI03) e suspensão do agente (docs/seguranca.md §3.2, controles C1 e C5).

Antes da v1.1.0, quem rodava `python -m src.main --usuario bruno ...` lia e alterava o
perfil do Bruno: o `--usuario` era a identidade, sem prova nenhuma.

Agora cada usuário tem um TOKEN, e a CLI só executa se `NUTRI_TOKEN` provar a identidade
pedida em `--usuario`. O banco guarda só o SHA-256 do token (tabela `credenciais`), e a
comparação é em tempo constante. Sem token, token errado ou erro ao conferir: a execução
NÃO acontece (fail-closed), e o trace registra `termino=acesso_negado`.

O operador tem uma credencial à parte (papel `operador`), que serve para duas coisas:
listar/expirar as pausas de todos (`--pendentes`) e SUSPENDER o agente:

    python -m src.acesso suspender "motivo"     # com NUTRI_TOKEN do operador
    python -m src.acesso retomar
    python -m src.acesso estado
    python -m src.acesso token ana              # imprime o token local da ana (dados/tokens_locais.json)

Suspenso, toda execução termina em `suspenso` antes de tocar no modelo ou no banco.

O que este controle NÃO cobre (risco aceito, docs/seguranca.md §3.3): quem lê os arquivos da
máquina lê `dados/tokens_locais.json` e o próprio `nutri.sqlite`, que não é cifrado. O token
separa usuários da CLI; ele não protege o disco.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
import sys
from datetime import datetime

from . import config, db

TOKENS_LOCAIS = config.DADOS / "tokens_locais.json"   # NÃO versionado (.gitignore): simula a custódia de cada pessoa

OPERADOR = "operador"   # as tabelas `credenciais` e `controle` estão em db.ESQUEMA


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def iniciar() -> None:
    db.iniciar()


def emitir(usuario_id: str, papel: str = "usuario") -> str:
    """Cria (ou troca) o token de um usuário. Devolve o token em claro UMA vez; o banco guarda o hash."""
    iniciar()
    token = secrets.token_urlsafe(18)
    with db.conexao() as con:
        con.execute("INSERT INTO credenciais VALUES (?, ?, ?, ?) ON CONFLICT(usuario_id) DO UPDATE SET "
                    "token_sha256 = excluded.token_sha256, papel = excluded.papel, criado_em = excluded.criado_em",
                    (usuario_id, _hash(token), papel, db.agora()))
    return token


def autenticar(usuario_id: str, token: str | None, papel: str = "usuario") -> bool:
    """True só se o token prova a identidade. Qualquer falha ao conferir conta como negação (fail-closed)."""
    if not token or not usuario_id:
        return False
    try:
        with db.conexao() as con:
            linha = con.execute("SELECT token_sha256, papel FROM credenciais WHERE usuario_id = ?", (usuario_id,)).fetchone()
    except sqlite3.Error:
        return False
    if linha is None or linha["papel"] != papel:
        return False
    return hmac.compare_digest(linha["token_sha256"], _hash(token))


def suspensao() -> dict | None:
    """O agente está suspenso? Erro ao ler o estado conta como SUSPENSO (fail-closed)."""
    try:
        iniciar()  # banco anterior à v1.1.0 ganha a tabela aqui; sem isso, o erro abaixo suspenderia tudo
        with db.conexao() as con:
            linha = con.execute("SELECT valor, por, em FROM controle WHERE chave = 'suspenso'").fetchone()
    except sqlite3.Error as erro:
        return {"motivo": f"erro ao ler o estado de suspensão: {erro}", "por": "sistema", "em": db.agora()}
    return dict(linha) | {"motivo": linha["valor"]} if linha else None


def suspender(token_operador: str | None, motivo: str) -> None:
    if not autenticar(OPERADOR, token_operador, papel=OPERADOR):
        raise PermissionError("só o operador suspende o agente (NUTRI_TOKEN do operador)")
    iniciar()
    with db.conexao() as con:
        con.execute("INSERT OR REPLACE INTO controle VALUES ('suspenso', ?, ?, ?)", (motivo, OPERADOR, db.agora()))


def retomar(token_operador: str | None) -> None:
    if not autenticar(OPERADOR, token_operador, papel=OPERADOR):
        raise PermissionError("só o operador retoma o agente (NUTRI_TOKEN do operador)")
    with db.conexao() as con:
        con.execute("DELETE FROM controle WHERE chave = 'suspenso'")


def semear_tokens(usuarios: list[str]) -> dict[str, str]:
    """Emite um token por usuário fictício e um para o operador; grava em dados/tokens_locais.json."""
    tokens = {u: emitir(u) for u in usuarios}
    tokens[OPERADOR] = emitir(OPERADOR, papel=OPERADOR)
    TOKENS_LOCAIS.write_text(json.dumps(tokens, indent=1), encoding="utf-8")
    return tokens


def token_local(usuario_id: str) -> str:
    return json.loads(TOKENS_LOCAIS.read_text(encoding="utf-8"))[usuario_id]


if __name__ == "__main__":
    import os
    sys.stdout.reconfigure(encoding="utf-8")
    comando = sys.argv[1] if len(sys.argv) > 1 else "estado"
    try:
        if comando in ("suspender", "retomar"):
            {"suspender": lambda: suspender(os.getenv("NUTRI_TOKEN"), " ".join(sys.argv[2:]) or "sem motivo informado"),
             "retomar": lambda: retomar(os.getenv("NUTRI_TOKEN"))}[comando]()
    except PermissionError as erro:
        sys.exit(f"negado: {erro}")
    if comando == "token":
        print(token_local(sys.argv[2]))
    elif comando == "suspender":
        print(f"agente SUSPENSO em {datetime.now().isoformat(timespec='seconds')}")
    elif comando == "retomar":
        print("agente retomado")
    else:
        print(json.dumps({"suspenso": suspensao()}, ensure_ascii=False))
