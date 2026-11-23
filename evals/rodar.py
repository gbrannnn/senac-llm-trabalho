"""Roda o golden dataset contra o sistema entregue e grava a rodada.

    python -m evals.rodar --versao 1.0.0
    python -m evals.rodar --versao 1.0.0 --casos R01,P02     # só alguns casos (depuração; não vale como rodada)

Cada caso:
  1. o banco volta ao estado inicial (scripts.preparar.semear: ana, bruno, carla);
  2. cada passo roda pela CLI do README, num processo novo:
        python -m src.main --usuario <u> --sessao <s> --json "<texto>"   (ou --aprovar/--editar/--rejeitar)
     ou seja, o MESMO ponto de entrada que uma pessoa usa, e não uma cópia simplificada;
  3. as verificações leem a saída, os spans do trace de cada passo e o banco antes/depois.

A rodada vai para evals/resultados/v<versao>_<data>/:
  rodada.json   versão do sistema, do dataset e da rubrica, commit, modelos, ambiente, placar por classe
  casos.jsonl   um caso por linha: cada verificação com o detalhe, a saída e os traces
  traces/       cópia dos traces de cada passo (a evidência dos números fica junto da rodada)
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts import preparar
from src import config, llm
from src.registro import commit

from . import juiz, verificacoes

RAIZ = config.RAIZ
DATASET = RAIZ / "evals" / "dataset.json"
RESULTADOS = RAIZ / "evals" / "resultados"
TOKENS = config.DADOS / "tokens_locais.json"   # existe a partir da v1.1.0 (src/acesso.py)
TIMEOUT_PASSO_S = 900


def carregar_dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def fotografar() -> dict:
    """O estado do mundo que importa: perfil, estoque e histórico de cada usuário."""
    con = sqlite3.connect(config.DB_DOMINIO)
    con.row_factory = sqlite3.Row
    try:
        perfil = {r["usuario_id"]: dict(r) for r in con.execute("SELECT * FROM perfil")}
        for p in perfil.values():
            p.pop("atualizado_em", None)
        estoque: dict[str, dict] = {}
        for r in con.execute("SELECT usuario_id, item_id, quantidade FROM estoque"):
            estoque.setdefault(r["usuario_id"], {})[r["item_id"]] = r["quantidade"]
        historico: dict[str, list] = {}
        for r in con.execute("SELECT usuario_id, pedido FROM historico ORDER BY criado_em"):
            historico.setdefault(r["usuario_id"], []).append(r["pedido"])
    finally:
        con.close()
    return {"perfil": perfil, "estoque": estoque, "historico": historico}


def _token(usuario: str) -> str | None:
    if not TOKENS.exists():
        return None
    return json.loads(TOKENS.read_text(encoding="utf-8")).get(usuario)


def rodar_passo(caso: dict, passo: dict, sessao: str, nome_log: str) -> dict:
    cmd = [sys.executable, "-m", "src.main", "--usuario", caso["usuario"], "--sessao", sessao, "--log", nome_log, "--json"]
    if "texto" in passo:
        cmd.append(passo["texto"])
    elif passo["acao"] == "aprovar":
        cmd.append("--aprovar")
    elif passo["acao"] == "rejeitar":
        cmd.append("--rejeitar")
    elif passo["acao"] == "editar":
        cmd += ["--editar", json.dumps(passo["itens"], ensure_ascii=False)]
    env = dict(os.environ)
    env.pop("NUTRI_TOKEN", None)
    if token := _token(caso.get("token_de", caso["usuario"])):
        env["NUTRI_TOKEN"] = token
    inicio = time.perf_counter()
    proc = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8",
                          timeout=TIMEOUT_PASSO_S)
    segundos = round(time.perf_counter() - inicio, 1)
    if proc.returncode != 0:
        return {"erro_processo": proc.stderr[-2000:], "segundos": segundos, "comando": cmd}
    return {**json.loads(proc.stdout.strip().splitlines()[-1]), "segundos": segundos}


def ler_spans(caminho: str | None) -> list[dict]:
    if not caminho or not Path(caminho).exists():
        return []
    return [json.loads(l) for l in Path(caminho).read_text(encoding="utf-8").splitlines() if l.strip()]


def rodar_caso(caso: dict, rodada_id: str, pasta: Path) -> dict:
    preparar.semear()  # estado inicial conhecido; cada caso usa uma sessão nova (o checkpoint não vaza)
    antes = fotografar()
    sessao = f"eval-{rodada_id}-{caso['id']}"
    passos, spans, raizes = [], [], []
    for n, passo in enumerate(caso["passos"], 1):
        r = rodar_passo(caso, passo, sessao, f"eval_{rodada_id}_{caso['id']}_{n}")
        passos.append(r)
        if "erro_processo" in r:
            break
        s = ler_spans(r.get("trace"))
        spans += s
        raizes += [x["attributes"] for x in s if x["parent_id"] is None]
        if r.get("trace"):
            (pasta / "traces").mkdir(exist_ok=True)
            shutil.copy(r["trace"], pasta / "traces" / Path(r["trace"]).name)
    depois = fotografar()
    if "erro_processo" in passos[-1]:
        achados = [{"nivel": "execucao", "verificacao": "processo", "passou": False, "detalhe": passos[-1]["erro_processo"][-300:]}]
        saida = {}
    else:
        saida = passos[-1]["saida"]
        entradas = [p["texto"] for p in caso["passos"] if "texto" in p]
        achados = verificacoes.avaliar(caso, saida, spans, raizes, antes, depois, entradas)
    return {"id": caso["id"], "classe": caso["classe"], "origem": caso["origem"], "usuario": caso["usuario"],
            "passou": all(a["passou"] for a in achados), "verificacoes": achados, "juiz": None,
            "saida": saida, "passos": [{k: v for k, v in p.items() if k != "saida"} for p in passos],
            "termino": saida.get("termino"), "segundos": round(sum(p.get("segundos", 0) for p in passos), 1)}


def placar(resultados: list[dict]) -> dict:
    por_classe: dict[str, list[bool]] = {}
    for r in resultados:
        por_classe.setdefault(r["classe"], []).append(r["passou"])
    classes = {c: {"casos": len(v), "passaram": sum(v), "taxa": round(sum(v) / len(v), 4)} for c, v in sorted(por_classe.items())}
    niveis: dict[str, list[bool]] = {}
    for r in resultados:
        for a in r["verificacoes"]:
            niveis.setdefault(a["nivel"], []).append(a["passou"])
    julgados = [r["juiz"]["adequada"] for r in resultados if r.get("juiz")]
    return {"classes": classes,
            "media_por_classe": round(sum(c["taxa"] for c in classes.values()) / len(classes), 4),
            "casos_passaram": sum(r["passou"] for r in resultados), "casos": len(resultados),
            "verificacoes_por_nivel": {n: {"total": len(v), "passaram": sum(v)} for n, v in niveis.items()},
            "juiz_adequacao": {"julgados": len(julgados), "adequadas": sum(julgados)},
            "terminos": dict(Counter(r["termino"] for r in resultados))}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Roda o golden dataset contra o sistema")
    p.add_argument("--versao", required=True, help="versão do sistema sob teste; tem de ser a de src/config.py")
    p.add_argument("--casos", help="ids separados por vírgula (só para depuração)")
    p.add_argument("--sem-juiz", action="store_true")
    a = p.parse_args()
    if a.versao != config.VERSAO_SISTEMA:
        sys.exit(f"--versao {a.versao} não é a versão do código ({config.VERSAO_SISTEMA}): a rodada sairia com o rótulo errado")

    dataset = carregar_dataset()
    casos = dataset["casos"]
    if a.casos:
        casos = [c for c in casos if c["id"] in a.casos.split(",")]
    rodada_id = datetime.now().strftime("%Y%m%d-%H%M")
    pasta = RESULTADOS / (f"v{a.versao}_{rodada_id}" + ("_parcial" if a.casos else ""))
    pasta.mkdir(parents=True, exist_ok=True)
    meta = {"versao_sistema": a.versao, "commit": commit(), "dataset": dataset["versao"], "inicio": datetime.now().isoformat(timespec="seconds"),
            "rubrica_juiz": juiz.rubrica()["versao"] if not a.sem_juiz else None, "modelo_juiz": juiz.MODELO if not a.sem_juiz else None,
            "modelo": llm.identidade_modelo(), "parcial": bool(a.casos),
            "ambiente": {"TIMEOUT_EXECUCAO_S": config.TIMEOUT_EXECUCAO_S, "EMBED_MODELO": config.EMBED_MODELO,
                         "LLM_MODELO": config.LLM_MODELO, "python": sys.version.split()[0]}}
    resultados = []
    parcial = pasta / "casos.parcial.jsonl"   # escrito caso a caso: se a rodada cair, o que rodou fica
    with parcial.open("w", encoding="utf-8") as f:
        for caso in casos:
            r = rodar_caso(caso, rodada_id, pasta)
            resultados.append(r)
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            f.flush()
            falhas = [f"{x['nivel']}.{x['verificacao']}: {x['detalhe']}" for x in r["verificacoes"] if not x["passou"]]
            print(f"{r['id']:4s} {'PASSOU' if r['passou'] else 'FALHOU'}  {r['termino']}  {r['segundos']}s"
                  + "".join(f"\n       - {x}" for x in falhas), flush=True)

    # O juiz roda DEPOIS de todos os casos: os dois modelos não cabem juntos na GPU de 4 GB,
    # e intercalar faria o Ollama trocar de modelo a cada caso.
    meta["juiz_adotado"] = juiz.adotado()
    if not a.sem_juiz:
        por_id = {c["id"]: c for c in casos}
        for r in resultados:
            caso = por_id[r["id"]]
            if caso["esperado"].get("juiz") and r["saida"].get("receita"):
                pedido = next(p["texto"] for p in reversed(caso["passos"]) if "texto" in p)
                r["juiz"] = juiz.julgar_saida(pedido, r["saida"])
                print(f"{r['id']:4s} juiz: {'adequada' if r['juiz']['adequada'] else 'NÃO adequada'} — {r['juiz']['motivo']}", flush=True)
                if meta["juiz_adotado"] and not r["juiz"]["adequada"]:
                    r["passou"] = False   # só um juiz validado acima do limiar decide se o caso passa
                    r["verificacoes"].append({"nivel": "juiz", "verificacao": "adequacao_receita", "passou": False,
                                              "detalhe": r["juiz"]["motivo"]})
    with (pasta / "casos.jsonl").open("w", encoding="utf-8") as f:
        for r in resultados:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    parcial.unlink()
    meta["fim"] = datetime.now().isoformat(timespec="seconds")
    meta["placar"] = placar(resultados)
    (pasta / "rodada.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta["placar"], ensure_ascii=False, indent=1))
    print(f"rodada: {pasta.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
