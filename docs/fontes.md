# Fontes consultadas

Acessadas em 20/10/2026, salvo indicação.

## Dados do sistema

| Fonte | Link | Uso | Licença |
|---|---|---|---|
| Food Ingredients and Recipe Dataset with Images (Epicurious, via Kaggle), espelho no Hugging Face | https://huggingface.co/datasets/Hieu-Pham/kaggle_food_recipes | recorte de 300 receitas (`dados/corpus/receitas.jsonl`) | CC BY-SA 3.0. O recorte, como obra derivada, segue a mesma licença |
| Eight Portions — Recipe Box (fonte prevista na v1) | https://github.com/rtlee9/recipe-box · arquivo `https://storage.googleapis.com/recipe-box/recipes_raw.zip` | **não usado**: o arquivo responde HTTP 404 | — |
| TBCA — Tabela Brasileira de Composição de Alimentos (USP/FoRC) | https://www.tbca.net.br/base-dados/composicao_alimentos.php | composição de 62 alimentos, baixada por código (`dados/tbca.json`, fora do git) | "não é permitida a reprodução total ou parcial"; uso com citação da fonte |
| WHO — Healthy diet (fact sheet, 26/01/2026) | https://www.who.int/news-room/fact-sheets/detail/healthy-diet | corpus da OMS | © OMS; uso não comercial com atribuição. A licença CC BY-NC-SA 3.0 IGO vale para as publicações da OMS; não conferimos se cobre as fichas do site |
| WHO — Sodium reduction (fact sheet, 11/05/2026) | https://www.who.int/news-room/fact-sheets/detail/sodium-reduction | corpus da OMS | © OMS; uso não comercial com atribuição. A licença CC BY-NC-SA 3.0 IGO vale para as publicações da OMS; não conferimos se cobre as fichas do site |
| WHO — Salt reduction (versão de 2018, **revogada**) | http://web.archive.org/web/20180430180905/http://www.who.int:80/news-room/fact-sheets/detail/salt-reduction | documento revogado de propósito ([rag.md §4.2](rag.md#o-documento-revogado)) | © OMS; uso não comercial com atribuição. A licença CC BY-NC-SA 3.0 IGO vale para as publicações da OMS; não conferimos se cobre as fichas do site |
| Anvisa — RDC nº 26, de 2 de julho de 2015 (rotulagem de alimentos alergênicos) | sem link: os endereços do DOU e da BVS não responderam ou deram 404 na conferência | lista brasileira de alérgenos do catálogo | norma pública |

## Modelos e software

| Item | Link | Versão |
|---|---|---|
| Ollama | https://ollama.com | 0.40.6 |
| qwen2.5:7b-instruct | https://ollama.com/library/qwen2.5 | digest `845dbda0ea48` |
| llama3.1:8b (comparação) | https://ollama.com/library/llama3.1 | digest `46e0c10c039e` |
| bge-m3 | https://ollama.com/library/bge-m3 | digest `790764642607` |
| LangGraph | https://github.com/langchain-ai/langgraph | 1.2.16 (padrão de `recursion_limit` em `langgraph/_internal/_config.py`) |
| openai (Python) | https://github.com/openai/openai-python | 3.35.1 |
| Pydantic | https://docs.pydantic.dev | 2.14.1 |
| SQLite — WAL e `wal_checkpoint` | https://www.sqlite.org/wal.html | (achado da remoção, [memoria.md §5.4](memoria.md#a-cobertura-da-remoção)) |

## Disciplina

| Documento | Link |
|---|---|
| Parte 2 — enunciado | https://github.com/celsocrivelaro/senac-agentes-llm/blob/main/trabalho/02-segunda-entrega.md |
| Visão geral e Parte 1 | https://github.com/celsocrivelaro/senac-agentes-llm/tree/main/trabalho |
| Aula 12 — governança (model card) | https://github.com/celsocrivelaro/senac-agentes-llm/tree/main/aula-12-governanca |

## Legislação citada nos documentos

- LGPD, Lei nº 13.709/2018: art. 5º, II (dado sensível), art. 11 (base legal para dado de saúde), art. 18, VI (eliminação). Texto oficial no portal do Planalto; o endereço não respondeu na conferência.
