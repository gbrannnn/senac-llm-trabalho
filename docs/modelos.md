# Análise de modelos

**Data:** 20/10/2026 · **Decisão:** qwen2.5 7B instruct (Q4_K_M), **local**, via Ollama 0.40.6, com `num_ctx` 8192 (modelo `nutri-qwen`, [Modelfile](../Modelfile)) · embedding: bge-m3

> O `modelos.md` da Parte 1 se perdeu (ver [case.md](case.md)). Esta análise foi refeita, e com medição: os dois candidatos locais rodaram a mesma bateria.

## 3.1 Os candidatos

| Candidato | Por que entrou | Por que saiu ou ficou |
|---|---|---|
| **qwen2.5:7b-instruct** (Q4_K_M, 4,7 GB) | suporta saída estruturada e chamada de ferramenta no Ollama; bom em português; cabe nos 8 GB da GPU junto com o modelo de embedding | **escolhido** |
| **llama3.1:8b** (Q4_K_M, 4,9 GB) | mesma faixa de tamanho, chamada de ferramenta nativa | medido; perdeu no laço do consultor (abaixo) |
| Mistral via API (o dos laboratórios) | é o padrão da disciplina | **não usado, por decisão do grupo de rodar local.** Pesou também que o perfil tem dado de saúde (alergia): com modelo local, o dado não sai da máquina. Não medimos qualidade nem custo da API |
| qwen2.5:14b e maiores | mais capacidade | não cabem nos 8 GB de VRAM junto com o embedding; rodariam parcialmente na CPU, e o 7B já leva ~1 s por chamada |

**Embedding: bge-m3** (1,2 GB, 1024 dimensões, multilíngue). As perguntas chegam em português e o corpus está em inglês. Um modelo de embedding só de inglês erraria a ponte entre as línguas, e o bge-m3 já é fraco nisso ([rag.md §4.1](rag.md#a-escolha-com-justificativa)).

## 3.2 A conta

| | Modelo local (escolhido) |
|---|---|
| hardware | RTX 4060 Ti 8 GB, i5-12400F, 16 GB RAM |
| memória de GPU em uso | `nutri-qwen` 5,0 GB + `bge-m3` 0,7 GB, "100% GPU" (`ollama ps`) |
| custo marginal por execução | **R$ 0** de API; o custo é energia, **não medida** |
| tempo por recomendação | 4–7 s (medido, [E06](evidencias/E06-frase.txt)); a primeira chamada depois de trocar de modelo leva ~13 s (carga na GPU) |
| tokens por recomendação | ~4.600 (4 chamadas) |
| dado pessoal fora da máquina | **nenhum** |

**Um achado da conta:** o modelo de chat **não** estava usando a GPU na primeira execução (`size_vram: 0`, ~13 s por chamada curta). Um servidor `ollama serve` iniciado pelo terminal ocupou a porta sem acesso à GPU, e o servidor do aplicativo não conseguiu subir ("bind: Only one usage of each socket address"). Depois de encerrar o servidor do terminal, a chamada caiu para 0,1 s. Para quem for rodar: use o aplicativo do Ollama e confira `ollama ps`, coluna PROCESSOR.

## 3.3 A verificação mínima

A mesma bateria nos dois modelos, com os mesmos prompts e o mesmo código:

| Teste | qwen2.5 7B | llama3.1 8B | Evidência |
|---|---|---|---|
| triagem, 20 casos rotulados (critério ≥ 18) | **20/20** | 19/20 (errou "comprei uma air fryer" → estoque) | [E07](evidencias/E07-etapas.txt), [E09](evidencias/E09-modelos-llama3.1-8b.txt) |
| extração de itens, 6 casos (critério ≥ 5) | 5/6 | 5/6 (o mesmo erro) | idem |
| recomendação "o que eu faço pra jantar?" | concluída, 4 chamadas, 4.567 tokens | concluída, **6 chamadas, 7.754 tokens** | E09 |
| recomendação "tenho abobrinha…" | concluída, 4 chamadas | concluída, 4 chamadas | E09 |
| pergunta **respondível**: "limite de sódio para um adulto?" | **resposta correta** (< 2000 mg) | **recusou** (falso negativo) | E09 |
| pergunta fora do corpus (cafeína) | recusou | recusou | E09 |

Nos dois modelos, nenhuma execução terminou em `erro_fatal` (0 de 49 logs): a saída estruturada (`json_schema`) nunca falhou duas vezes seguidas. Não medimos quantas vezes ela falhou uma vez e deu certo na segunda tentativa. Os dois às vezes respondem em texto quando deveriam chamar a ferramenta final; o fechamento estruturado cobre os dois ([grafo.md §6.5](grafo.md#65-o-que-o-framework-não-deu)).

## 3.4 A decisão

**qwen2.5 7B**, pelos três números que separam os candidatos:
- triagem 20/20 contra 19/20;
- o laço do consultor respondeu a pergunta respondível, e o do llama recusou;
- ~40% menos tokens na recomendação em que os dois divergiram.

O empate na extração mostra que o erro restante ("um pacote" → quantidade nula) é do prompt, não do modelo.

**O que a decisão custa:**
- o 7B erra **interpretação**: leu "Ovo, galinha, branco" como clara e *teaspoons* como colheres de sopa. Promete benefício de saúde mesmo instruído a não fazer. Os portões em código existem por isso ([prompts.md](prompts.md#22-os-prompts-em-arquivo-e-o-histórico-das-versões));
- a janela padrão do Ollama trunca o início do prompt em silêncio. Por isso o Modelfile fixa `num_ctx` ([E02](evidencias/E02-janela.txt)).

**A amostra é pequena:** 4 pedidos de ponta a ponta por modelo, uma execução cada. A diferença no consultor é um caso. Para a Parte 3, repetir com os 20 casos da [aula-11-avaliacao.md](aula-11-avaliacao.md), 5 execuções cada.
