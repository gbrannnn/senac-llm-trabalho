"""Compara duas rodadas da suíte, classe a classe.

    python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>

Imprime o placar por classe (fração de casos que passaram em TODAS as verificações), a
média por classe, e os casos que mudaram de lado, com a verificação que mudou.
Só compara rodadas do mesmo dataset: com casos diferentes, o delta não significa nada.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from . import juiz
from .rodar import carregar_dataset


def ler(pasta: str) -> tuple[dict, dict[str, dict]]:
    p = Path(pasta)
    meta = json.loads((p / "rodada.json").read_text(encoding="utf-8"))
    casos = {c["id"]: c for c in (json.loads(l) for l in (p / "casos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    return meta, casos


def _pct(x: float | None) -> str:
    return "  -  " if x is None else f"{x * 100:5.0f}%"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    (meta_a, a), (meta_b, b) = ler(sys.argv[1]), ler(sys.argv[2])
    if meta_a["dataset"] != meta_b["dataset"] or set(a) != set(b):
        sys.exit(f"rodadas de datasets diferentes ({meta_a['dataset']} x {meta_b['dataset']}): o delta não significa nada")
    dataset = carregar_dataset()
    origens = Counter(c["origem"] for c in dataset["casos"] if c["id"] in a)
    validacao = json.loads(juiz.VALIDACAO.read_text(encoding="utf-8")) if juiz.VALIDACAO.exists() else None
    print(f"DATASET v{meta_a['dataset']}   {len(a)} casos   (producao {origens['producao']} · "
          f"desenvolvimento {origens['desenvolvimento']} · sintetico {origens['sintetico']})")
    if validacao:
        print(f"JUIZ rubrica v{validacao['rubrica']}   concordância {validacao['concordancia'] * 100:.0f}%   "
              f"limiar {validacao['limiar']['concordancia'] * 100:.0f}%   "
              f"({'adotado' if validacao['adotado'] else 'NÃO adotado: fora do placar'})")
    else:
        print(f"JUIZ rubrica v{juiz.rubrica()['versao']}   concordância não medida   limiar {juiz.LIMIAR_CONCORDANCIA * 100:.0f}%   "
              "(não adotado: fora do placar)")
    print(f"\nA = v{meta_a['versao_sistema']} ({meta_a['commit']}, {meta_a['inicio'][:16]})   "
          f"B = v{meta_b['versao_sistema']} ({meta_b['commit']}, {meta_b['inicio'][:16]})\n")

    classes = sorted({c["classe"] for c in a.values()})
    print(f"{'classe':16s}  {'versão A':>8s}  {'versão B':>8s}  {'delta':>6s}")
    taxas_a, taxas_b = [], []
    for classe in classes:
        ids = [i for i, c in a.items() if c["classe"] == classe]
        ta = sum(a[i]["passou"] for i in ids) / len(ids)
        tb = sum(b[i]["passou"] for i in ids) / len(ids)
        taxas_a.append(ta)
        taxas_b.append(tb)
        print(f"{classe:16s}  {_pct(ta):>8s}  {_pct(tb):>8s}  {(tb - ta) * 100:+6.0f}   ({len(ids)} casos)")
    ma, mb = sum(taxas_a) / len(taxas_a), sum(taxas_b) / len(taxas_b)
    print(f"{'MÉDIA':16s}  {_pct(ma):>8s}  {_pct(mb):>8s}  {(mb - ma) * 100:+6.0f}")

    juiz_a = [c["juiz"]["adequada"] for c in a.values() if c.get("juiz")]
    juiz_b = [c["juiz"]["adequada"] for c in b.values() if c.get("juiz")]
    if juiz_a or juiz_b:
        print(f"\njuiz (adequação da receita): A {sum(juiz_a)}/{len(juiz_a)}   B {sum(juiz_b)}/{len(juiz_b)}")

    mudaram = [i for i in sorted(a) if a[i]["passou"] != b[i]["passou"]]
    print(f"\ncasos que mudaram de lado ({len(mudaram)}):")
    for i in mudaram:
        falhas = lambda c: {f"{v['nivel']}.{v['verificacao']}" for v in c["verificacoes"] if not v["passou"]}
        sentido = "passou a PASSAR" if b[i]["passou"] else "passou a FALHAR"
        diff = falhas(a[i]) ^ falhas(b[i])
        print(f"  {i:4s} {sentido:16s} {a[i]['termino']} -> {b[i]['termino']}   ({', '.join(sorted(diff)) or 'mesmas verificações'})")
    print("\ntérminos:  A " + ", ".join(f"{k}={v}" for k, v in Counter(c["termino"] for c in a.values()).most_common())
          + "\n           B " + ", ".join(f"{k}={v}" for k, v in Counter(c["termino"] for c in b.values()).most_common()))


if __name__ == "__main__":
    main()
