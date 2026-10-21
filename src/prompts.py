"""Carrega os prompts de src/prompts/*.md em tempo de execução.

Cada arquivo começa com um cabeçalho `---` com `id` e `versao`. O carregador
devolve o texto sem o cabeçalho, a versão declarada e o hash do conteúdo, para
que o log de cada execução registre exatamente que combinação rodou.
"""
import hashlib
from dataclasses import dataclass
from functools import cache

from . import config


@dataclass(frozen=True)
class Prompt:
    id: str
    versao: str
    texto: str
    sha: str

    def formatar(self, **campos) -> str:
        texto = self.texto
        for chave, valor in campos.items():
            texto = texto.replace("{{" + chave + "}}", str(valor))
        return texto


@cache
def carregar(nome: str) -> Prompt:
    # CRLF -> LF: com autocrlf no Windows o mesmo prompt teria outro hash num clone novo
    bruto = (config.PROMPTS / f"{nome}.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, texto = {}, bruto
    if bruto.startswith("---"):
        _, cabecalho, texto = bruto.split("---", 2)
        for linha in cabecalho.strip().splitlines():
            chave, _, valor = linha.partition(":")
            meta[chave.strip()] = valor.strip()
    texto = texto.strip()
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:10]
    return Prompt(meta.get("id", nome), meta.get("versao", "0"), texto, sha)


def versoes() -> dict[str, str]:
    """`{id: "versao@sha"}` de todos os prompts — vai no cabeçalho do log."""
    return {
        p.stem: f"{carregar(p.stem).versao}@{carregar(p.stem).sha}"
        for p in sorted(config.PROMPTS.glob("*.md"))
    }
