"""Remoção a pedido do titular (LGPD art. 18, VI) e a varredura que a verifica.

    python -m src.remover <usuario_id>            # remove e varre
    python -m src.remover <usuario_id> --varrer   # só varre

A varredura é INDEPENDENTE da remoção: não pergunta à remoção o que ela apagou,
procura o identificador em cada estrutura (docs/memoria.md §5.4).

Estruturas onde o `usuario_id` cai, e a ação em cada uma:
  1. perfil, estoque, historico (SQL)   -> DELETE. O vetor episódico mora na mesma
     linha do histórico: apagar a linha apaga o vetor (não há tombstone).
  2. escritas (livro de idempotência)   -> DELETE.
  3. checkpoints do LangGraph           -> DELETE das conversas `usuario:*`.
  4. logs/*.jsonl                       -> o arquivo do titular é apagado; menção em
     outro arquivo é substituída por "[removido]".
  5. memória procedural                 -> NÃO é editada por código: se o id aparecer,
     a varredura acusa, e um humano reescreve a regra.
Índices de receitas e OMS não têm dado de pessoa: entram na varredura só para provar isso.
"""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime

from . import config, db

TABELAS = ("perfil", "estoque", "historico", "escritas")


def _compactar(arquivo) -> None:
    """DELETE não apaga bytes: a linha removida fica em página livre e, no modo WAL, no
    arquivo -wal. Medido (docs/evidencias/E05): sem o checkpoint do WAL, o id do titular
    continuava em 1.469 bytes do banco de checkpoints depois do DELETE + VACUUM."""
    con = sqlite3.connect(arquivo)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


def remover(usuario_id: str) -> dict:
    relatorio = {}
    with db.conexao() as con:
        for t in TABELAS:
            relatorio[t] = con.execute(f"DELETE FROM {t} WHERE usuario_id = ?", (usuario_id,)).rowcount
    _compactar(config.DB_DOMINIO)
    if config.DB_CHECKPOINTS.exists():
        con = sqlite3.connect(config.DB_CHECKPOINTS)
        try:
            for t in ("checkpoints", "writes"):
                relatorio[f"checkpoint.{t}"] = con.execute(f"DELETE FROM {t} WHERE thread_id LIKE ?",
                                                           (f"{usuario_id}:%",)).rowcount
            con.commit()
        finally:
            con.close()
        _compactar(config.DB_CHECKPOINTS)
    apagados, redigidos = 0, 0
    for arquivo in sorted(config.LOGS.glob("*.jsonl")):
        texto = arquivo.read_text(encoding="utf-8")
        primeira = json.loads(texto.splitlines()[0]) if texto else {}
        if primeira.get("usuario_id") == usuario_id:
            arquivo.unlink()
            apagados += 1
        elif usuario_id in texto:
            arquivo.write_text(texto.replace(usuario_id, "[removido]"), encoding="utf-8")
            redigidos += 1
    relatorio["logs.apagados"], relatorio["logs.redigidos"] = apagados, redigidos
    # o registro da remoção não guarda o identificador: guarda o hash
    with (config.LOGS / "remocoes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"data": datetime.now().isoformat(timespec="seconds"),
                            "titular_sha256": hashlib.sha256(usuario_id.encode()).hexdigest()[:16],
                            "relatorio": relatorio}, ensure_ascii=False) + "\n")
    return relatorio


def varrer(usuario_id: str) -> dict:
    """Procura o identificador em todas as estruturas. Tudo 0 = removido."""
    achados = {}
    with db.conexao() as con:
        for t in TABELAS:
            achados[t] = con.execute(f"SELECT COUNT(*) FROM {t} WHERE usuario_id = ?", (usuario_id,)).fetchone()[0]
        # o id pode aparecer DENTRO de conteúdo de outra linha (ex.: texto do pedido)
        achados["sql.texto_livre"] = sum(con.execute(f"SELECT COUNT(*) FROM {t} WHERE CAST({c} AS TEXT) LIKE ?",
                                                     (f"%{usuario_id}%",)).fetchone()[0]
                                         for t, c in (("historico", "pedido"), ("escritas", "conteudo")))
    # busca nos BYTES dos arquivos (inclusive o -wal, onde dado apagado pode sobreviver) e nos blobs serializados
    achados["checkpoint.bytes"] = sum(arq.read_bytes().count(usuario_id.encode())
                                      for arq in config.DADOS.glob(config.DB_CHECKPOINTS.name + "*"))
    achados["dominio.bytes"] = sum(arq.read_bytes().count(usuario_id.encode())
                                   for arq in config.DADOS.glob(config.DB_DOMINIO.name + "*"))
    achados["logs"] = sum(usuario_id in a.read_text(encoding="utf-8") for a in config.LOGS.glob("*.jsonl"))
    achados["memoria_procedural"] = (config.PROMPTS / "regras_procedurais.md").read_text(encoding="utf-8").count(usuario_id)
    achados["corpus_receitas_oms"] = (config.RECEITAS.read_text(encoding="utf-8").count(usuario_id)
                                      + sum(a.read_text(encoding="utf-8").count(usuario_id) for a in config.CORPUS_OMS.glob("*.md")))
    achados["limpo"] = not any(v for k, v in achados.items() if k != "limpo")
    return achados


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    alvo = sys.argv[1]
    if "--varrer" not in sys.argv:
        print("remoção:", json.dumps(remover(alvo), ensure_ascii=False))
    print("varredura:", json.dumps(varrer(alvo), ensure_ascii=False))
