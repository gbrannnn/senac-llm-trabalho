"""Baixa e cura as três fontes externas. Idempotente: pula o que já existe.

    python -m scripts.baixar_dados

- receitas: dataset Epicurious (Kaggle, CC BY-SA 3.0, espelho no Hugging Face)
  -> recorte curado de 300 receitas em dados/corpus/receitas.jsonl (versionado);
- TBCA: só os alimentos do catálogo, por código -> dados/tbca.json (NÃO versionado:
  a TBCA não permite reprodução; o script baixa de novo em cada máquina);
- OMS: fichas atuais + uma versão de 2018 (documento revogado, de propósito)
  -> dados/corpus/oms/*.md (versionado, CC BY-NC-SA 3.0 IGO, com atribuição).
"""
import ast
import csv
import html
import json
import random
import re
import sys
import time

import requests

from src import catalogo, config

URL_RECEITAS = ("https://huggingface.co/datasets/Hieu-Pham/kaggle_food_recipes/resolve/main/"
                "Food%20Ingredients%20and%20Recipe%20Dataset%20with%20Image%20Name%20Mapping.csv")
URL_TBCA = "https://www.tbca.net.br/base-dados/composicao_alimentos.php"
N_RECEITAS = 300
SEMENTE = 42

OMS = [
    {"id": "oms-alimentacao-saudavel-2026", "familia": "oms-alimentacao-saudavel", "titulo": "Healthy diet",
     "url": "https://www.who.int/news-room/fact-sheets/detail/healthy-diet", "data_publicacao": "2026-01-26"},
    {"id": "oms-sodio-2026", "familia": "oms-sodio", "titulo": "Sodium reduction",
     "url": "https://www.who.int/news-room/fact-sheets/detail/sodium-reduction", "data_publicacao": "2026-05-11"},
    # Revogado de propósito (docs/rag.md §4.2): meta de 30% "até 2025", depois estendida a 2030.
    {"id": "oms-sal-2018", "familia": "oms-sodio", "titulo": "Salt reduction (versão de 2018)",
     "url": "http://web.archive.org/web/20180430180905id_/http://www.who.int:80/news-room/fact-sheets/detail/salt-reduction",
     "data_publicacao": "2018-04-30"},
]


