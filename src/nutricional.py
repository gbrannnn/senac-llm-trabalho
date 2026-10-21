"""Cálculo nutricional determinístico: gramas do ingrediente x TBCA / 100.

Nada aqui chama o modelo. Quando um ingrediente não tem quantidade conhecida
ou não tem dado na TBCA, ele fica FORA do cálculo e a saída diz isso
(`completa=False`) — em vez de inventar um número (caso C16 da avaliação).
"""
import json
from functools import cache

from . import catalogo, config
from .esquemas import Nutricao

# densidade dos básicos que pesam na conta (g por xícara)
_XICARA_BASICOS = {"sugar": 200, "olive oil": 216, "vegetable oil": 218, "canola oil": 218, "oil": 218, "salt": 292}
_COMPONENTES = ("energia_kcal", "proteina_g", "carboidrato_g", "lipidio_g", "sodio_mg")


@cache
def tbca() -> dict:
    return json.loads(config.TBCA.read_text(encoding="utf-8"))


def por_100g(codigo: str) -> dict | None:
    return tbca().get(codigo)


def _basico(texto: str) -> tuple[str | None, float | None]:
    """'2 Tbsp. olive oil' -> (código TBCA, gramas). Básico sem peso nutricional -> (None, 0)."""
    mapa = catalogo.dados()["basicos"]["tbca"]
    for termo in sorted(mapa, key=len, reverse=True):
        if termo in texto.lower():
            return mapa[termo], catalogo.gramas(texto, "_basico", xicara_g=_XICARA_BASICOS[termo])
    return None, 0.0  # água, gelo, temperos secos


_SAL = "BRC0020L"
_OLEOS = {"BRC0030D", "BRC0002D"}
LIMITE_SAL_INGERIDO_G = 20      # acima disso é salmoura ou água do cozimento, não tempero
LIMITE_OLEO_INGERIDO_G = 120    # acima disso (ou 'for frying') é óleo de fritura


def _nao_ingerido(texto: str, codigo: str, g: float) -> str | None:
    """Sal de salmoura e óleo de fritura não são ingeridos inteiros, e a TBCA não diz quanto fica.

    Somar a xícara de sal da salmoura dá 100 mil mg de sódio — número que parece
    preciso e é falso. O certo é deixar fora e dizer por quê (docs/case.md)."""
    t = texto.lower()
    if codigo == _SAL and g > LIMITE_SAL_INGERIDO_G:
        return "sal de salmoura ou de cozimento: quantidade ingerida desconhecida"
    if codigo in _OLEOS and ("fry" in t or "frying" in t or g > LIMITE_OLEO_INGERIDO_G):
        return "óleo de fritura: quantidade absorvida desconhecida"
    return None


def calcular(receita: dict) -> Nutricao:
    totais = dict.fromkeys(_COMPONENTES, 0.0)
    fora = []
    for ing in receita["ingredientes"]:
        if ing["opcional"]:
            continue
        if ing["item"] == "_basico":
            codigo, g = _basico(ing["texto"])
            if codigo is None:
                continue
            if g is None:  # 'salt, to taste' já é opcional; 'salt' sem medida: sem dado
                fora.append(ing["texto"])
                continue
            if motivo := _nao_ingerido(ing["texto"], codigo, g):
                fora.append(f"{ing['texto']} ({motivo})")
                continue
        else:
            item = catalogo.itens()[ing["item"]]
            if item.get("desprezivel"):
                continue
            codigo, g = item["tbca"], ing["gramas"]
            if codigo is None or g is None:
                fora.append(ing["texto"])
                continue
        valores = tbca()[codigo]["por_100g"]
        for c in _COMPONENTES:
            totais[c] += (valores.get(c) or 0.0) * g / 100
    return Nutricao(**{c: round(v, 1) for c, v in totais.items()}, completa=not fora, fora_do_calculo=fora)
