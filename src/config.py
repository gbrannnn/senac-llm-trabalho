"""Configuração: caminhos, variáveis de ambiente e os tetos do orçamento.

Os tetos vêm de docs/arquitetura.md §2 (orçamento) e são declarados aqui, e não
deixados no padrão do framework, pela razão de docs/grafo.md §6.6.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DADOS = RAIZ / "dados"
LOGS = RAIZ / "logs"
PROMPTS = Path(__file__).resolve().parent / "prompts"

DB_DOMINIO = DADOS / "nutri.sqlite"          # perfil, estoque, histórico, escritas
DB_CHECKPOINTS = DADOS / "checkpoints.sqlite"  # checkpointer do LangGraph
INDICE = DADOS / "indice"                     # vetores de receitas e OMS
CATALOGO = DADOS / "catalogo_ingredientes.json"
TBCA = DADOS / "tbca.json"
RECEITAS = DADOS / "corpus" / "receitas.jsonl"
CORPUS_OMS = DADOS / "corpus" / "oms"

LLM_BASE_URL = os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1"
LLM_API_KEY = os.getenv("LLM_API_KEY") or "ollama"
LLM_MODELO = os.getenv("LLM_MODELO") or "nutri-qwen"
EMBED_MODELO = os.getenv("EMBED_MODELO") or "bge-m3"
TEMPERATURA = 0.0
TOP_P = 1.0

# Orçamento (docs/arquitetura.md, "O orçamento")
MAX_PASSOS_AGENTE = 5          # chamadas do modelo por rodada do agente (chef ou consultor)
MAX_RODADAS_AVALIACAO = 3      # vezes que uma proposta pode ser reprovada
# A v1 dizia "6000 tokens por pedido" sem dizer se era janela ou execução. Agora são dois:
MAX_TOKENS_JANELA = 6000       # prompt de UMA chamada (num_ctx=8192 no Modelfile deixa folga)
MAX_TOKENS_EXECUCAO = 40000    # soma de todas as chamadas do turno
TIMEOUT_EXECUCAO_S = 120       # parede: modelo local é mais lento que o declarado na v1
RECURSION_LIMIT = 40           # declarado: o padrão do LangGraph 1.2.16 é 10007 (era 25 nas 0.x) e muda por env var — docs/grafo.md §6.6
K_RECEITAS = 5
K_OMS = 3
JANELA_CONVERSA_TURNOS = 6     # turnos (usuário+sistema) mantidos no estado da conversa
DECAIMENTO_DIAS = 90           # histórico mais velho que isso é rebaixado, não apagado
PESO_DECAIDO = 0.5
PRAZO_APROVACAO_S = int(os.getenv("PRAZO_APROVACAO_S") or 24 * 3600)
# Desempate de versões da OMS por data_publicacao (docs/rag.md). Desligar só para a demonstração do revogado.
DESEMPATE_OMS = (os.getenv("DESEMPATE_OMS") or "1") != "0"
