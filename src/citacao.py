"""Verificação de citação em código: todo NÚMERO da resposta precisa estar nas fontes.

O schema garante que o consultor devolveu {resposta, suficiente, fontes}; não
garante que a resposta saiu das fontes. Medido no caso 5 (docs/io.md): o modelo
recuperou trechos irrelevantes da OMS e respondeu "200 mg de cafeína para
grávidas" — número que não está em nenhum documento do corpus.

Cobre números (o tipo de afirmação mais perigoso aqui: dose, limite, quantidade).
Não cobre afirmação qualitativa sem número; isso fica declarado como limite.
"""
import re

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


def _normalizar(n: str) -> str:
    n = n.replace(",", ".")
    return n.rstrip("0").rstrip(".") if "." in n else n


def numeros(texto: str) -> set[str]:
    # 2.000 (milhar) e 2000 são o mesmo número
    texto = re.sub(r"(\d)\.(\d{3})\b", r"\1\2", texto)
    return {_normalizar(n) for n in _NUMERO.findall(texto)}


def _plano(texto: str) -> str:
    """Minúsculas, sem aspas/escapes de JSON e com espaços colapsados: o modelo copia
    do texto, e o texto da ferramenta vem serializado em JSON."""
    texto = texto.replace("\\n", " ").replace('\\"', '"').lower()
    texto = re.sub(r"\s+", " ", re.sub(r"[\"'`{}\[\]]", " ", texto))
    return re.sub(r"\s+([:;,.])", r"\1", texto).strip()


def trecho_existe(trecho: str, fontes_texto: list[str]) -> bool:
    """O trecho citado pelo verificador existe, literalmente, em alguma fonte?

    O modelo às vezes pula um pedaço no meio ("por 100 g: [energia 126 kcal;] proteína
    9.04 g"). Aceita-se a citação em FRAGMENTOS separados por ';', ':', ' - ' ou '…', desde que
    cada fragmento exista literalmente e ao menos um tenha 3 palavras ou mais."""
    planos = [_plano(t) for t in fontes_texto]
    fragmentos = [f for f in (_plano(x) for x in re.split(r"\s*(?:[;:]|\s-\s|\.\.\.|…)\s*", trecho)) if len(f.split()) >= 2]
    if not fragmentos or max(len(f.split()) for f in fragmentos) < 3:
        return False
    return all(any(f.rstrip(":;,.") in p for p in planos) for f in fragmentos)


def nao_sustentados(resposta: str, fontes_texto: list[str]) -> set[str]:
    """Números da resposta que não aparecem em nenhuma fonte. Vazio = sustentada."""
    nas_fontes = set().union(*(numeros(t) for t in fontes_texto)) if fontes_texto else set()
    # o ano citado como origem ("OMS (2026)") vem do metadado do trecho, que também é fonte
    return {n for n in numeros(resposta) if n not in nas_fontes}
