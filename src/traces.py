"""Lê os traces de logs/traces/ e desenha a árvore de spans de uma execução.

    python -m src.traces                 # a execução mais recente
    python -m src.traces 3f2a9c1e        # pelo começo do trace_id (o que a CLI imprime)
    python -m src.traces caso1           # por parte do nome do arquivo
    python -m src.traces caso1 --raiz    # e todos os atributos da raiz (o registro da decisão)
    python -m src.traces --lista         # as últimas 20 execuções, uma por linha
    python -m src.traces --expurgar      # apaga traces e logs de execução com mais de RETENCAO_DIAS (90)

Cada arquivo é um JSONL com um span por linha, no formato do SDK do OpenTelemetry
(`ReadableSpan.to_json`). Não há serviço a subir: o destino é o arquivo.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config

TRACES = config.LOGS / "traces"
# os atributos que a árvore mostra ao lado de cada span; o resto fica em --raiz
MOSTRAR = ("nutri.etapa", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "nutri.chamada.pediu_ferramentas",
           "gen_ai.tool.call.arguments", "nutri.tool.origem", "error.type")


def ler(arquivo: Path) -> list[dict]:
    return [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def duracao(span: dict) -> float:
    return (_ts(span["end_time"]) - _ts(span["start_time"])).total_seconds()


def raiz(spans: list[dict]) -> dict | None:
    return next((s for s in spans if s["parent_id"] is None), None)


def achar(chave: str | None) -> Path:
    arquivos = sorted(TRACES.glob("*.jsonl"))
    if not arquivos:
        sys.exit(f"nenhum trace em {TRACES}")
    if chave is None:
        return arquivos[-1]
    por_nome = [a for a in arquivos if chave in a.name]
    if por_nome:
        return por_nome[-1]
    for a in reversed(arquivos):
        r = raiz(ler(a))
        if r and r["context"]["trace_id"].removeprefix("0x").startswith(chave.removeprefix("0x")):
            return a
    sys.exit(f"nenhum trace com '{chave}'")


def desenhar(spans: list[dict], com_raiz: bool = False) -> str:
    filhos: dict[str | None, list[dict]] = {}
    for s in spans:
        filhos.setdefault(s["parent_id"], []).append(s)
    for lista in filhos.values():
        lista.sort(key=lambda s: s["start_time"])
    r = raiz(spans)
    if r is None:
        return "(trace sem raiz: a execução não terminou?)"
    a = r["attributes"]
    linhas = [f"trace {r['context']['trace_id']}  ·  {r['start_time'][:19]}  ·  versão {a.get('nutri.versao_sistema')}"
              f"  ·  commit {a.get('nutri.commit')}",
              f"{r['name']}  {duracao(r):.1f}s  termino={a.get('nutri.termino')}  rota={a.get('nutri.rota')}  "
              f"status={r['status']['status_code']}"]
    pilha = [(f, 1) for f in reversed(filhos.get(r["context"]["span_id"], []))]
    while pilha:
        s, nivel = pilha.pop()
        extras = "  ".join(f"{k.split('.')[-1]}={s['attributes'][k]}" for k in MOSTRAR if k in s["attributes"])
        erro = "  ERRO" if s["status"]["status_code"] == "ERROR" else ""
        linhas.append(f"{'  ' * nivel}├─ {s['name']}  {duracao(s):.2f}s  {extras}{erro}"[:240])
        pilha += [(f, nivel + 1) for f in reversed(filhos.get(s["context"]["span_id"], []))]
    if com_raiz:
        linhas.append("\natributos da raiz (o registro da decisão):")
        linhas += [f"  {k} = {v}" for k, v in sorted(a.items())]
    return "\n".join(linhas)


RETENCAO_DIAS = 90   # docs/model-card.md §11: o trace herda a classificação do dado pessoal que carrega


def expurgar(dias: int = RETENCAO_DIAS, hoje: datetime | None = None) -> list[Path]:
    """Apaga trace e log de execução mais velhos que `dias`, pela data no nome (AAAAMMDD-HHMMSS_...).

    Apaga da pasta de trabalho. As execuções citadas como evidência na entrega continuam no
    histórico do git (só usuários fictícios), e isso está declarado no model card §11."""
    limite = (hoje or datetime.now()).timestamp() - dias * 86400
    apagados = []
    for arq in sorted(TRACES.glob("*.jsonl")) + sorted(config.LOGS.glob("2*.jsonl")):
        try:
            quando = datetime.strptime(arq.name[:15], "%Y%m%d-%H%M%S").timestamp()
        except ValueError:
            continue
        if quando < limite:
            arq.unlink()
            apagados.append(arq)
    return apagados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--expurgar" in sys.argv:
        apagados = expurgar()
        print(f"{len(apagados)} arquivo(s) com mais de {RETENCAO_DIAS} dias apagado(s)")
        return
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if "--lista" in sys.argv:
        for arq in sorted(TRACES.glob("*.jsonl"))[-20:]:
            r = raiz(ler(arq)) or {"attributes": {}, "context": {"trace_id": "?"}}
            print(f"{r['context']['trace_id'][2:10]}  {arq.name:60s} {r['attributes'].get('nutri.termino')}")
        return
    arquivo = achar(args[0] if args else None)
    print(f"arquivo: {arquivo}")
    print(desenhar(ler(arquivo), "--raiz" in sys.argv))


if __name__ == "__main__":
    main()
