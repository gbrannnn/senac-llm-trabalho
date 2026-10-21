"""Banco do domínio (SQLite): perfil, estoque, histórico e o livro de escritas.

Toda escrita passa por `escrever_uma_vez`, com chave de idempotência derivada
do CONTEÚDO (docs/memoria.md §5.3): o mesmo conteúdo produz a mesma chave, e a
segunda tentativa devolve `ja_existia=True` sem alterar nada.

O `usuario_id` nunca vem do modelo: é argumento que o código injeta a partir da
sessão (docs/model-card.md, lacuna L06).
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import numpy as np

from . import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS perfil (
    usuario_id TEXT PRIMARY KEY, nome TEXT, objetivo TEXT,
    alergias TEXT DEFAULT '[]', restricoes TEXT DEFAULT '[]',
    preferencias TEXT DEFAULT '[]', equipamentos TEXT DEFAULT '[]', atualizado_em TEXT);
CREATE TABLE IF NOT EXISTS estoque (
    usuario_id TEXT, item_id TEXT, quantidade REAL, unidade TEXT, atualizado_em TEXT,
    PRIMARY KEY (usuario_id, item_id));
CREATE TABLE IF NOT EXISTS historico (
    chave TEXT PRIMARY KEY, usuario_id TEXT, data TEXT, receita_id TEXT, receita_nome TEXT,
    pedido TEXT, energia_kcal REAL, embedding BLOB, criado_em TEXT);
CREATE TABLE IF NOT EXISTS escritas (
    chave TEXT PRIMARY KEY, tipo TEXT, usuario_id TEXT, conteudo TEXT, criado_em TEXT);
"""
CAMPOS_LISTA = ("alergias", "restricoes", "preferencias", "equipamentos")


@contextmanager
def conexao():
    con = sqlite3.connect(config.DB_DOMINIO)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar() -> None:
    config.DB_DOMINIO.parent.mkdir(parents=True, exist_ok=True)
    with conexao() as con:
        con.executescript(ESQUEMA)


def chave(*partes) -> str:
    bruto = json.dumps(partes, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- leitura -----------------------------------------------------------------

def perfil(usuario_id: str) -> dict | None:
    with conexao() as con:
        linha = con.execute("SELECT * FROM perfil WHERE usuario_id = ?", (usuario_id,)).fetchone()
    if not linha:
        return None
    p = dict(linha)
    for campo in CAMPOS_LISTA:
        p[campo] = json.loads(p[campo] or "[]")
    return p


def estoque(usuario_id: str) -> list[dict]:
    with conexao() as con:
        linhas = con.execute("SELECT item_id, quantidade, unidade, atualizado_em FROM estoque "
                             "WHERE usuario_id = ? AND quantidade > 0 ORDER BY item_id", (usuario_id,)).fetchall()
    return [dict(l) for l in linhas]


def historico(usuario_id: str) -> list[dict]:
    with conexao() as con:
        linhas = con.execute("SELECT chave, data, receita_id, receita_nome, pedido, energia_kcal, embedding "
                             "FROM historico WHERE usuario_id = ? ORDER BY data DESC", (usuario_id,)).fetchall()
    resultado = []
    for l in linhas:
        d = dict(l)
        d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32) if d["embedding"] else None
        resultado.append(d)
    return resultado


# --- escrita, sempre idempotente ---------------------------------------------

def escrever_uma_vez(con: sqlite3.Connection, k: str, tipo: str, usuario_id: str, conteudo: dict) -> bool:
    """Registra a escrita no livro. Devolve True se a chave já existia (nada a fazer)."""
    try:
        con.execute("INSERT INTO escritas VALUES (?, ?, ?, ?, ?)",
                    (k, tipo, usuario_id, json.dumps(conteudo, ensure_ascii=False), agora()))
        return False
    except sqlite3.IntegrityError:
        return True


def somar_estoque(usuario_id: str, itens: list[dict], dia: str | None = None) -> dict:
    """Soma quantidades ao estoque. Chave = usuário + itens + dia: a mesma nota
    reenviada no mesmo dia é reconhecida como repetição (docs/humano.md §8.5)."""
    dia = dia or date.today().isoformat()
    normalizados = sorted((i["item_id"], float(i["quantidade"] or 0), i.get("unidade") or "") for i in itens)
    k = chave("estoque", usuario_id, normalizados, dia)
    with conexao() as con:
        if escrever_uma_vez(con, k, "estoque", usuario_id, {"itens": normalizados, "dia": dia}):
            return {"chave": k, "ja_existia": True, "gravados": 0}
        for item_id, qtd, unidade in normalizados:
            con.execute("INSERT INTO estoque VALUES (?, ?, ?, ?, ?) ON CONFLICT(usuario_id, item_id) "
                        "DO UPDATE SET quantidade = quantidade + excluded.quantidade, "
                        "unidade = excluded.unidade, atualizado_em = excluded.atualizado_em",
                        (usuario_id, item_id, qtd, unidade, agora()))
    return {"chave": k, "ja_existia": False, "gravados": len(normalizados)}


def atualizar_perfil(usuario_id: str, campo: str, operacao: str, valor: str) -> dict:
    """Escrita por REGRA em código: o campo é validado contra uma lista fechada."""
    if campo not in ("objetivo", *CAMPOS_LISTA):
        raise ValueError(f"campo de perfil não permitido: {campo}")
    k = chave("perfil", usuario_id, campo, operacao, valor.strip().lower())
    with conexao() as con:
        if escrever_uma_vez(con, k, "perfil", usuario_id, {"campo": campo, "operacao": operacao, "valor": valor}):
            return {"chave": k, "ja_existia": True}
        con.execute("INSERT OR IGNORE INTO perfil (usuario_id, atualizado_em) VALUES (?, ?)", (usuario_id, agora()))
        if campo == "objetivo":
            con.execute("UPDATE perfil SET objetivo = ?, atualizado_em = ? WHERE usuario_id = ?",
                        (valor, agora(), usuario_id))
        else:
            atual = json.loads(con.execute(f"SELECT {campo} FROM perfil WHERE usuario_id = ?",
                                           (usuario_id,)).fetchone()[0] or "[]")
            v = valor.strip().lower()
            novo = [x for x in atual if x != v] if operacao == "remover" else (
                [v] if operacao == "definir" else sorted(set(atual) | {v}))
            con.execute(f"UPDATE perfil SET {campo} = ?, atualizado_em = ? WHERE usuario_id = ?",
                        (json.dumps(novo, ensure_ascii=False), agora(), usuario_id))
    return {"chave": k, "ja_existia": False}


def registrar_recomendacao(usuario_id: str, receita: dict, pedido: str, energia_kcal: float | None,
                           embedding: np.ndarray | None, dia: str | None = None) -> dict:
    dia = dia or date.today().isoformat()
    k = chave("recomendacao", usuario_id, dia, receita["id"])
    with conexao() as con:
        if escrever_uma_vez(con, k, "recomendacao", usuario_id, {"receita_id": receita["id"], "dia": dia}):
            return {"chave": k, "ja_existia": True}
        con.execute("INSERT INTO historico VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (k, usuario_id, dia, receita["id"], receita["nome"], pedido, energia_kcal,
                     embedding.astype(np.float32).tobytes() if embedding is not None else None, agora()))
    return {"chave": k, "ja_existia": False}
