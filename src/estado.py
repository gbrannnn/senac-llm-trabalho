"""O estado que atravessa o grafo, com os reducers (docs/grafo.md §7).

O estado persiste entre turnos da mesma conversa (o checkpointer grava tudo
por `thread_id`). Por isso os campos acumulados são "por turno": o nó `inicio`
manda `None` e o reducer zera a lista; sem isso, as fontes do turno anterior
apareceriam na saída deste.
"""
from typing import Annotated, Any, TypedDict

from . import config


def por_turno(atual: list | None, novo: list | None) -> list:
    """Acumula dentro do turno; `None` zera (início de turno)."""
    if novo is None:
        return []
    return (atual or []) + novo


def janela_conversa(atual: list | None, novo: list | None) -> list:
    """Acumula a conversa e corta pelo INÍCIO: os turnos mais antigos saem primeiro.

    O prompt de sistema não mora aqui (é montado a cada chamada), então nunca é cortado."""
    juntos = (atual or []) + (novo or [])
    return juntos[-2 * config.JANELA_CONVERSA_TURNOS:]


def somar_uso(atual: dict | None, novo: dict | None) -> dict:
    if novo is None:
        return {"tokens": 0, "chamadas": 0, "segundos": 0.0}
    base = dict(atual or {"tokens": 0, "chamadas": 0, "segundos": 0.0})
    for chave in ("tokens", "chamadas", "segundos"):
        base[chave] = round(base.get(chave, 0) + novo.get(chave, 0), 2)
    base["maior_janela"] = max(base.get("maior_janela", 0), novo.get("maior_janela", 0))
    return base


CAMPOS: dict[str, Any] = {
    # identidade do turno — escritos só por `inicio`, a partir da sessão (nunca do modelo)
    "entrada": str,
    "usuario_id": str,
    "thread_id": str,
    "execucao_id": str,
    "inicio_ts": float,
    # contexto carregado em paralelo por três nós
    "perfil": dict | None,
    "estoque": list,
    "recentes": list,
    "fontes": Annotated[list, por_turno],          # escrito por 3 nós paralelos e por vários depois
    # decisões
    "triagem": dict | None,
    "disponiveis_extra": list,                     # o que a pessoa disse ter e o estoque não registra
    "escolhas": Annotated[list, por_turno],
    "agente_msgs": Annotated[list, por_turno],     # bloco de rascunho do agente do turno
    "passos_agente": int,
    "recuperacoes": Annotated[list, por_turno],
    "descartes_oms": Annotated[list, por_turno],
    "rejeitadas": Annotated[list, por_turno],      # ids reprovados no turno
    "proposta": dict | None,
    "nutricao": dict | None,
    "veredito": dict | None,
    "rodadas": int,
    "resposta_consultor": dict | None,
    "itens_ditos": list,                           # o que o modelo extraiu do texto, antes do catálogo
    "itens_propostos": list,                       # já casados com o catálogo: o que a pessoa aprova
    "atualizacao_perfil": dict | None,
    "expira_em": float | None,                     # gravado ANTES da pausa: a retomada roda o nó de novo
    "pendentes": list,
    "decisao_humana": dict | None,
    "efeito": dict | None,                         # resultado da escrita (com ja_existia)
    "termino": str | None,
    "erro": str | None,
    "saida": dict | None,
    "uso": Annotated[dict, somar_uso],
    "conversa": Annotated[list, janela_conversa],  # só texto conversacional: o que a pessoa disse e leu
}

# operator.add seria o reducer ingênuo; `por_turno` existe porque o checkpointer guarda o turno anterior
Estado = TypedDict("Estado", CAMPOS, total=False)

# Variante para a demonstração do §7.2: o MESMO estado, sem reducer em `fontes`.
EstadoSemReducer = TypedDict("EstadoSemReducer", {**CAMPOS, "fontes": list}, total=False)

