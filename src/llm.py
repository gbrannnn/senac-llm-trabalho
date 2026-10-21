"""Cliente do modelo: biblioteca `openai` apontada para o Ollama local.

Duas formas de chamada:
- `estruturada`: a saída é validada contra um modelo Pydantic (schema enviado
  como `response_format`, e validado de novo aqui — o schema garante o formato,
  não a correção);
- `com_ferramentas`: o modelo pode pedir chamadas de ferramenta.

Erros de rede ou de servidor são **fatais** (não há o que o modelo contorne);
JSON inválido é **recuperável** uma vez.
"""
import json
import time
from functools import cache

import requests
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

from . import config


class ErroFatal(Exception):
    """O sistema não consegue continuar: modelo fora do ar, resposta inválida repetida."""


@cache
def cliente() -> OpenAI:
    return OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=90)


@cache
def identidade_modelo() -> dict:
    """Modelo pedido + digest servido pelo Ollama (a 'versão datada' de um modelo local)."""
    base = config.LLM_BASE_URL.removesuffix("/v1")
    try:
        tags = requests.get(f"{base}/api/tags", timeout=5).json()["models"]
        por_nome = {m["name"]: m for m in tags}
        m = por_nome.get(config.LLM_MODELO) or por_nome.get(config.LLM_MODELO + ":latest", {})
        e = por_nome.get(config.EMBED_MODELO) or por_nome.get(config.EMBED_MODELO + ":latest", {})
        return {"modelo": config.LLM_MODELO, "digest": m.get("digest", "?")[:12],
                "embedding": config.EMBED_MODELO, "digest_embedding": e.get("digest", "?")[:12]}
    except requests.RequestException as erro:
        raise ErroFatal(f"Ollama indisponível em {base}: {erro}") from erro


def _criar(**kwargs):
    try:
        return cliente().chat.completions.create(
            model=config.LLM_MODELO, temperature=config.TEMPERATURA, top_p=config.TOP_P, **kwargs)
    except (APIConnectionError, APIStatusError) as erro:
        raise ErroFatal(f"falha ao chamar o modelo: {erro}") from erro


def estruturada(sistema: str, usuario: str, esquema: type[BaseModel]) -> tuple[BaseModel, dict]:
    mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    formato = {"type": "json_schema",
               "json_schema": {"name": esquema.__name__, "schema": esquema.model_json_schema()}}
    uso = {"tokens": 0, "chamadas": 0, "segundos": 0.0}
    for tentativa in range(2):
        inicio = time.perf_counter()
        resposta = _criar(messages=mensagens, response_format=formato)
        uso["segundos"] += round(time.perf_counter() - inicio, 2)
        uso["chamadas"] += 1
        uso["tokens"] += resposta.usage.total_tokens if resposta.usage else 0
        uso["maior_janela"] = max(uso.get("maior_janela", 0), resposta.usage.prompt_tokens if resposta.usage else 0)
        uso["modelo_servido"] = resposta.model
        conteudo = resposta.choices[0].message.content or ""
        try:
            return esquema.model_validate_json(conteudo), uso
        except ValidationError as erro:
            if tentativa == 1:
                raise ErroFatal(f"{esquema.__name__}: saída inválida duas vezes: {erro}") from erro
            mensagens += [{"role": "assistant", "content": conteudo},
                          {"role": "user", "content": f"Saída inválida: {erro}. Responda só o JSON válido."}]
    raise AssertionError("inalcançável")


def com_ferramentas(mensagens: list[dict], ferramentas: list[dict]) -> tuple[dict, dict]:
    inicio = time.perf_counter()
    resposta = _criar(messages=mensagens, tools=ferramentas)
    msg = resposta.choices[0].message
    uso = {"tokens": resposta.usage.total_tokens if resposta.usage else 0, "chamadas": 1,
           "maior_janela": resposta.usage.prompt_tokens if resposta.usage else 0,
           "segundos": round(time.perf_counter() - inicio, 2), "modelo_servido": resposta.model}
    saida = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        saida["tool_calls"] = [
            {"id": t.id, "type": "function",
             "function": {"name": t.function.name, "arguments": t.function.arguments}}
            for t in msg.tool_calls]
    return saida, uso


def argumentos(chamada: dict) -> dict:
    try:
        return json.loads(chamada["function"]["arguments"] or "{}")
    except json.JSONDecodeError:
        return {}
