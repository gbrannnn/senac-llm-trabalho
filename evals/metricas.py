"""As métricas do §4.3 e o SLO do §4.4, calculadas SÓ a partir dos traces, por versão.

    python -m evals.metricas evals/resultados/<rodada-A> evals/resultados/<rodada-B> [mais pastas]

Lê todo `traces/*.jsonl` das pastas dadas (uma pasta de rodada, ou logs/traces) e agrupa
pela versão carimbada na raiz (`nutri.versao_sistema`): um número que mistura versões soma
sistemas diferentes. Uma EXECUÇÃO é uma raiz `invoke_agent` (um passo da CLI).

Custo. O modelo roda local: não há fatura por token. O custo por execução é dado em três
unidades: tokens (entrada + saída, somados dos spans `chat`), segundos de modelo, e uma
ESTIMATIVA em reais da energia da máquina, com as premissas declaradas em CUSTO abaixo.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.traces import duracao

# Premissas da estimativa de energia (declaradas em docs/observabilidade.md §5):
CUSTO = {"potencia_w": 90,        # notebook Ryzen 5 5600H + GTX 1650 sob carga (CPU+GPU), estimado, não medido
         "tarifa_brl_kwh": 0.85}  # tarifa residencial média com impostos, ordem de grandeza

# SLO de qualidade (docs/observabilidade.md §4): término por DECISÃO, e não por teto, laço ou erro.
TERMINO_RUIM = {"teto_passos", "teto_rodadas", "teto_tokens", "teto_tempo", "laco_detectado", "erro_fatal"}
SLO_OBJETIVO = 0.95
TETO_DECLARADO_S = 120   # o teto do sistema; as rodadas rodaram com 600 s nesta máquina (docs/evals.md §4)


def percentil(valores: list[float], p: float) -> float:
    """Percentil por interpolação linear (o mesmo do numpy 'linear')."""
    v = sorted(valores)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p
    i, f = int(k), k - int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * f


def carregar(pastas: list[str]) -> dict[str, list[list[dict]]]:
    """{versão: [spans de uma execução, ...]}"""
    por_versao: dict[str, list[list[dict]]] = defaultdict(list)
    vistos = set()
    for pasta in pastas:
        p = Path(pasta)
        arquivos = sorted(p.glob("traces/*.jsonl")) or sorted(p.glob("*.jsonl"))
        for arq in arquivos:
            if arq.name in vistos:
                continue
            vistos.add(arq.name)
            spans = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
            raiz = next((s for s in spans if s["parent_id"] is None), None)
            if raiz:
                por_versao[raiz["attributes"].get("nutri.versao_sistema", "?")].append(spans)
    return por_versao


def resumo(execucoes: list[list[dict]]) -> dict:
    raizes = [next(s for s in e if s["parent_id"] is None) for e in execucoes]
    lat = [duracao(r) for r in raizes]
    chats = [[s for s in e if s["name"].startswith("chat ")] for e in execucoes]
    tokens = [sum(s["attributes"].get("gen_ai.usage.input_tokens", 0) + s["attributes"].get("gen_ai.usage.output_tokens", 0)
                  for s in c) for c in chats]
    seg_modelo = [sum(duracao(s) for s in c) for c in chats]
    reais = [d * CUSTO["potencia_w"] / 1000 / 3600 * CUSTO["tarifa_brl_kwh"] for d in lat]
    terminos = Counter(r["attributes"].get("nutri.termino") for r in raizes)
    ferramentas: dict[str, list[bool]] = defaultdict(list)
    for e in execucoes:
        for s in e:
            if s["name"].startswith("execute_tool "):
                ferramentas[s["attributes"]["gen_ai.tool.name"]].append(s["status"]["status_code"] == "ERROR")
    chamadas_modelo = [s for c in chats for s in c]
    erro_modelo = sum(s["status"]["status_code"] == "ERROR" for s in chamadas_modelo)
    ruins = sum(terminos[t] for t in TERMINO_RUIM)
    n = len(raizes)
    sli = (n - ruins) / n if n else float("nan")
    orcamento = 1 - SLO_OBJETIVO
    datas = sorted(r["start_time"] for r in raizes)
    return {
        "execucoes": n, "janela": f"{datas[0][:16]} a {datas[-1][:16]}" if datas else None,
        "latencia_s": {"p50": round(percentil(lat, .5), 1), "p95": round(percentil(lat, .95), 1),
                       "max": round(max(lat), 1) if lat else None,
                       f"acima_de_{TETO_DECLARADO_S}s": sum(x > TETO_DECLARADO_S for x in lat)},
        "custo_por_execucao": {"tokens_p50": round(percentil(tokens, .5)), "tokens_media": round(sum(tokens) / n) if n else 0,
                               "segundos_modelo_p50": round(percentil(seg_modelo, .5), 1),
                               "reais_energia_media": round(sum(reais) / n, 5) if n else 0,
                               "chamadas_modelo_media": round(len(chamadas_modelo) / n, 2) if n else 0},
        "terminos": dict(terminos.most_common()),
        "erro_por_ferramenta": {k: {"chamadas": len(v), "erros": sum(v), "taxa": round(sum(v) / len(v), 3)}
                                for k, v in sorted(ferramentas.items())},
        "erro_modelo": {"chamadas": len(chamadas_modelo), "erros": erro_modelo},
        "slo": {"sli": round(sli, 4), "objetivo": SLO_OBJETIVO, "bons": n - ruins, "validos": n,
                "ruins_por_motivo": {t: terminos[t] for t in TERMINO_RUIM if terminos[t]},
                "orcamento_erro_execucoes": round(orcamento * n, 1),
                "orcamento_consumido": round(ruins / (orcamento * n), 3) if n else None,
                "violado": sli < SLO_OBJETIVO},
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    por_versao = carregar(sys.argv[1:])
    saida = {v: resumo(e) for v, e in sorted(por_versao.items())}
    saida["_premissas"] = {"custo": CUSTO, "termino_ruim": sorted(TERMINO_RUIM), "slo_objetivo": SLO_OBJETIVO,
                           "gerado_em": datetime.now().isoformat(timespec="seconds"), "pastas": sys.argv[1:]}
    print(json.dumps(saida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
