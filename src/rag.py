"""Recuperação: busca vetorial em dois índices pequenos, guardados em arquivo .npz.

Por que não um banco vetorial: são ~300 receitas e ~60 trechos da OMS. Um
produto escalar sobre uma matriz de 360 x 1024 leva menos de 1 ms; um serviço
a mais custaria mais do que resolve (docs/rag.md §4.1).

- receitas: uma receita = um trecho (a receita perde sentido partida);
- OMS: um trecho por seção `##` do documento, com o título herdado;
- desempate de contradição: entre trechos da mesma `familia`, só a versão de
  maior `data_publicacao` sobrevive, e o descarte é registrado.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cache

import numpy as np

from . import config, llm


def embedar(textos: list[str]) -> np.ndarray:
    try:
        resposta = llm.cliente().embeddings.create(model=config.EMBED_MODELO, input=textos)
    except Exception as erro:  # rede/servidor: não há o que o modelo contorne
        raise llm.ErroFatal(f"falha no embedding: {erro}") from erro
    matriz = np.array([d.embedding for d in resposta.data], dtype=np.float32)
    return matriz / np.linalg.norm(matriz, axis=1, keepdims=True)


# --- corpus -> trechos -------------------------------------------------------

def receitas() -> list[dict]:
    with config.RECEITAS.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f]


@cache
def receitas_por_id() -> dict[str, dict]:
    return {r["id"]: r for r in receitas()}


def _texto_receita(r: dict) -> str:
    ingredientes = "; ".join(i["texto"] for i in r["ingredientes"])
    return f"Receita: {r['nome']}\nIngredientes: {ingredientes}\nPreparo: {r['modo_preparo'][:400]}"


MAX_PALAVRAS_TRECHO = 200


def _secoes(corpo: str) -> list[tuple[str, list[str]]]:
    """Divide pela estrutura do documento. Título = linha `#` OU linha curta solta
    (a página da OMS marca alguns títulos sem <h2>, como 'WHO response')."""
    secoes: list[tuple[str, list[str]]] = [("Introdução", [])]
    for linha in corpo.splitlines():
        limpa = linha.strip()
        if not limpa:
            continue
        curta_solta = len(limpa.split()) <= 4 and not limpa.startswith("-") and not re.search(r"[.,:;]$", limpa)
        if limpa.startswith("#") or curta_solta:
            titulo = limpa.lstrip("# ").strip()
            if titulo.lower() == "references":
                break  # referências bibliográficas não respondem pergunta e poluem o índice
            secoes.append((titulo, []))
        else:
            secoes[-1][1].append(limpa)
    return [(t, linhas) for t, linhas in secoes if linhas]


def trechos_oms() -> list[dict]:
    """Corte por estrutura; seção longa vira janelas de até 200 palavras por parágrafo,
    cada uma com o título herdado (docs/rag.md §4.3)."""
    trechos = []
    for arquivo in sorted(config.CORPUS_OMS.glob("*.md")):
        _, cabecalho, corpo = arquivo.read_text(encoding="utf-8").split("---", 2)
        meta = dict(l.split(": ", 1) for l in cabecalho.strip().splitlines())
        n = 0
        for titulo, linhas in _secoes(corpo):
            janela: list[str] = []
            for linha in linhas + [None]:
                cheia = linha is None or (janela and len(" ".join(janela + [linha]).split()) > MAX_PALAVRAS_TRECHO)
                if cheia and janela:
                    texto = "\n".join(janela)
                    if len(texto.split()) >= 15:
                        trechos.append({"id": f"{meta['id']}#{n:02d}", "documento": meta["id"], "familia": meta["familia"],
                                        "data_publicacao": meta["data_publicacao"], "secao": titulo, "url": meta["url"],
                                        "texto": f"Documento: {meta['titulo']} ({meta['data_publicacao']})\n"
                                                 f"Seção: {titulo}\n\n{texto}"})
                        n += 1
                    janela = []
                if linha is not None:
                    janela.append(linha)
    return trechos


# --- índice ------------------------------------------------------------------

def _hash_corpus(textos: list[str]) -> str:
    return hashlib.sha256("\n".join(textos).encode("utf-8")).hexdigest()[:12]


def indexar() -> dict:
    config.INDICE.mkdir(parents=True, exist_ok=True)
    info = {}
    for nome, itens, texto in (("receitas", receitas(), _texto_receita), ("oms", trechos_oms(), lambda t: t["texto"])):
        textos = [texto(i) for i in itens]
        vetores = np.vstack([embedar(textos[i:i + 32]) for i in range(0, len(textos), 32)])
        versao = f"idx-{nome}-{_hash_corpus(textos)}"
        np.savez(config.INDICE / f"{nome}.npz", vetores=vetores,
                 ids=np.array([i["id"] for i in itens]), versao=versao)
        info[nome] = {"versao": versao, "trechos": len(itens), "dimensoes": int(vetores.shape[1])}
    (config.INDICE / "info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


@cache
def _indice(nome: str) -> tuple[np.ndarray, list[str], str]:
    dados = np.load(config.INDICE / f"{nome}.npz")
    return dados["vetores"], list(dados["ids"]), str(dados["versao"])


def versoes_indice() -> dict[str, str]:
    return {n: _indice(n)[2] for n in ("receitas", "oms")}


@cache
def _oms_por_id() -> dict[str, dict]:
    return {t["id"]: t for t in trechos_oms()}


def _top(nome: str, consulta: str, k: int) -> list[tuple[str, float]]:
    vetores, ids, _ = _indice(nome)
    notas = vetores @ embedar([consulta])[0]
    ordem = np.argsort(-notas)[:k]
    return [(ids[i], float(notas[i])) for i in ordem]


def buscar_receitas(consulta: str, k: int = config.K_RECEITAS) -> list[tuple[dict, float]]:
    return [(receitas_por_id()[i], nota) for i, nota in _top("receitas", consulta, k)]


@dataclass
class ResultadoOMS:
    trechos: list[tuple[dict, float]]
    descartados: list[dict] = field(default_factory=list)


def buscar_oms(consulta: str, k: int = config.K_OMS, desempate: bool | None = None) -> ResultadoOMS:
    """Recupera 2k e só então aplica o desempate, para que o descarte de uma versão
    antiga não esvazie o resultado."""
    brutos = [(_oms_por_id()[i], nota) for i, nota in _top("oms", consulta, k * 2)]
    if not (config.DESEMPATE_OMS if desempate is None else desempate):
        return ResultadoOMS(brutos[:k])
    mais_recente: dict[str, str] = {}
    for t, _ in brutos:
        mais_recente[t["familia"]] = max(mais_recente.get(t["familia"], ""), t["data_publicacao"])
    vigentes, descartados = [], []
    for t, nota in brutos:
        if t["data_publicacao"] < mais_recente[t["familia"]]:
            descartados.append({"id": t["id"], "data_publicacao": t["data_publicacao"],
                                "substituido_por_data": mais_recente[t["familia"]]})
        else:
            vigentes.append((t, nota))
    return ResultadoOMS(vigentes[:k], descartados)
