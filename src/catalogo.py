"""Catálogo de ingredientes: o vocabulário comum entre receita, estoque, TBCA e alérgeno.

Tudo aqui é código determinístico. O modelo nunca decide se um ingrediente é
alérgeno nem a que item do catálogo um nome corresponde.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache

from . import config


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sem_acento.lower())).strip()


def _singular_palavra(p: str) -> str:
    """Plural do português, já sem acento: camaroes->camarao, paes->pao, amendoins->amendoim,
    nozes->noz, ovos->ovo. Tirar só o 's' final dava 'camaroe' e 'amendoin' (bug pego em teste)."""
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ns", "m"), ("zes", "z"), ("res", "r")):
        if p.endswith(fim) and len(p) > len(fim):
            return p[: -len(fim)] + troca
    return p[:-1] if p.endswith("s") and len(p) > 3 else p


def singular(texto: str) -> str:
    return " ".join(_singular_palavra(p) for p in normalizar(texto).split())


@cache
def dados() -> dict:
    return json.loads(config.CATALOGO.read_text(encoding="utf-8"))


@cache
def itens() -> dict[str, dict]:
    return {i["id"]: i for i in dados()["itens"]}


@cache
def _padroes_en() -> list[tuple[re.Pattern, str]]:
    """(regex, alvo) ordenado do termo mais longo ao mais curto: 'brown sugar' vence 'sugar'."""
    pares = [(t, i["id"]) for i in dados()["itens"] for t in i["en"]]
    pares += [(t, "_basico") for t in dados()["basicos"]["termos_en"]]
    pares.sort(key=lambda p: -len(p[0]))
    return [(re.compile(rf"\b{t}\b", re.I), alvo) for t, alvo in pares]


def casar_en(ingrediente: str) -> str | None:
    """Ingrediente de receita (inglês) -> id do catálogo, '_basico', ou None."""
    for padrao, alvo in _padroes_en():
        if padrao.search(ingrediente):
            return alvo
    return None


def eh_opcional(ingrediente: str) -> bool:
    texto = ingrediente.lower()
    return any(t in texto for t in dados()["opcionais_en"])


def alergenos_por_texto(ingredientes: list[str]) -> set[str]:
    """Alérgenos achados por termo no texto bruto dos ingredientes (segunda fonte, conservadora)."""
    achados = set()
    for marcador, termos in dados()["alergenos_por_termo_en"].items():
        if any(re.search(rf"\b{t}\b", i, re.I) for i in ingredientes for t in termos):
            achados.add(marcador)
    return achados


def receita_excluida(ingredientes: list[str]) -> bool:
    proibidos = dados()["excluir_receita_en"]
    return any(re.search(rf"\b{p}\b", i, re.I) for i in ingredientes for p in proibidos)


@dataclass
class Casamento:
    texto: str
    candidatos: list[str]

    @property
    def status(self) -> str:
        return {0: "nao_reconhecido", 1: "reconhecido"}.get(len(self.candidatos), "ambiguo")


def casar_pt(nome: str) -> Casamento:
    """Nome dito pelo usuário (português) -> candidatos do catálogo.

    'leite' casa com leite integral e leite desnatado: é ambíguo, e quem resolve
    é a pessoa (docs/humano.md). Nome exato ou sinônimo exato vence casamento parcial.
    """
    alvo = normalizar(nome)
    alvo_sing = singular(nome)
    exatos, parciais = [], []
    for item in dados()["itens"]:
        nomes = [normalizar(n) for n in [item["nome"], *item["sinonimos"]]]
        if alvo in nomes or alvo_sing in [singular(n) for n in nomes]:
            exatos.append(item["id"])
        elif any(re.search(rf"\b{re.escape(alvo_sing)}", n) for n in nomes):
            parciais.append(item["id"])
    if exatos:
        return Casamento(nome, sorted(set(exatos)))
    # 'leite' não é nome de item, mas é nome de família: no uso brasileiro, "leite"
    # sozinho é leite de vaca (integral ou desnatado), não creme de leite nem leite de coco
    familia = sorted(i["id"] for i in dados()["itens"] if i.get("familia") and normalizar(i["familia"]) == alvo)
    if familia:
        return Casamento(nome, familia)
    return Casamento(nome, sorted(set(parciais)) if len(parciais) <= 3 else [])


def alergenos_de(item_id: str) -> set[str]:
    return set(itens().get(item_id, {}).get("alergenos", []))


# --- quantidades -> gramas ------------------------------------------------------

_FRACOES = {"½": 0.5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 0.25, "¾": 0.75, "⅛": 0.125}
_UNIDADES_VOLUME = {"cup": 1.0, "cups": 1.0, "tbsp": 1 / 16, "tablespoon": 1 / 16,
                    "tablespoons": 1 / 16, "tsp": 1 / 48, "teaspoon": 1 / 48, "teaspoons": 1 / 48}
_UNIDADES_MASSA = {"lb": 453.6, "lbs": 453.6, "pound": 453.6, "pounds": 453.6, "oz": 28.35,
                   "ounce": 28.35, "ounces": 28.35, "g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0}


def _numero(texto: str) -> float | None:
    texto = texto.strip()
    for simbolo, valor in _FRACOES.items():
        if simbolo in texto:
            resto = texto.replace(simbolo, "").strip()
            return valor + (float(resto) if resto.replace(".", "").isdigit() else 0)
    if re.fullmatch(r"\d+/\d+", texto):
        a, b = texto.split("/")
        return int(a) / int(b)
    try:
        return float(texto)
    except ValueError:
        return None


_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?\s*[½⅓⅔¼¾⅛]?|[½⅓⅔¼¾⅛])"


def _peso_entre_parenteses(texto: str) -> float | None:
    """'(4 ounces)', '(1/2-pound)', '(about 2 ounces)' -> gramas. Primeiro número de uma faixa."""
    for conteudo in re.findall(r"\(([^)]*)\)", texto):
        m = re.search(rf"({_NUM})(?:\s*(?:–|-|to)\s*{_NUM})?[\s-]*(lb|lbs|pounds?|oz|ounces?|g|grams?|kg)\b", conteudo)
        if m and _numero_seguro(m.group(1)):
            return sum(_numero(p) for p in m.group(1).split()) * _UNIDADES_MASSA[m.group(2)]
    return None


def _numero_seguro(texto: str) -> bool:
    return all(_numero(p) is not None for p in texto.split())


def gramas(ingrediente: str, item_id: str, xicara_g: float | None = None) -> float | None:
    """'2 Tbsp. olive oil' -> gramas. None quando a quantidade não é determinável.

    A conversão de volume usa a densidade (gramas por xícara) do item, que é
    aproximada: o resultado nutricional é estimativa, e a saída diz isso.
    Faixas ('3–4 cups') usam o primeiro número.
    """
    item = itens().get(item_id, {})
    if item.get("desprezivel"):  # ervas, baunilha, fermento: não mudam kcal nem macro
        return 0.0
    texto = ingrediente.lower().replace("-", " ").replace(".", " ")
    peso = _peso_entre_parenteses(ingrediente.lower().replace(".", ""))
    m = re.match(rf"\s*({_NUM})(?:\s*(?:–|to)\s*{_NUM})?\s*(\([^)]*\))?\s*([a-z]+)?", texto)
    if not m:
        return peso
    qtd = sum(_numero(p) for p in m.group(1).split()) if _numero_seguro(m.group(1)) else None
    if qtd is None:
        return peso
    unidade = m.group(3) or ""
    if peso is not None:
        # '1 (5-ounce) bag' e '2 ribs (3 pounds each)' multiplicam; '4 slices (4 ounces)' já é o total
        cada = m.group(2) is not None or " each" in ingrediente.lower()
        return qtd * peso if cada else peso
    if unidade in _UNIDADES_MASSA:
        return qtd * _UNIDADES_MASSA[unidade]
    if unidade in _UNIDADES_VOLUME:
        return qtd * _UNIDADES_VOLUME[unidade] * (xicara_g or item.get("xicara_g", 240))
    if unidade in ("stick", "sticks") and item_id == "manteiga":
        return qtd * 113
    if item.get("unidade_g"):  # '3 large eggs', '2 garlic cloves'
        return qtd * item["unidade_g"]
    return None
