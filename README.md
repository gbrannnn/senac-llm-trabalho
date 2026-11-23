# Agente Nutricionista Pessoal

**O problema em uma frase:** decidir o que cozinhar hoje com o que já existe em casa, respeitando as alergias e o objetivo de quem vai comer, sem inventar número de nutrição.

## Integrantes
- Eduardo Dias Santos
- Daniel de Araujo Carvalho
- Gabriel Brandão Vehchani de Freitas
- Pedro Henrique Gomes

**Entrega atual:** Parte 3 — o sistema sob controle: [avaliação](docs/evals.md), [governança](docs/model-card.md), [segurança](docs/seguranca.md), [observabilidade](docs/observabilidade.md) e o [histórico de mudanças](docs/mudancas.md). Sistema na versão **1.1.0**. A documentação das Partes 1 e 2 continua em [docs/](docs/); comece por [docs/case.md](docs/case.md) e [docs/arquitetura.md](docs/arquitetura.md).

**Frentes opcionais da Parte 3 (§5): nenhuma.** O sistema não usa MCP, não lê nem produz mídia, e não é multiagente: os papéis do modelo (triagem, chef, avaliador, consultor, verificador) são etapas de um mesmo grafo, no mesmo processo, sem credencial própria ([docs/seguranca.md §1](docs/seguranca.md#1-os-canais-por-onde-entra-conteúdo-não-confiável)).

---

## Como rodar

Testado do zero, num clone novo, **duas vezes**. Na Parte 2 (GPU de 8 GB): **2 min 15 s** com os modelos já baixados (instalação 56 s, preparação 63 s, primeira pergunta 16 s). Na Parte 3, v1.1.0, em 23/11/2026 (GTX 1650 de 4 GB): instalação 21 s (com o cache do pip), preparação **247 s** (quase tudo é baixar de novo a TBCA, que **bateu com o manifesto** de integridade), 130 testes passando e a primeira pergunta respondida em 101 s, com o modelo frio. Baixar os modelos (~6 GB) leva mais, e depende da conexão.

**Requisitos:** Python 3.13, [Ollama](https://ollama.com) 0.40+ e GPU com 8 GB (roda na CPU, mas devagar).

```bash
# 1. Modelos (uma vez). Use o APLICATIVO do Ollama: um `ollama serve` aberto no terminal
#    pode ocupar a porta sem GPU (ver docs/modelos.md §3.2). Confira com `ollama ps`.
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
ollama create nutri-qwen -f Modelfile      # fixa num_ctx=8192 (docs/evidencias/E02)

# 2. Ambiente
python -m venv .venv
.venv\Scripts\activate                     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# opcional: copie .env.example para .env (sem .env, valem os padrões de src/config.py)

# 3. Dados, índice e banco com usuários fictícios (~1 min: baixa receitas, TBCA e OMS, confere
#    cada arquivo contra dados/manifesto.json, indexa, e emite um token para cada usuário)
python -m scripts.preparar

# 4. Usar: a CLI só executa com o token de quem está em --usuario (v1.1.0)
export NUTRI_TOKEN=$(python -m src.acesso token ana)      # Windows: set NUTRI_TOKEN=... (o valor impresso)
python -m src.main --usuario ana "o que eu faço pra jantar?"

# 5. Testes (130, sem modelo), entre eles os dos controles de segurança, e conferência do grafo
python -m pytest
python -m pytest tests/test_controles.py -v               # só os controles (docs/seguranca.md §3)
python conferir_grafo.py
```

A TBCA não permite reprodução, então `dados/tbca.json` não está no git: o `preparar` baixa o arquivo em cada máquina. Nenhuma chave de API é necessária, porque o modelo roda local.

**Os tokens.** O `preparar` grava um token por usuário fictício, e um do operador, em `dados/tokens_locais.json` (fora do git); o banco guarda só o hash. `python -m src.acesso token <usuario>` imprime o token local. Sem `NUTRI_TOKEN`, ou com o token de outra pessoa, a execução termina em `acesso_negado` e nada roda ([docs/seguranca.md §3, C1](docs/seguranca.md#c1--identidade-por-token-asi03)).

**GPU de 4 GB.** Numa GPU menor que 8 GB, o modelo de chat divide a GPU com a CPU, e o Ollama passa a descarregar o modelo a cada embedding. Prenda o embedding na CPU e dê mais tempo à execução (foi assim que a suíte rodou, [docs/mudancas.md](docs/mudancas.md)):

```bash
printf 'FROM bge-m3\nPARAMETER num_gpu 0\n' > /tmp/Modelfile.bge && ollama create bge-m3-cpu -f /tmp/Modelfile.bge
export EMBED_MODELO=bge-m3-cpu TIMEOUT_EXECUCAO_S=600
```

## Como usar

A pessoa **digita texto livre**. O sistema:
- recomenda uma refeição com o que está no estoque;
- registra compras (com a sua aprovação);
- atualiza o perfil (objetivo, alergias, restrições);
- responde dúvidas de nutrição com base na OMS e na TBCA.

Usuários fictícios já criados: **ana** (perfil completo, estoque com 18 itens), **bruno** (alergia a amendoim, e amendoim no estoque) e **carla** (usuária nova, sem perfil).

### O exemplo principal

Copiado do log [`logs/20261020-230141_caso1.jsonl`](logs/20261020-230141_caso1.jsonl) (commit `fffe38f`). A saída completa e outros exemplos estão em [docs/io.md](docs/io.md).

```text
$ python -m src.main --usuario ana --sessao caso1 "oi! o que eu posso fazer pra jantar hoje?"
Sugestão: Stir-Fried Black Rice with Fried Egg and Roasted Broccoli. Usa arroz, ovo, que estão no seu estoque. A receita inteira tem cerca de 1652 kcal e 35 g de proteína (TBCA).
```

```json
{
  "tipo": "recomendacao",
  "receita": {
    "id": "R03115",
    "nome": "Stir-Fried Black Rice with Fried Egg and Roasted Broccoli",
    "faltando_no_estoque": [],
    "nutricao": { "energia_kcal": 1651.5, "proteina_g": 35.1, "carboidrato_g": 295.4, "lipidio_g": 37.8,
                  "sodio_mg": 151.1, "completa": false, "fora_do_calculo": ["Kosher salt"],
                  "base": "receita inteira (o dataset não informa porções)" }
  },
  "fontes": [ {"tipo": "estoque", "id": "ana"}, {"tipo": "perfil", "id": "ana"},
              {"tipo": "oms", "id": "oms-alimentacao-saudavel-2026#01"},
              {"tipo": "receita", "id": "R03115"}, {"tipo": "tbca", "id": "BRC0001A,BRC0012J"} ],
  "suficiencia": "suficiente",
  "escolhas_declaradas": [
    "cálculo nutricional parcial: fora do cálculo Kosher salt",
    "justificativa do modelo substituída por texto em código: prometia benefício ('boa opção')"
  ],
  "termino": "concluido"
}
```
*(campos `ingredientes`, `detalhe` e `uso` omitidos aqui; estão completos em [docs/io.md](docs/io.md))*

> **Sobre os hashes nos logs:** os logs da Parte 2 em `logs/` e as evidências em `docs/evidencias/` registram o commit `d16e6b7`. Esse é o mesmo código do commit `fffe38f` (a árvore é idêntica): só a mensagem do commit foi reescrita antes do envio.

**A mesma pergunta na versão 1.1.0**, copiada da rodada B da suíte (caso R01, 23/11/2026; [o trace](logs/traces/20261123-152355_eval_20261123-1523_R01_1.jsonl), e a saída completa em [evals/resultados/v1.1.0_20261123-1523/casos.jsonl](evals/resultados/v1.1.0_20261123-1523/casos.jsonl)). Com o histórico vazio da rodada, o chef escolheu outra receita; e a justificativa do modelo prometia "manutenção do peso", então o código a trocou e declarou a troca:

```text
$ export NUTRI_TOKEN=$(python -m src.acesso token ana)
$ python -m src.main --usuario ana "oi! o que eu posso fazer pra jantar hoje?"
Sugestão: Frango milanesa com salada de rúcula com limão (Lemony Chicken Milanese with Arugula Salad). Usa ervas frescas,
folhas verdes, frango, limão, ovo, pão, que estão no seu estoque. A receita inteira tem cerca de 1609 kcal e 186 g de proteína (TBCA).
Ingredientes:
  - 4 peitos de frango sem pele e esqueleto
  - 2 ovos grandes
  - 1 1/4 cups panko (Japanese breadcrumbs)
  ...
```
```json
  "escolhas_declaradas": [
    "nome e ingredientes traduzidos pelo modelo; alérgeno e nutrição foram calculados sobre o original",
    "2 linha(s) de ingrediente mantida(s) em inglês: o ingrediente 'pão' não aparece na tradução; unidade diferente do original",
    "justificativa do modelo substituída por texto em código: prometia benefício ('manutenção do peso')"
  ],
  "termino": "concluido"
```

**Como interpretar:**
- `faltando_no_estoque` vazio: dá para fazer agora. O brócolis do nome é acompanhamento opcional, "(for serving)".
- As calorias são da **receita inteira**, porque o acervo não informa porções.
- `escolhas_declaradas` é o que o sistema decidiu sozinho e está avisando.
- `fontes` é o que sustenta a resposta.

**Receita em português.** O acervo é em inglês. Depois desse log, entrou o nó `traduzir_receita`: a saída mostra o nome e os ingredientes traduzidos (`nome_pt`, `ingredientes_pt`), e os originais continuam no JSON. Exemplo real:

```text
Sugestão: Bolo de chocolate (Chocolate Cake). ...
Ingredientes:
  - 9 onças (250 g) de chocolate amargo ou meio amargo, picado
  - 8 colheres de sopa (120 g) de manteiga sem sal
  - 2 tablespoons flour
```

A tradução é feita pelo modelo e **conferida linha a linha em código**: número, unidade e ingrediente precisam ser iguais aos do original. A linha que falha fica em inglês e é declarada. Acima, o modelo tinha escrito "2 colheres de **chá** de farinha", e a linha voltou ao original. Alérgeno, estoque e nutrição são sempre calculados sobre o original em inglês.

### Quando o sistema para e espera você

Ao registrar uma compra, o sistema **não grava nada** antes de você aprovar a lista exata:

```text
$ python -m src.main --usuario ana --sessao compras "comprei leite e 6 ovos"
Vou SOMAR estes itens ao seu estoque (ana):
  - ovo: 6 un
Pendentes:
  ? leite: ambíguo entre leite_desnatado, leite_integral — NÃO será gravado, a menos que você edite
...
Responda até 2026-10-21T23:02:18:
  aprovar | editar <json> | rejeitar
Sem resposta até o prazo, nada é gravado.

$ python -m src.main --usuario ana --sessao compras --editar '[{"item_id":"leite_integral","quantidade":1,"unidade":"l"},{"item_id":"ovo","quantidade":6,"unidade":"un"}]'
Estoque atualizado: leite integral (1 l), ovo (6 un).
```

- A resposta pode vir **de outro processo**, horas depois: a pausa fica gravada em `dados/checkpoints.sqlite`.
- Aprovar duas vezes não soma duas vezes.
- Sem resposta em 24 h, a pausa expira: `python -m src.main --pendentes --expirar`.
- Remover uma alergia também pausa.

Detalhes em [docs/humano.md](docs/humano.md).

### Outras coisas que você pode digitar

| Você digita | O sistema |
|---|---|
| `tenho abobrinha aqui, me sugere alguma coisa com abobrinha` | recomenda com abobrinha e **avisa** que o seu estoque não registra abobrinha (não grava) |
| `quanta proteína tem 100 g de tofu e 100 g de ovo?` | responde o ovo (TBCA) e diz que tofu não está na tabela (`suficiencia: parcial`) |
| `tenho alergia a camarão` | atualiza o perfil |
| `amanhã vou comprar brócolis, me lembra?` | não registra nada sobre o futuro; não envia lembretes |

### O que o sistema não faz

- **não** diagnostica, não trata condição clínica, não prescreve suplemento nem dose ("quantas cápsulas de ômega 3?" → recusa);
- **não** informa porções nem tempo de preparo: o acervo não tem esses dados, e o sistema diz isso em vez de inventar;
- **não** substitui nutricionista;
- **não** desconta do estoque o que você cozinhou;
- **não** lê foto de nota fiscal: cole o texto.

### O que acontece quando ele não sabe

O sistema **recusa e diz o que consegue responder**, com `suficiencia: insuficiente` e as `fontes` vazias:

```text
$ python -m src.main --usuario ana "o que a OMS recomenda sobre cafeína na gravidez?"
Não encontrei nas minhas fontes (TBCA e fichas da OMS) a informação para responder isso. Consigo informar a
composição de alimentos como abacate, abobrinha, ... e as recomendações da OMS sobre alimentação saudável e
sódio. Para outros alimentos, consulte um nutricionista.
```

Toda resposta de nutrição passa por dois controles em código: **todo número precisa estar nas fontes**, e o **trecho citado como prova precisa existir literalmente**. Quando o modelo inventa ("200 mg de cafeína", "130 kcal de quinoa"), a resposta é descartada e o descarte é declarado. Ver [docs/rag.md](docs/rag.md).

---

## A suíte de avaliação (Parte 3)

```bash
# roda os 35 casos de evals/dataset.json pela CLI acima, um processo por passo, e grava
# evals/resultados/v<versão>_<data>/ (rodada.json, casos.jsonl e os traces de cada passo)
python -m evals.rodar --versao 1.1.0          # --versao tem de ser a de src/config.py

# compara duas rodadas, classe a classe, e lista os casos que mudaram de lado
python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>

# latência p50/p95, custo, términos, erro por ferramenta e o SLO, por versão, a partir dos traces
python -m evals.metricas evals/resultados/<rodada-A> evals/resultados/<rodada-B>

# o juiz LLM: gera as 20 saídas a rotular, valida contra os rótulos humanos, julga uma rodada
python -m evals.juiz amostrar
python -m evals.juiz validar
python -m evals.juiz rodada evals/resultados/<rodada>
```

Uma rodada leva ~30 min numa GTX 1650 (a suíte precisa do Ollama no ar). Os resultados das rodadas da entrega estão commitados em [evals/resultados/](evals/resultados/), e a leitura deles em [docs/evals.md](docs/evals.md).

## Os traces

Cada execução grava um trace OpenTelemetry (convenções GenAI: `invoke_agent` → `chat` / `embeddings` / `execute_tool`) em `logs/traces/<data>_<nome>.jsonl`. A CLI imprime o arquivo e o começo do `trace_id` no fim de cada execução.

```bash
python -m src.traces --lista            # as últimas 20 execuções: trace_id, arquivo, término
python -m src.traces                    # a árvore de spans da execução mais recente
python -m src.traces 3f2a9c1e --raiz    # pelo trace_id, com o registro da decisão (todos os atributos da raiz)
python -m src.traces --expurgar         # apaga traces e logs com mais de 90 dias
```

O que cada atributo significa: [docs/observabilidade.md §2](docs/observabilidade.md#2-o-trace-de-uma-execução).

## Suspender o agente

```bash
export NUTRI_TOKEN=$(python -m src.acesso token operador)
python -m src.acesso suspender "motivo"     # toda execução seguinte termina em `suspenso`
python -m src.acesso retomar
python -m src.acesso estado
```

Só o operador suspende e retoma; quem pode, e quando, está no [model card §3](docs/model-card.md#3-autoridade).

---

## Estrutura

```text
README.md            este arquivo
requirements.txt     dependências fixadas (inclusive LangGraph)
.env.example         nomes das variáveis, sem valores
Modelfile            o modelo nutri-qwen (num_ctx 8192)
conferir_grafo.py    imprime nós e arestas do grafo que o sistema executa
docs/                case, modelos, prompts, arquitetura, rag, memoria, grafo, humano, io, fontes,
                     e na Parte 3: mudancas, evals, model-card, seguranca, observabilidade
  evidencias/        E01–E10: saídas de comando dos experimentos
src/                 o sistema (grafo.py é o centro; acesso, integridade, validacao, escopo = os controles)
  prompts/           os prompts, versionados
evals/               dataset, verificações, rodar, comparar, métricas, juiz
  juiz/              rubrica, amostra, rótulos humanos, validação
  resultados/        uma pasta por rodada, commitada: a evidência dos números
scripts/             preparar (do zero), demonstrar (os 6 casos), experimentos (E02–E10)
dados/               catálogo de ingredientes, corpus (receitas, OMS) e manifesto.json (os hashes esperados)
logs/                um JSONL por execução; traces/ tem o trace OpenTelemetry de cada uma
tests/               130 testes das partes determinísticas, entre eles os dos controles
```
