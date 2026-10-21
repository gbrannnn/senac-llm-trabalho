"""Memória de longo prazo: leitura da episódica (com decaimento) e regra de alergia.

- episódica: tabela `historico` + embedding do par pedido+receita; lida por
  similaridade ao pedido atual, SEMPRE filtrada por usuário;
- semântica: tabela `perfil`, lida por chave (db.perfil);
- procedural: src/prompts/regras_procedurais.md, escrita só por humano.
"""
from datetime import date

import numpy as np

from . import catalogo, config, rag

# alergia dita pela pessoa -> marcadores de alérgeno do catálogo (RDC 26/2015)
ALERGIA_PARA_MARCADOR = {
    "amendoim": {"amendoim"}, "leite": {"leite"}, "lactose": {"leite"}, "ovo": {"ovo"},
    "camarao": {"crustaceos"}, "crustaceo": {"crustaceos"}, "frutos do mar": {"crustaceos", "peixe"},
    "peixe": {"peixe"}, "soja": {"soja"}, "gluten": {"trigo", "aveia"}, "trigo": {"trigo"},
    "castanha": {"castanhas"}, "nozes": {"castanhas"}, "amendoa": {"castanhas"}, "oleaginosas": {"castanhas"},
}
RESTRICAO_PARA_ITENS = {
    "vegetariano": {"frango", "carne_bovina", "porco", "peixe", "camarao", "caldo"},
    "vegano": {"frango", "carne_bovina", "porco", "peixe", "camarao", "caldo", "ovo", "manteiga", "leite_integral",
               "leite_desnatado", "creme_de_leite", "iogurte", "queijo_parmesao", "queijo_mussarela", "ricota",
               "queijo_cottage", "cream_cheese", "queijo_feta", "queijo_cheddar", "mel", "maionese", "creme_azedo",
               "leite_condensado"},
}


def marcadores_de_alergia(alergias: list[str]) -> tuple[set[str], list[str]]:
    """Devolve (marcadores conhecidos, alergias que o catálogo não sabe mapear).

    Uma alergia desconhecida não é ignorada: o filtro passa a procurar o NOME dela
    nos ingredientes (conservador), e a saída declara isso."""
    conhecidos, desconhecidas = set(), []
    for a in alergias:
        chave = catalogo.singular(a)
        if chave in ALERGIA_PARA_MARCADOR:
            conhecidos |= ALERGIA_PARA_MARCADOR[chave]
        else:
            desconhecidas.append(a)
    return conhecidos, desconhecidas


def peso_por_idade(dia: str, hoje: date | None = None) -> float:
    idade = ((hoje or date.today()) - date.fromisoformat(dia)).days
    return config.PESO_DECAIDO if idade > config.DECAIMENTO_DIAS else 1.0


def lembrar(historico: list[dict], pedido: str, k: int = 3) -> list[dict]:
    """Top-k do histórico por similaridade x peso de idade (decaimento rebaixa, não apaga)."""
    com_vetor = [h for h in historico if h["embedding"] is not None]
    if not com_vetor:
        return []
    consulta = rag.embedar([pedido])[0]
    notas = [(float(np.dot(h["embedding"], consulta)) * peso_por_idade(h["data"]), h) for h in com_vetor]
    notas.sort(key=lambda x: -x[0])
    return [{"receita_id": h["receita_id"], "receita_nome": h["receita_nome"], "data": h["data"],
             "nota": round(n, 3), "decaido": peso_por_idade(h["data"]) < 1} for n, h in notas[:k]]


def embedding_episodio(pedido: str, receita_nome: str) -> np.ndarray:
    return rag.embedar([f"Pedido: {pedido}\nReceita: {receita_nome}"])[0]
