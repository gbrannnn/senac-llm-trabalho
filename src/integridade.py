"""Integridade do corpus e do índice (ASI04 e ASI06, docs/seguranca.md §3.2, controle C2).

O acervo de receitas veio de um espelho de terceiros no Hugging Face, a TBCA é baixada de novo
em cada máquina, e o índice vetorial é lido em TODO pedido de TODOS os usuários. Um arquivo
trocado ("almond butter" virando "butter") passaria a ser recomendado a quem é alérgico.

O controle: `dados/manifesto.json` (versionado) guarda o SHA-256 esperado de cada arquivo do
corpus, do catálogo e da TBCA, e a versão esperada de cada índice. O sistema confere tudo:
  - ao subir (src.grafo.obter_grafo): divergência = a execução NÃO roda (fail-closed),
    termina em `integridade_violada`;
  - no preparo (scripts.preparar), antes de indexar: um download diferente do esperado aborta.

Além do manifesto versionado, o preparo grava `dados/indice/manifesto_local.json` com o hash
dos vetores (.npz). Os vetores dependem da máquina que calculou o embedding, então não dá para
versioná-los; o arquivo local pega a troca do índice DEPOIS de indexado.

    python -m src.integridade             # confere e imprime o relatório
    python -m src.integridade --atualizar # reescreve o manifesto (mudança legítima do corpus: revisar o diff!)
"""
import hashlib
import json
import sys
from pathlib import Path

from . import config

MANIFESTO = config.DADOS / "manifesto.json"
MANIFESTO_LOCAL = config.INDICE / "manifesto_local.json"


class IntegridadeViolada(Exception):
    """Um arquivo do corpus, do catálogo, da TBCA ou do índice não é o esperado."""


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def arquivos_protegidos() -> list[Path]:
    return [config.RECEITAS, config.CATALOGO, config.TBCA, *sorted(config.CORPUS_OMS.glob("*.md"))]


def _rel(p: Path) -> str:
    return p.relative_to(config.RAIZ).as_posix()


def _versoes_calculadas() -> dict[str, str]:
    """A versão que o índice DEVERIA ter, recalculada a partir do corpus atual (o mesmo hash de rag.indexar)."""
    from . import rag
    textos = {"receitas": [rag._texto_receita(r) for r in rag.receitas()], "oms": [t["texto"] for t in rag.trechos_oms()]}
    return {n: f"idx-{n}-{rag._hash_corpus(t)}" for n, t in textos.items()}


def verificar(conferir_indice: bool = True) -> list[str]:
    """Lista de problemas; vazia = íntegro."""
    if not MANIFESTO.exists():
        return [f"manifesto ausente: {_rel(MANIFESTO)}"]
    esperado = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    problemas = []
    atuais = {_rel(p) for p in arquivos_protegidos()}
    for rel, sha in esperado["arquivos"].items():
        p = config.RAIZ / rel
        if not p.exists():
            problemas.append(f"{rel}: ausente")
        elif _sha(p) != sha:
            problemas.append(f"{rel}: conteúdo diferente do manifesto")
    problemas += [f"{rel}: arquivo novo, fora do manifesto" for rel in sorted(atuais - set(esperado["arquivos"]))]
    if not conferir_indice:
        return problemas
    from . import rag
    try:
        no_indice = rag.versoes_indice()
    except (OSError, KeyError, ValueError) as erro:
        return problemas + [f"índice ilegível: {erro}"]
    calculadas = _versoes_calculadas()
    for nome, versao in esperado["indices"].items():
        if no_indice.get(nome) != versao:
            problemas.append(f"índice {nome}: versão {no_indice.get(nome)} ≠ manifesto {versao}")
        if calculadas[nome] != versao:
            problemas.append(f"índice {nome}: o corpus atual daria {calculadas[nome]}, o manifesto diz {versao}")
    if not MANIFESTO_LOCAL.exists():
        problemas.append(f"{_rel(MANIFESTO_LOCAL)} ausente: rode python -m scripts.preparar")
    else:
        for nome, sha in json.loads(MANIFESTO_LOCAL.read_text(encoding="utf-8")).items():
            p = config.INDICE / nome
            if not p.exists() or _sha(p) != sha:
                problemas.append(f"índice {nome}: vetores alterados depois de indexados")
    return problemas


def exigir(conferir_indice: bool = True) -> None:
    if problemas := verificar(conferir_indice):
        raise IntegridadeViolada("; ".join(problemas))


def gravar_manifesto_local() -> None:
    """Chamado por scripts.preparar logo depois de indexar."""
    MANIFESTO_LOCAL.write_text(json.dumps({p.name: _sha(p) for p in sorted(config.INDICE.glob("*.npz"))}, indent=1),
                               encoding="utf-8")


def atualizar() -> dict:
    """Reescreve o manifesto com o estado atual. Mudança legítima do corpus passa por aqui, e o
    diff de dados/manifesto.json no commit é a revisão humana dessa mudança."""
    from . import rag
    manifesto = {"sobre": "SHA-256 esperado de cada arquivo do corpus e versão esperada de cada índice (src/integridade.py)",
                 "arquivos": {_rel(p): _sha(p) for p in arquivos_protegidos()},
                 "indices": rag.versoes_indice()}
    MANIFESTO.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifesto


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--atualizar" in sys.argv:
        print(json.dumps(atualizar(), ensure_ascii=False, indent=1))
    problemas = verificar()
    print("íntegro" if not problemas else "VIOLADO:\n  " + "\n  ".join(problemas))
    sys.exit(1 if problemas else 0)
