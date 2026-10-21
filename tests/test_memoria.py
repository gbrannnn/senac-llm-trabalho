"""Decaimento e janela da conversa: regras de código, sem modelo."""
from datetime import date, timedelta

from src import config, memoria
from src.estado import janela_conversa, por_turno


def test_decaimento_rebaixa_e_nao_apaga():
    hoje = date(2026, 10, 20)
    assert memoria.peso_por_idade((hoje - timedelta(days=config.DECAIMENTO_DIAS)).isoformat(), hoje) == 1.0
    assert memoria.peso_por_idade((hoje - timedelta(days=config.DECAIMENTO_DIAS + 1)).isoformat(), hoje) == config.PESO_DECAIDO


def test_janela_da_conversa_corta_o_inicio():
    turnos = [{"role": "user", "content": str(i)} for i in range(20)]
    janela = janela_conversa(turnos[:10], turnos[10:])
    assert len(janela) == 2 * config.JANELA_CONVERSA_TURNOS
    assert janela[-1]["content"] == "19"           # o mais recente fica
    assert janela[0]["content"] == str(20 - 2 * config.JANELA_CONVERSA_TURNOS)


def test_por_turno_zera_com_none_e_acumula_no_turno():
    assert por_turno(["fonte do turno anterior"], None) == []
    assert por_turno(["a"], ["b"]) == ["a", "b"]
