"""Imprime os nós e as arestas do grafo QUE O SISTEMA EXECUTA (src.grafo.obter_grafo).

    python conferir_grafo.py

Não monta grafo próprio: importa o objeto compilado que src/main.py usa.
"""
import sys

from src.grafo import obter_grafo

sys.stdout.reconfigure(encoding="utf-8")
desenho = obter_grafo().get_graph()

print(f"NÓS ({len(desenho.nodes)}):")
for nome in desenho.nodes:
    print(f"  {nome}")

print(f"\nARESTAS ({len(desenho.edges)}; [cond] = condicional, com o rótulo da rota):")
for a in desenho.edges:
    # o LangGraph omite o rótulo quando ele é igual ao nome do destino
    rotulo = f"  [cond: {a.data or a.target}]" if a.conditional else ""
    print(f"  {a.source} -> {a.target}{rotulo}")
