"""Traces OpenTelemetry nas convenções semânticas GenAI (docs/observabilidade.md §2).

Uma execução = um trace:

    invoke_agent agente-nutricionista          raiz, aberta por src.main.executar
    ├── chat nutri-qwen                        cada chamada ao modelo (src.llm)
    ├── embeddings bge-m3                      cada chamada de embedding (src.rag)
    └── execute_tool <ferramenta>              cada ferramenta: as que o modelo pede
                                               (origem=modelo) e as escritas que o
                                               código faz (origem=codigo)

O trace é também o REGISTRO DA DECISÃO (docs/model-card.md §11): a raiz guarda a
entrada, as versões, o contexto recuperado, a saída, o motivo de término e a
aprovação humana.

Destino: um arquivo JSONL por execução em logs/traces/, um span por linha, no
formato `ReadableSpan.to_json()` do SDK. `python -m src.traces` lê e desenha a árvore.

Por que os filhos são presos à raiz explicitamente (e não pelo contexto implícito):
o LangGraph roda os três `carregar_*` em paralelo, em outras threads, e o contexto
do OpenTelemetry é por thread. A CLI roda uma execução por processo, então a raiz
vigente fica num atributo do módulo.
"""
import contextvars
import json
from contextlib import contextmanager
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, Status, StatusCode

from . import config

AGENTE = "agente-nutricionista"
TRACES = config.LOGS / "traces"


class ExportadorArquivo(SpanExporter):
    """Escreve cada span terminado como uma linha JSON no arquivo da execução vigente."""

    def __init__(self) -> None:
        self.caminho: Path | None = None

    def export(self, spans) -> SpanExportResult:
        if self.caminho is not None:
            with self.caminho.open("a", encoding="utf-8") as f:
                for s in spans:
                    f.write(s.to_json(indent=None) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.caminho = None


_exportador = ExportadorArquivo()
_provedor = TracerProvider(resource=Resource.create({
    "service.name": AGENTE, "service.version": config.VERSAO_SISTEMA}))
_provedor.add_span_processor(SimpleSpanProcessor(_exportador))
_tracer = _provedor.get_tracer("src.telemetria", config.VERSAO_SISTEMA)

_raiz: trace.Span | None = None
# a etapa do grafo que está rodando (posta pelo decorador `no` de src.grafo); vai em cada span filho
etapa_atual: contextvars.ContextVar[str | None] = contextvars.ContextVar("etapa_atual", default=None)


def _contexto():
    return trace.set_span_in_context(_raiz) if _raiz is not None else None


def _atributo(valor):
    """O OpenTelemetry só aceita primitivos e listas de primitivos: o resto vira JSON."""
    if valor is None:
        return None
    if isinstance(valor, (str, bool, int, float)):
        return valor
    if isinstance(valor, (list, tuple)) and all(isinstance(v, str) for v in valor):
        return list(valor)
    return json.dumps(valor, ensure_ascii=False, default=str)


def definir(span: trace.Span, atributos: dict) -> None:
    for chave, valor in atributos.items():
        if (v := _atributo(valor)) is not None:
            span.set_attribute(chave, v)


def _com_etapa(atributos: dict) -> dict:
    return {**atributos, "nutri.etapa": etapa_atual.get()}


@contextmanager
def execucao(nome_arquivo: str, atributos: dict):
    """Abre a raiz `invoke_agent`. Tudo que for aberto até o fim do bloco é filho dela."""
    global _raiz
    TRACES.mkdir(parents=True, exist_ok=True)
    _exportador.caminho = TRACES / f"{nome_arquivo}.jsonl"
    span = _tracer.start_span(f"invoke_agent {AGENTE}", kind=SpanKind.INTERNAL)
    definir(span, {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": AGENTE,
                   "gen_ai.provider.name": "ollama", "nutri.versao_sistema": config.VERSAO_SISTEMA, **atributos})
    _raiz = span
    try:
        yield span
    except BaseException as erro:
        span.record_exception(erro)
        span.set_status(Status(StatusCode.ERROR, str(erro)[:200]))
        span.set_attribute("error.type", type(erro).__name__)
        raise
    finally:
        span.end()
        _raiz = None


def caminho_trace() -> str | None:
    return str(_exportador.caminho) if _exportador.caminho else None


def id_do_trace(span: trace.Span) -> str:
    return format(span.get_span_context().trace_id, "032x")


@contextmanager
def chat(modelo: str, atributos: dict):
    span = _tracer.start_span(f"chat {modelo}", context=_contexto(), kind=SpanKind.CLIENT)
    definir(span, _com_etapa({"gen_ai.operation.name": "chat", "gen_ai.provider.name": "ollama",
                              "gen_ai.request.model": modelo, **atributos}))
    try:
        yield span
    except BaseException as erro:
        span.set_status(Status(StatusCode.ERROR, str(erro)[:200]))
        span.set_attribute("error.type", type(erro).__name__)
        raise
    finally:
        span.end()


@contextmanager
def embeddings(modelo: str, n_textos: int):
    span = _tracer.start_span(f"embeddings {modelo}", context=_contexto(), kind=SpanKind.CLIENT)
    definir(span, _com_etapa({"gen_ai.operation.name": "embeddings", "gen_ai.provider.name": "ollama",
                              "gen_ai.request.model": modelo, "nutri.embeddings.textos": n_textos}))
    try:
        yield span
    except BaseException as erro:
        span.set_status(Status(StatusCode.ERROR, str(erro)[:200]))
        span.set_attribute("error.type", type(erro).__name__)
        raise
    finally:
        span.end()


@contextmanager
def ferramenta(nome: str, argumentos: dict, chamada_id: str | None = None, origem: str = "modelo",
               tipo: str = "leitura"):
    """`execute_tool`. O resultado é posto por `resultado()`; erro de domínio marca o span como erro."""
    span = _tracer.start_span(f"execute_tool {nome}", context=_contexto(), kind=SpanKind.INTERNAL)
    definir(span, _com_etapa({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,
                              "gen_ai.tool.type": "function", "gen_ai.tool.call.id": chamada_id,
                              "gen_ai.tool.call.arguments": argumentos, "nutri.tool.origem": origem,
                              "nutri.tool.tipo": tipo}))
    try:
        yield span
    except BaseException as erro:
        span.set_status(Status(StatusCode.ERROR, str(erro)[:200]))
        span.set_attribute("error.type", type(erro).__name__)
        raise
    finally:
        span.end()


def resultado(span: trace.Span, valor) -> None:
    """Grava o resultado da ferramenta (até 2000 caracteres) e marca o erro de domínio.

    Erro de domínio (receita inexistente, alimento fora da TBCA) não derruba a execução:
    volta ao modelo como observação. Por isso só aparece na métrica se for contado aqui."""
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    span.set_attribute("gen_ai.tool.call.result", texto[:2000])
    try:
        dado = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return
    if isinstance(dado, dict) and dado.get("erro"):
        span.set_status(Status(StatusCode.ERROR, str(dado["erro"])[:200]))
        span.set_attribute("error.type", "erro_de_dominio")
