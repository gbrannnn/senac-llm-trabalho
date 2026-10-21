"""Log de execução em JSONL: um arquivo por turno, em logs/.

Primeira linha: o cabeçalho com a combinação que rodou (commit, modelo e digest,
versão e hash de cada prompt, versão dos índices, parâmetros e tetos).
Depois: uma linha por atualização de nó, na ordem em que o grafo executou.
Última linha: a saída validada.
"""
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import config, llm, prompts, rag


def commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.RAIZ, capture_output=True,
                             text=True, check=True).stdout.strip()
        sujo = subprocess.run(["git", "status", "--porcelain", "--", "src", "dados/catalogo_ingredientes.json"],
                              cwd=config.RAIZ, capture_output=True, text=True).stdout.strip()
        return sha + ("+alteracoes" if sujo else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "desconhecido"


class Registro:
    def __init__(self, nome: str, thread_id: str, usuario_id: str, entrada: str | dict):
        config.LOGS.mkdir(exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.caminho: Path = config.LOGS / f"{carimbo}_{nome}.jsonl"
        self.inicio = time.perf_counter()
        self._escrever({"tipo": "cabecalho", "data": datetime.now().isoformat(timespec="seconds"), "commit": commit(),
                        "thread_id": thread_id, "usuario_id": usuario_id, "entrada": entrada,
                        "modelo": llm.identidade_modelo(), "parametros": {"temperature": config.TEMPERATURA, "top_p": config.TOP_P},
                        "prompts": prompts.versoes(), "indices": rag.versoes_indice(),
                        "tetos": {"passos_agente": config.MAX_PASSOS_AGENTE, "rodadas": config.MAX_RODADAS_AVALIACAO,
                                  "tokens_execucao": config.MAX_TOKENS_EXECUCAO, "tokens_janela": config.MAX_TOKENS_JANELA,
                                  "tempo_s": config.TIMEOUT_EXECUCAO_S, "recursion_limit": config.RECURSION_LIMIT}})

    def _escrever(self, obj: dict) -> None:
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")

    def evento(self, no: str, atualizacao) -> None:
        self._escrever({"tipo": "no", "no": no, "t": round(time.perf_counter() - self.inicio, 2), "atualizacao": atualizacao})

    def saida(self, saida: dict) -> None:
        self._escrever({"tipo": "saida", "t": round(time.perf_counter() - self.inicio, 2), "saida": saida})

    def nota(self, texto: str, **extra) -> None:
        self._escrever({"tipo": "nota", "texto": texto, **extra})
