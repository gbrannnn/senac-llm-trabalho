"""O juiz LLM da propriedade 'a receita atende ao pedido?' e a validação contra rótulos humanos.

    python -m evals.juiz amostrar    # roda 20+ pedidos de recomendação pela CLI e gera a planilha para rotular
    python -m evals.juiz validar     # depois que um humano rotulou: roda o juiz, monta a matriz, decide a adoção

Arquivos em evals/juiz/:
  rubrica.md        a rubrica, a versão e o LIMIAR, declarados antes de medir
  amostra.jsonl     as saídas reais a rotular (sem veredito do juiz: quem rotula não vê o juiz)
  rotulos.csv       a planilha que o humano preenche: rotulo_humano (sim/nao), nota, rotulador
  veredictos.jsonl  o que o juiz disse sobre cada saída (gerado só no `validar`)
  validacao.json    concordância, matriz, desacordos e a decisão de adoção

O juiz é de outra família (llama3.1 8B) que o sistema (qwen2.5 7B): mitiga a auto-preferência
(Aula 11, nota 3 §2). Temperatura 0 e saída estruturada.
"""
import csv
import json
import os
import re
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from src import config, llm, rag

PASTA = config.RAIZ / "evals" / "juiz"
RUBRICA = PASTA / "rubrica.md"
AMOSTRA = PASTA / "amostra.jsonl"
ROTULOS = PASTA / "rotulos.csv"
VEREDICTOS = PASTA / "veredictos.jsonl"
VALIDACAO = PASTA / "validacao.json"
MODELO = os.getenv("JUIZ_MODELO") or "llama3.1:8b"
LIMIAR_CONCORDANCIA = 0.85
MAX_FALSOS_POSITIVOS = 1


class Veredito(BaseModel):
    adequada: bool
    motivo: str = Field(description="uma frase")


def rubrica() -> dict:
    _, cabecalho, texto = RUBRICA.read_text(encoding="utf-8").split("---", 2)
    meta = dict(l.split(": ", 1) for l in cabecalho.strip().splitlines())
    return {**meta, "texto": texto.strip()}


def julgar(pedido: str, receita_nome: str, ingredientes: list[str]) -> dict:
    r = rubrica()
    usuario = (f"Pedido da pessoa: {pedido}\nReceita recomendada: {receita_nome}\n"
               "Ingredientes:\n" + "\n".join(f"- {i}" for i in ingredientes))
    resposta = llm.cliente().chat.completions.create(
        model=MODELO, temperature=0, top_p=1,
        messages=[{"role": "system", "content": "Você é um avaliador. Aplique a rubrica e responda só o JSON.\n\n" + r["texto"]},
                  {"role": "user", "content": usuario}],
        response_format={"type": "json_schema", "json_schema": {"name": "Veredito", "schema": Veredito.model_json_schema()}})
    v = Veredito.model_validate_json(resposta.choices[0].message.content or "{}")
    return {"adequada": v.adequada, "motivo": v.motivo, "rubrica": r["versao"], "modelo": MODELO,
            "modelo_servido": resposta.model}


def julgar_saida(pedido: str, saida: dict) -> dict:
    rec = saida["receita"]
    return julgar(pedido, rec["nome"], rec["ingredientes"])


def adotado() -> bool:
    return VALIDACAO.exists() and json.loads(VALIDACAO.read_text(encoding="utf-8")).get("adotado", False)


# --- a amostra a rotular -----------------------------------------------------------------

PEDIDOS = [
    ("ana", "o que eu faço pro almoço?"), ("ana", "me sugere um lanche"), ("ana", "quero algo pro café da manhã"),
    ("ana", "uma sobremesa com banana"), ("ana", "quero um jantar com espinafre"), ("ana", "faz alguma coisa com batata"),
    ("ana", "quero um molho pra acompanhar o macarrão"), ("ana", "me sugere um acompanhamento pro frango"),
    ("ana", "o que eu janto hoje?"), ("ana", "quero uma massa"), ("ana", "uma sopa, por favor"),
    ("ana", "algo com tomate e queijo"), ("ana", "um prato com arroz"), ("ana", "quero comer algo doce"),
    ("ana", "tem alguma salada que eu consiga fazer?"), ("bruno", "o que eu almoço hoje?"),
    ("bruno", "um lanche pós-treino"), ("bruno", "algo com ovo pro jantar"), ("bruno", "me sugere uma receita com limão"),
    ("ana", "quero um pão caseiro"), ("ana", "um petisco pra receber visita"), ("bruno", "quero um prato com arroz e frango"),
    ("ana", "uma receita com cebola e alho"), ("ana", "almoço rápido com ovo"),
]
N_AMOSTRA = 20


