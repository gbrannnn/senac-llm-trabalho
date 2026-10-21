"""O portão determinístico da recomendação (grafo.conferir_proposta), sem chamar o modelo.

É o controle que impede receita com alérgeno de chegar à pessoa, mesmo que o
modelo a proponha. A ferramenta de busca já esconde essas receitas; este é o
segundo controle, para o caso de o modelo inventar ou repetir um id.
"""
import time

import pytest

from src import grafo, rag


def receita_com(item: str) -> dict:
    return next(r for r in rag.receitas() if item in r["itens"])


def estado(receita: dict, alergias=(), restricoes=(), estoque=None) -> dict:
    itens = receita["itens"] if estoque is None else estoque
    return {"usuario_id": "teste", "inicio_ts": time.time(), "rodadas": 0,
            "perfil": {"alergias": list(alergias), "restricoes": list(restricoes), "objetivo": "manutenção"},
            "estoque": [{"item_id": i} for i in itens], "proposta": {"receita_id": receita["id"], "justificativa": ""}}


def test_receita_viavel_passa():
    r = receita_com("frango")
    assert grafo.conferir_proposta(estado(r)) == {"veredito": None}


def test_alergeno_do_perfil_reprova():
    r = receita_com("amendoim")
    saida = grafo.conferir_proposta(estado(r, alergias=["amendoim"]))
    assert saida["veredito"]["aprovado"] is False
    assert "amendoim" in saida["veredito"]["motivo"]
    assert saida["rejeitadas"] == [r["id"]]


def test_alergia_dita_de_outro_jeito_tambem_reprova():
    r = receita_com("camarao")
    assert grafo.conferir_proposta(estado(r, alergias=["Camarões"]))["veredito"]["aprovado"] is False


def test_restricao_vegetariana_reprova_carne():
    r = receita_com("frango")
    assert "vegetariano" in grafo.conferir_proposta(estado(r, restricoes=["vegetariano"]))["veredito"]["motivo"]


def test_ingrediente_faltando_reprova():
    r = receita_com("frango")
    sem_frango = [i for i in r["itens"] if i != "frango"]
    assert "frango" in grafo.conferir_proposta(estado(r, estoque=sem_frango))["veredito"]["motivo"]


def test_terceira_reprovacao_encerra():
    r = receita_com("amendoim")
    e = estado(r, alergias=["amendoim"])
    e["rodadas"] = 2
    assert grafo.conferir_proposta(e)["termino"] == "teto_rodadas"


@pytest.mark.parametrize("dito", ["amendoim", "Amendoins"])
def test_marcador_de_alergia(dito):
    from src import memoria
    assert memoria.marcadores_de_alergia([dito])[0] == {"amendoim"}


@pytest.mark.parametrize("texto,trocada", [
    ("Usa arroz e ovo, que você já tem.", False),
    ("É uma ótima opção para manter o peso.", True),
    ("A receita é leve e saudável.", True),
    ("Ajuda na manutenção do peso.", True),
])
def test_justificativa_sem_promessa_de_saude(texto, trocada):
    r = receita_com("frango")
    novo, motivo = grafo._justificativa(texto, r)
    assert (motivo is not None) == trocada
    if trocada:
        assert "estoque" in novo and not grafo._PROMESSA.search(novo)
