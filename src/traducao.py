"""Conferência em código da tradução de receita (EN -> PT) feita pelo modelo.

A tradução é só para exibir: alérgeno, estoque e nutrição continuam calculados
sobre o original em inglês. Mesmo assim, uma linha traduzida não pode mudar a
quantidade: o 7B já leu *teaspoons* como "colheres de sopa" (docs/rag.md, E08 #7).
Por isso cada linha traduzida passa por duas regras; a que falha volta ao original.
"""
import re

from . import catalogo, citacao

# unidade em inglês -> como ela tem de aparecer em português (texto já normalizado, sem acento)
UNIDADES = [
    (r"\b(teaspoons?|tsp)\b", r"\bcolher(es)? de cha\b|\bcolherinhas?\b"),
    (r"\b(tablespoons?|tbsp)\b", r"\bcolher(es)? de sopa\b"),
    (r"\bcups?\b", r"\bxicaras?\b"),
    (r"\b(ounces?|oz)\b", r"\boncas?\b"),
    (r"\b(pounds?|lbs?)\b", r"\blibras?\b"),
    (r"\bpints?\b", r"\bpints?\b|\bquartilhos?\b"),
    (r"\bquarts?\b", r"\bquartos? de galao\b|\bquarts?\b"),
    (r"\bsticks?\b", r"\btabletes?\b|\bbarras?\b"),
    (r"\b(teaspoons?|tablespoons?|tsp|tbsp|spoons?)\b", r"\bcolher|\bcolherinha"),  # "1 stick" virou "1 colher"
]

# nomes em português que valem pelo item do catálogo, além do nome e dos sinônimos dele
NOMES_EXTRA = {"ovo": ["gema", "clara"], "chocolate": ["cacau"]}

# Itens básicos que o catálogo não confere (sal, água, óleo...) e que o 7B troca:
# "Pinch of salt" virou "pimenta-do-reino a gosto"; "egg yolks" virou "ovos claros".
# Conferidos nos dois sentidos, como as unidades.
TERMOS = [
    (r"salt", r"\bsal\b|\bsalgad"),            # "salt" casa "unsalted" ("sem sal")
    (r"pepper", r"\bpiment"),                  # pimenta, pimentão
    (r"sugar", r"\bacucar"),
    (r"\bwater\b", r"\bagua\b"),
    (r"\boils?\b", r"\boleo\b|\bazeite\b"),
    (r"\byolks?\b", r"\bgemas?\b"),
    (r"\begg whites?\b", r"\bclaras?\b"),       # "white pepper" não é clara
]


def _nomes_pt(item_id: str) -> list[str]:
    """Como o item pode aparecer em português: nome, sinônimos e o substantivo principal
    ("farinha" de "farinha de trigo"). Comparação por trecho, então "batatas" contém "batata"."""
    item = catalogo.itens()[item_id]
    nomes = [item["nome"], *item.get("sinonimos", []), *NOMES_EXTRA.get(item_id, [])]
    return {catalogo.normalizar(n) for n in nomes} | {catalogo.normalizar(item["nome"]).split()[0]}


def conferir_linha(original: str, traduzida: str) -> str | None:
    """None se a linha traduzida preserva números, unidades e o ingrediente; senão, o motivo."""
    if citacao.numeros(original) != citacao.numeros(traduzida):
        return "número diferente do original"
    en, pt = original.lower(), catalogo.normalizar(traduzida)
    for padrao_en, padrao_pt in UNIDADES:
        tem_en, tem_pt = bool(re.search(padrao_en, en)), bool(re.search(padrao_pt, pt))
        if tem_en != tem_pt:
            return "unidade diferente do original"
    for padrao_en, padrao_pt in TERMOS:
        if bool(re.search(padrao_en, en)) != bool(re.search(padrao_pt, pt)):
            return "ingrediente básico trocado (sal, pimenta, açúcar, água, óleo, gema ou clara)"
    item = catalogo.casar_en(original)
    if item in catalogo.itens() and not any(n in pt for n in _nomes_pt(item)):
        return f"o ingrediente '{catalogo.itens()[item]['nome']}' não aparece na tradução"
    return None


def aplicar(nome: str, ingredientes: list[str], nome_pt: str, ingredientes_pt: list[str]) -> dict:
    """Junta a tradução conferida: linha que falha fica em inglês, e a contagem é devolvida."""
    if len(ingredientes_pt) != len(ingredientes):
        return {"nome_pt": nome_pt.strip() or nome, "ingredientes_pt": list(ingredientes),
                "mantidas": len(ingredientes), "motivo": "a tradução não tem o mesmo número de linhas"}
    linhas, motivos = [], []
    for original, traduzida in zip(ingredientes, ingredientes_pt):
        motivo = conferir_linha(original, traduzida) if traduzida.strip() else "linha vazia"
        if motivo is None:
            linhas.append(traduzida.strip())
        else:
            linhas.append(original)
            motivos.append(motivo)
    return {"nome_pt": nome_pt.strip() or nome, "ingredientes_pt": linhas, "mantidas": len(motivos),
            "motivo": "; ".join(sorted(set(motivos))) or None}