def amostrar() -> None:
    from scripts import preparar

    from .rodar import rodar_passo
    linhas = []
    for n, (usuario, pedido) in enumerate(PEDIDOS, 1):
        if len(linhas) >= N_AMOSTRA:
            break
        preparar.semear()
        r = rodar_passo({"usuario": usuario}, {"texto": pedido}, f"juiz-{n:02d}", f"juiz_amostra_{n:02d}")
        saida = r.get("saida") or {}
        print(f"{n:02d} {usuario} {pedido!r} -> {saida.get('termino')} {(saida.get('receita') or {}).get('nome')}", flush=True)
        if not saida.get("receita"):
            continue
        rec = saida["receita"]
        linhas.append({"id": f"J{len(linhas) + 1:02d}", "usuario": usuario, "pedido": pedido, "receita_id": rec["id"],
                       "receita": rec["nome"], "receita_pt": rec.get("nome_pt"), "ingredientes": rec["ingredientes"],
                       "trace": r.get("trace"), "versao_sistema": config.VERSAO_SISTEMA})
    AMOSTRA.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")
    with ROTULOS.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "pedido", "receita", "ingredientes", "rotulo_humano", "nota", "rotulador", "classificacao_desacordo"])
        for l in linhas:
            w.writerow([l["id"], l["pedido"], f"{l['receita']} ({l['receita_pt'] or '-'})", " | ".join(l["ingredientes"]),
                        "", "", "", ""])
    print(f"{len(linhas)} saídas em {AMOSTRA.name}; planilha para rotular: {ROTULOS.relative_to(config.RAIZ)}")


# --- a validação ---------------------------------------------------------------------------

def _rotulos() -> dict[str, dict]:
    with ROTULOS.open(encoding="utf-8", newline="") as f:
        return {l["id"]: l for l in csv.DictReader(f)}


def validar() -> None:
    amostra = [json.loads(l) for l in AMOSTRA.read_text(encoding="utf-8").splitlines() if l.strip()]
    rotulos = _rotulos()
    faltando = [a["id"] for a in amostra if rotulos.get(a["id"], {}).get("rotulo_humano", "").strip().lower() not in ("sim", "nao", "não")]
    if faltando:
        sys.exit(f"rótulo humano faltando em {faltando}: preencha rotulo_humano (sim/nao) e nota em {ROTULOS.name}")
    veredictos = []
    for a in amostra:
        v = julgar(a["pedido"], a["receita"], a["ingredientes"])
        veredictos.append({"id": a["id"], **v})
        print(f"{a['id']} juiz={'sim' if v['adequada'] else 'não'}  {v['motivo']}", flush=True)
    VEREDICTOS.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in veredictos), encoding="utf-8")
    matriz = {"juiz_sim_humano_sim": 0, "juiz_sim_humano_nao": 0, "juiz_nao_humano_sim": 0, "juiz_nao_humano_nao": 0}
    desacordos = []
    for v in veredictos:
        rot = rotulos[v["id"]]
        humano = rot["rotulo_humano"].strip().lower() == "sim"
        matriz[f"juiz_{'sim' if v['adequada'] else 'nao'}_humano_{'sim' if humano else 'nao'}"] += 1
        if v["adequada"] != humano:
            desacordos.append({"id": v["id"], "juiz": v["adequada"], "humano": humano, "motivo_juiz": v["motivo"],
                               "nota_humana": rot["nota"], "classificacao": rot.get("classificacao_desacordo") or "A CLASSIFICAR"})
    n = len(veredictos)
    concordancia = (matriz["juiz_sim_humano_sim"] + matriz["juiz_nao_humano_nao"]) / n
    fp = matriz["juiz_sim_humano_nao"]
    resultado = {"rubrica": rubrica()["versao"], "modelo_juiz": MODELO, "n": n, "matriz": matriz,
                 "concordancia": round(concordancia, 4), "falsos_positivos": fp, "falsos_negativos": matriz["juiz_nao_humano_sim"],
                 "limiar": {"concordancia": LIMIAR_CONCORDANCIA, "max_falsos_positivos": MAX_FALSOS_POSITIVOS},
                 "adotado": concordancia >= LIMIAR_CONCORDANCIA and fp <= MAX_FALSOS_POSITIVOS,
                 "rotuladores": sorted({r["rotulador"] for r in rotulos.values() if r["rotulador"]}),
                 "desacordos": desacordos}
    VALIDACAO.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"""
                     humano: sim   humano: não
  juiz: sim       {matriz['juiz_sim_humano_sim']:10d}  {matriz['juiz_sim_humano_nao']:12d}   <- falsos positivos
  juiz: não       {matriz['juiz_nao_humano_sim']:10d}  {matriz['juiz_nao_humano_nao']:12d}

  concordância {concordancia:.0%} (limiar {LIMIAR_CONCORDANCIA:.0%}) · falsos positivos {fp} (máximo {MAX_FALSOS_POSITIVOS})
  -> {'ADOTADO' if resultado['adotado'] else 'NÃO ADOTADO'}; {len(desacordos)} desacordo(s) a ler, em {VALIDACAO.name}""")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"amostrar": amostrar, "validar": validar}[sys.argv[1]]()
