"""Linha de comando do agente.

    python -m src.main --usuario ana "o que eu faço pra janta?"
    python -m src.main --usuario ana --sessao s2 "comprei leite e 6 ovos"   # pode pausar
    python -m src.main --usuario ana --sessao s2 --aprovar
    python -m src.main --usuario ana --sessao s2 --editar '[{"item_id":"leite_integral","quantidade":1,"unidade":"l"}]'
    python -m src.main --usuario ana --sessao s2 --rejeitar
    python -m src.main --pendentes [--expirar]

O `thread_id` é `usuario:sessao`. Mesma sessão = mesma conversa (o checkpoint
guarda o histórico); sessão nova = conversa nova, mas a memória de longo prazo
(perfil, estoque, histórico) é a mesma.
"""
import argparse
import json
import sys
from datetime import datetime

from langgraph.types import Command

from . import config
from .grafo import montar_saida, obter_grafo, saida_da_pausa
from .registro import Registro


def executar(usuario: str, sessao: str, entrada=None, retomada: dict | None = None, nome_log: str | None = None,
             checkpoint_id: str | None = None) -> dict:
    """`checkpoint_id` retoma a partir de um ponto do passado: é como se a mesma
    aprovação chegasse de novo no momento da pausa (prova de docs/humano.md §8.5)."""
    grafo = obter_grafo()
    thread_id = f"{usuario}:{sessao}"
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": config.RECURSION_LIMIT}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    registro = Registro(nome_log or f"{usuario}-{sessao}", thread_id, usuario, entrada if retomada is None else retomada)

    if retomada is not None:
        if not grafo.get_state(cfg).next:
            registro.nota("nada pendente nesta conversa: a retomada não executou nenhum nó")
            saida = {"thread_id": thread_id, "tipo": "resposta", "resultado": "Não há nada aguardando aprovação nesta conversa.",
                     "termino": "sem_acao", "suficiencia": "suficiente"}
            registro.saida(saida)
            return {"saida": saida, "log": str(registro.caminho)}
        entrada_grafo = Command(resume=retomada)
    else:
        entrada_grafo = {"entrada": entrada, "usuario_id": usuario, "thread_id": thread_id}

    for atualizacao in grafo.stream(entrada_grafo, cfg, stream_mode="updates"):
        for no, valor in atualizacao.items():
            registro.evento(no, valor)

    estado = grafo.get_state({"configurable": {"thread_id": thread_id}})
    pausas = [i.value for t in estado.tasks for i in t.interrupts]
    if pausas:
        saida = saida_da_pausa(estado.values, pausas[0]).model_dump()
    else:
        saida = estado.values.get("saida") or montar_saida(estado.values).model_dump()
    saida["uso"] = estado.values.get("uso")
    registro.saida(saida)
    return {"saida": saida, "log": str(registro.caminho)}


def pendentes(expirar: bool) -> list[dict]:
    """Lista as conversas paradas em `interrupt`; com --expirar, encerra as vencidas sem gravar nada."""
    grafo = obter_grafo()
    threads = {c.config["configurable"]["thread_id"] for c in grafo.checkpointer.list(None)}
    achados = []
    for thread_id in sorted(threads):
        cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": config.RECURSION_LIMIT}
        for t in grafo.get_state(cfg).tasks:
            for i in t.interrupts:
                vencida = datetime.fromisoformat(i.value["expira_em"]) < datetime.now()
                achados.append({"thread_id": thread_id, "acao": i.value["acao"], "expira_em": i.value["expira_em"],
                                "vencida": vencida})
                if expirar and vencida:
                    usuario, sessao = thread_id.split(":", 1)
                    achados[-1]["resultado"] = executar(usuario, sessao, retomada={"acao": "expirar"},
                                                        nome_log=f"{usuario}-{sessao}-expirar")["saida"]["resultado"]
    return achados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Agente Nutricionista Pessoal")
    p.add_argument("texto", nargs="?", help="o que a pessoa digita")
    p.add_argument("--usuario", default="ana")
    p.add_argument("--sessao", default="s1")
    p.add_argument("--aprovar", action="store_true")
    p.add_argument("--rejeitar", action="store_true")
    p.add_argument("--editar", metavar="JSON")
    p.add_argument("--pendentes", action="store_true")
    p.add_argument("--expirar", action="store_true")
    p.add_argument("--log", help="nome do arquivo de log (sem extensão)")
    a = p.parse_args()

    if a.pendentes:
        print(json.dumps(pendentes(a.expirar), ensure_ascii=False, indent=2))
        return
    retomada = ({"acao": "aprovar"} if a.aprovar else {"acao": "rejeitar"} if a.rejeitar else
                {"acao": "editar", "itens": json.loads(a.editar)} if a.editar else None)
    if retomada is None and not a.texto:
        p.error("informe o texto, ou --aprovar/--rejeitar/--editar")
    r = executar(a.usuario, a.sessao, a.texto, retomada, a.log)
    print(r["saida"]["resultado"])
    print("\n--- saída completa ---")
    print(json.dumps(r["saida"], ensure_ascii=False, indent=2))
    print(f"\nlog: {r['log']}")


if __name__ == "__main__":
    main()