def baixar_receitas() -> None:
    destino = config.RECEITAS
    if destino.exists():
        print(f"receitas: já existe {destino}")
        return
    bruto = config.DADOS / "bruto" / "epicurious.csv"
    bruto.parent.mkdir(parents=True, exist_ok=True)
    if not bruto.exists():
        print("receitas: baixando CSV (~26 MB)")
        bruto.write_bytes(requests.get(URL_RECEITAS, timeout=120).content)
    csv.field_size_limit(10**8)
    elegiveis = []
    with bruto.open(encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            receita = _curar(linha)
            if receita:
                elegiveis.append(receita)
    random.Random(SEMENTE).shuffle(elegiveis)
    escolhidas = sorted(elegiveis[:N_RECEITAS], key=lambda r: r["id"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as f:
        for r in escolhidas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"receitas: {len(elegiveis)} elegíveis, {len(escolhidas)} escolhidas -> {destino}")


def _curar(linha: dict) -> dict | None:
    """Mantém só receita cujo ingrediente obrigatório inteiro casa com o catálogo."""
    try:
        ingredientes = ast.literal_eval(linha["Ingredients"])
    except (ValueError, SyntaxError):
        return None
    if not (3 <= len(ingredientes) <= 10) or not linha["Instructions"].strip():
        return None
    if catalogo.receita_excluida(ingredientes):
        return None
    itens = []
    for texto in ingredientes:
        alvo = catalogo.casar_en(texto)
        opcional = catalogo.eh_opcional(texto)
        if alvo is None and not opcional:
            return None
        if alvo is None:
            continue
        g = catalogo.gramas(texto, alvo) if alvo != "_basico" else None
        itens.append({"texto": texto, "item": alvo, "gramas": round(g, 1) if g is not None else None,
                      "opcional": opcional})
    principais = {i["item"] for i in itens if i["item"] != "_basico" and not i["opcional"]}
    if len(principais) < 2:
        return None
    # duas fontes de alérgeno, unidas: o item casado e o termo no texto ('egg noodles' casa só com macarrão)
    obrigatorios = [i["texto"] for i in itens if not i["opcional"]]
    alergenos = sorted(set().union(*(catalogo.alergenos_de(i) for i in principais)) | catalogo.alergenos_por_texto(obrigatorios))
    return {"id": f"R{int(linha[''] or 0):05d}", "nome": linha["Title"].strip(), "ingredientes": itens,
            "itens": sorted(principais), "alergenos": alergenos,
            "modo_preparo": linha["Instructions"].strip(), "porcoes": None, "tempo_min": None,
            "fonte": "Epicurious via Kaggle 'Food Ingredients and Recipe Dataset with Images' (CC BY-SA 3.0)"}


def baixar_tbca() -> None:
    if config.TBCA.exists():
        print(f"tbca: já existe {config.TBCA}")
        return
    sessao = requests.Session()
    sessao.get(URL_TBCA, timeout=30)
    codigos = {i["tbca"] for i in catalogo.dados()["itens"] if i["tbca"]}
    codigos |= set(catalogo.dados()["basicos"]["tbca"].values())
    tabela = {}
    for codigo in sorted(codigos):
        tabela[codigo] = _tbca_alimento(sessao, codigo)
        print(f"tbca: {codigo} {tabela[codigo]['nome'][:50]}")
        time.sleep(0.5)  # gentileza com o servidor da USP
    config.TBCA.write_text(json.dumps(tabela, ensure_ascii=False, indent=1), encoding="utf-8")


_COMPONENTES = {"energia_kcal": r"^Energia$", "proteina_g": r"^Prote.na$", "carboidrato_g": r"^Carboidrato total$",
                "lipidio_g": r"^Lip.dios$", "fibra_g": r"^Fibra alimentar$", "sodio_mg": r"^S.dio$"}


def _tbca_alimento(sessao: requests.Session, codigo: str) -> dict:
    busca = sessao.post(URL_TBCA, data={"guarda": "tomo1", "produto": codigo},
                        headers={"Referer": URL_TBCA}, timeout=30).content.decode("utf-8", "replace")
    m = re.search(rf"<a href='(int_composicao_alimentos\.php\?[^']+)'>{codigo}</a></td><td><a[^>]*>([^<]+)", busca)
    if not m:
        raise RuntimeError(f"TBCA: código {codigo} não encontrado")
    pagina = sessao.get(f"https://www.tbca.net.br/base-dados/{html.unescape(m.group(1))}",
                        timeout=30).content.decode("utf-8", "replace")
    valores = {}
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", pagina, re.S):
        celulas = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]
        if len(celulas) < 3:
            continue
        rotulo, unidade, por_100g = celulas[0], celulas[1], celulas[2]
        for chave, padrao in _COMPONENTES.items():
            if re.match(padrao, rotulo) and (chave != "energia_kcal" or unidade == "kcal"):
                valores[chave] = _valor_tbca(por_100g)
    return {"codigo": codigo, "nome": html.unescape(m.group(2)).strip(), "por_100g": valores}


def _valor_tbca(texto: str) -> float | None:
    texto = texto.strip().lower()
    if texto in ("tr", ""):           # 'tr' = traço: presente em quantidade não quantificável
        return 0.0
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None                    # 'NA', '-': não analisado


def baixar_oms() -> None:
    config.CORPUS_OMS.mkdir(parents=True, exist_ok=True)
    for doc in OMS:
        destino = config.CORPUS_OMS / f"{doc['id']}.md"
        if destino.exists():
            print(f"oms: já existe {destino.name}")
            continue
        pagina = requests.get(doc["url"], timeout=60).content.decode("utf-8", "replace")
        texto = _html_para_md(pagina)
        cabecalho = "\n".join(f"{k}: {v}" for k, v in doc.items())
        destino.write_text(f"---\n{cabecalho}\nlicenca: CC BY-NC-SA 3.0 IGO — © World Health Organization\n---\n\n{texto}\n",
                           encoding="utf-8")
        print(f"oms: {destino.name} ({len(texto.split())} palavras)")


def _html_para_md(pagina: str) -> str:
    m = re.search(r"<article.*?</article>", pagina, re.S) or re.search(r"<main.*?</main>", pagina, re.S)
    s = m.group(0) if m else pagina
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S)
    s = re.sub(r"<h([1-4])[^>]*>", lambda g: "\n\n" + "#" * int(g.group(1)) + " ", s)
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"<(p|br|div)[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").replace("�", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    # o rodapé de referências não responde pergunta nenhuma e polui o índice
    return re.split(r"\n#+ References\b", s.strip())[0].strip()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    baixar_receitas()
    baixar_tbca()
    baixar_oms()
