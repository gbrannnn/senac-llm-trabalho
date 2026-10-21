"""Executa os seis casos do §9 e grava cada log em logs/caso<N>_*.jsonl.

    python -m scripts.preparar --banco    # estado inicial conhecido
    python -m scripts.demonstrar

Os textos de entrada são exatamente o que uma pessoa digitaria. Nenhuma saída é
escrita à mão: tudo o que docs/io.md mostra sai daqui.
"""
import json
import sys

from src.grafo import obter_grafo
from src.main import executar

CASOS = [
    (1, "ana", "caso1", "oi! o que eu posso fazer pra jantar hoje?"),
    (2, "ana", "caso2", "tenho abobrinha aqui, me sugere alguma coisa com abobrinha"),
    (3, "ana", "caso3", "quanta proteína tem 100 g de tofu e 100 g de ovo?"),
    (4, "ana", "caso4", "amanhã vou comprar brócolis e frango, me lembra de cozinhar?"),
    (5, "ana", "caso5", "o que a OMS recomenda sobre cafeína na gravidez?"),
]
EDICAO = [{"item_id": "leite_integral", "quantidade": 1, "unidade": "l"},
          {"item_id": "ovo", "quantidade": 6, "unidade": "un"}]


def mostrar(n, r):
    s = r["saida"]
    print(f"\n=== caso {n}: {s['tipo']} / {s['termino']} / {s['suficiencia']}\n{s['resultado']}\nlog: {r['log']}")


def caso6() -> None:
    """Pausa -> aprovar editando -> a MESMA aprovação chega de novo -> nada duplica."""
    mostrar(6, executar("ana", "caso6", "comprei leite e 6 ovos", nome_log="caso6a_pausa"))
    mostrar(6, executar("ana", "caso6", retomada={"acao": "editar", "itens": EDICAO}, nome_log="caso6b_aprovar_editando"))
    # o checkpoint em que a execução estava PARADA esperando a pessoa
    historico = obter_grafo().get_state_history({"configurable": {"thread_id": "ana:caso6"}})
    pausado = next(h for h in historico if h.next == ("confirmar_estoque",))
    mostrar(6, executar("ana", "caso6", retomada={"acao": "editar", "itens": EDICAO}, nome_log="caso6c_aprovacao_repetida",
                        checkpoint_id=pausado.config["configurable"]["checkpoint_id"]))
    mostrar(6, executar("ana", "caso6", retomada={"acao": "aprovar"}, nome_log="caso6d_aprovar_sem_pendencia"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for n, usuario, sessao, texto in CASOS:
        mostrar(n, executar(usuario, sessao, texto, nome_log=f"{sessao}"))
    caso6()
    # os dois exemplos de io.md que não são casos do §9
    mostrar("io-incompleta", executar("carla", "io", "o que eu faço pra janta?", nome_log="io_incompleta"))
    mostrar("io-alergia", executar("bruno", "io", "quero um lanche com banana e pão", nome_log="io_alergia"))
    print(json.dumps({"ok": True}))
