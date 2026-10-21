# O grafo — desenho, padrões, estado e o que o framework não deu

**Versão do sistema:** commit `d16e6b7` · LangGraph 1.2.16 · código em [src/grafo.py](../src/grafo.py)

O desenho ASCII completo, com `[M]`/`[C]`/`⏸`, e a saída do `conferir_grafo.py` ao lado estão em [arquitetura.md §3.1 e §6.1](arquitetura.md#31-o-diagrama). Aqui ficam as decisões.

## 6.1 Cada nó, se chama o modelo, e os términos

| Nó | Chama o modelo? | O que faz |
|---|---|---|
| `inicio` | não | zera os campos do turno (`None` → reducer zera), gera `execucao_id` |
| `carregar_perfil` · `carregar_estoque` · `carregar_historico` | não (só embedding no histórico) | **paralelos**; cada um acrescenta a sua fonte a `fontes` |
| `triagem` | **sim** | rota + `acao_futura` + ingredientes citados |
| `recusar` · `nao_agir` | não | término sem ação |
| `checar_pedido` | não | portão: perfil, estoque, divergência, tempo e porções não informados pelo acervo |
| `chef` | **sim** | uma volta do laço do agente |
| `ferramentas_chef` | não | executa a ferramenta; detecta laço |
| `conferir_proposta` | não | portão: alérgeno, restrição, ingrediente faltando |
| `avaliador` | **sim** (+ TBCA e OMS em código) | veredito contra o objetivo |
| `registrar` | não (só embedding) | grava o histórico, idempotente |
| `consultor` | **sim** | uma volta do laço do agente |
| `ferramentas_consultor` | não | executa a ferramenta; portão de números |
| `verificar_resposta` | **sim** + código | o trecho citado existe na fonte? |
| `extrair_itens` · `extrair_perfil` | **sim** | extração estruturada |
| `casar_catalogo` | não | nome dito → item do catálogo; ambíguo vira pendente |
| `confirmar_estoque` · `confirmar_perfil` | não | **`interrupt`** |
| `gravar_estoque` · `gravar_perfil` | não | escrita idempotente |
| `finalizar` | não | monta a `Saida` validada |

**Términos:** 14 motivos, todos terminando em `finalizar → __end__`, mais a pausa (`aguardando_humano`). A lista está em [arquitetura.md](arquitetura.md#o-término).

## 6.2 Os padrões, nomeados e justificados

| Padrão | Onde, no grafo | Por que ele, e não o de baixo | Condição de não uso |
|---|---|---|---|
| **sequencial com portão** | `checar_pedido` → chef; `casar_catalogo` → `confirmar_estoque` → `gravar_estoque`; `ferramentas_consultor` (portão de números) → `verificar_resposta` | os portões são condições verificáveis (perfil existe? item é ambíguo? número está na fonte?), e verificar é mais barato que gerar | se a condição exigisse julgamento sobre texto livre, viraria roteador |
| **router** | `triagem` → 5 rotas (+ `nao_agir`) | as intenções chegam em texto livre e em proporção relevante cada uma. Uma regra por palavra-chave errava "comprei uma air fryer" (perfil) contra "comprei arroz" (estoque) | se a entrada fosse formulário |
| **paralelização (*sectioning*)** | os três `carregar_*` saindo de `inicio` | três leituras independentes, sem ordem entre si | o ganho de tempo é pequeno (leitura de SQLite), ver a nota abaixo. O padrão está aqui pela **junção correta do estado**, não pelo tempo |
| **avaliador-otimizador** | `chef` ⇄ `conferir_proposta` (código) ⇄ `avaliador` (modelo), até 3 rodadas | a reprovação devolve um motivo que muda a próxima proposta ("faltam no estoque: cogumelo") | se não houvesse critério para reprovar, seria só geração |
| **agente (laço)** | `chef` ⇄ `ferramentas_chef`; `consultor` ⇄ `ferramentas_consultor`; até 5 passos por rodada | o modelo decide que consulta fazer e quando parar ("abobrinha" → busca → propõe). Um workflow com busca fixa não sabe qual ingrediente o pedido enfatiza. Justificativa completa em [arquitetura.md §3.3](arquitetura.md#33-a-defesa-do-nível-de-autonomia) | se a busca pudesse ser sempre a mesma (o avaliador é assim: busca fixa na OMS, sem laço) |
| orquestrador-trabalhador | **não usado** | — | não há subtarefas criadas em tempo de execução |

**O agente é o degrau mais caro, e ele está contido.** O laço livre só existe em duas sub-rotas, com teto de 5 passos e detector de laço. Medido na última rodada do [E06](evidencias/E06-frase.txt): com a regra de parada, os 5 pedidos usaram **1 busca e 4 chamadas ao modelo**. Sem a regra, 1 dos 5 fez uma busca a mais.

**Nota sobre paralelismo.** Não alegamos ganho de tempo. Os três ramos leem o SQLite local e aparecem no log no mesmo instante (`t=2.14` no caso 1), então não há o que medir. Só um deles chama o modelo de embedding.

## 6.3 Quem decide cada bifurcação

| Aresta condicional (função) | Condição | Degrau | Por quê |
|---|---|---|---|
| `triagem` → rotas (`rota_triagem`) | intenção do texto livre | **modelo**, saída `Literal` de 5 rotas | julgamento sobre texto. O `Literal` garante que a resposta seja uma rota; não garante a rota certa (medido: 20/20 na v1.1.0, 18/20 na v1.0.0, [E07](evidencias/E07-etapas.txt)) |
| `triagem` → `nao_agir` | `acao_futura` e rota ≠ pergunta | **regra em código** sobre um campo do modelo | a **rota** desses pedidos oscilou entre versões do prompt ("vou comprar peixe amanhã" → `recomendar`); o **campo** `acao_futura` foi estável. O código decide pelo campo estável |
| `checar_pedido` → chef / fim | perfil é `None`? estoque vazio? | **regra em código** | um `None` não precisa de modelo |
| `chef`/`consultor` → ferramentas / fim (`rota_agente`) | `termino` gravado? | **regra em código** | o modelo escolhe a ferramenta; a aresta só olha se o orçamento acabou |
| `ferramentas_chef` → conferir / chef / fim | existe `proposta`? | **regra em código** | campo |
| `conferir_proposta` → avaliador / chef / fim | `veredito` existe? | **regra em código** | o portão já decidiu |
| `avaliador` → registrar / chef / fim | `veredito.aprovado` | **modelo**, saída `bool` estruturada | "sobremesa de 2.000 kcal para quem quer emagrecer" é julgamento |
| `ferramentas_consultor` → verificar / consultor / fim | resposta existe e passou nos números? | **regra em código** | campo + portão |
| `casar_catalogo` → confirmar / fim | há algum item? | **regra em código** | lista vazia |
| `confirmar_*` → gravar / fim | `decisao_humana.acao` | **a pessoa** (pelo `interrupt`) | é a função da pausa |
| `extrair_perfil` → confirmar / gravar | (campo, operação) == (alergias, remover) | **regra em código** | campo |

**Nenhuma aresta usa embedding.** As rotas da triagem são poucas e estáveis, o que favoreceria o degrau do embedding. Mas a distinção que mais importa, "comprei" contra "vou comprar", é de **tempo verbal**, e o embedding de assunto não separa isso. Por isso o modelo, com o campo `acao_futura`.

## 6.4 A implementação

- `StateGraph(Estado)` com 24 nós; **12** arestas condicionais, todas com mapa de destinos explícito ([grafo.py](../src/grafo.py) `construir`).
- Paralelismo por três arestas saindo de `inicio` e junção por `add_edge([...], "triagem")`.
- Compilado **uma vez** por processo: `obter_grafo()` com `@cache`. É o objeto que `src/main.py` executa e que `conferir_grafo.py` importa.

## 6.5 O que o framework não deu

| Frente | O framework cobre? | O que escrevemos | Linhas |
|---|---|---|---|
| **motivo de término** | não. `END` diz que acabou, não por quê | campo `termino` com `Literal` de 14 motivos ([esquemas.py](../src/esquemas.py):94); cada rota olha `termino` primeiro (15 checagens em [grafo.py](../src/grafo.py)); `montar_saida` traduz o motivo em texto para a pessoa (67 linhas) | ~85 |
| **detector de laço** | não. O `recursion_limit` limita o dano, não detecta | `_laco` (10 linhas): a mesma chamada, com nome e argumentos, repetida no turno → `laco_detectado`. Pegou um caso real durante o desenvolvimento: o chef repropôs R01484 depois de reprovado (execução de 20/10, 22h26; o log não foi mantido, porque é anterior à versão que a ferramenta passou a filtrar as reprovadas) | 10 |
| **tetos** | só o de **passos do grafo** (`recursion_limit`) | `estouro` (10 linhas): tempo de parede, tokens por execução e janela por chamada. `_passo_agente` (32 linhas): passos por rodada do agente. `_reprovar` (11): rodadas | ~53 |
| **erro recuperável × fatal** | não. Uma exceção num nó derruba a execução | `ErroFatal` em [llm.py](../src/llm.py) (rede/servidor = fatal; JSON inválido = recuperável **uma** vez); decorador `no()` (9 linhas) transforma fatal em término `erro_fatal`. Erro de ferramenta (receita inexistente, alimento fora da TBCA) volta ao modelo como resultado, com a dica do que fazer | ~40 |
| **modelo que responde em texto em vez de chamar a ferramenta** | não | fechamento com saída estruturada em `_passo_agente`, mais `_fechar_chef`/`_fechar_consultor` | ~20 |
| **checkpoint, `interrupt`, retomada** | **sim, inteira** | nada: `SqliteSaver` em [grafo.py](../src/grafo.py) `checkpointer()` (3 linhas), `interrupt(...)` em `confirmar_estoque`, `Command(resume=...)` em [main.py](../src/main.py) `executar` | 0 de mecanismo |
| **escrita concorrente sem reducer** | **sim, detecta**: `InvalidUpdateError` ([E03](evidencias/E03-reducer.txt)) | nada | 0 |

Total escrito para cobrir o que o framework não deu: **~210 linhas**, contra 787 de [grafo.py](../src/grafo.py).

## 6.6 A decisão que virou parâmetro

### O limite de recursão (LangGraph)

- **A decisão:** quantos passos uma execução pode dar antes de ser cortada. Na arquitetura v1, ela era explícita e justificada: `MAX_PASSOS_CHEF = 5`, `MAX_RODADAS_AVALIACAO = 3` ([arquitetura-v1.md](arquitetura-v1.md) §2).
- **O que o framework fez com ela:** um parâmetro `recursion_limit` com valor padrão. No LangGraph 1.2.16 o padrão é **10007** (`DEFAULT_RECURSION_LIMIT` em `langgraph/_internal/_config.py`, linha 32). Nas versões 0.x era 25. E ele pode ser trocado **por variável de ambiente** (`LANGGRAPH_DEFAULT_RECURSION_LIMIT`), sem tocar no código.
- **O que acontece se o padrão mudar:** já mudou, de 25 para 10007. Um agente preso que antes parava em 25 passos agora roda 10 mil chamadas ao modelo. Com ~1,5 s por chamada, isso dá quatro horas de GPU para uma resposta errada.
- **Declarado no código:** `RECURSION_LIMIT = 40` em [config.py](../src/config.py), passado em toda execução ([main.py](../src/main.py)) e registrado no cabeçalho de todo log. O valor 40 cobre o pior caso legítimo: 3 rodadas × (5 passos do agente + ferramentas + portão + avaliador) ≈ 36 passos do grafo.

### A janela de contexto (Ollama)

Não é do LangGraph, mas é o mesmo fenômeno, e foi medido.
- **A decisão:** quanto contexto cabe numa chamada. A v1 declarou 6.000 tokens.
- **O parâmetro:** `num_ctx`, com padrão 4096 no Ollama 0.40.6 para este modelo.
- **O que acontece:** um prompt de 4.559 tokens foi processado com **2.050**. O Ollama descartou o **início** (onde fica o system prompt) sem erro nem aviso ([E02](evidencias/E02-janela.txt)).
- **Declarado:** `PARAMETER num_ctx 8192` no [Modelfile](../Modelfile), o que criou o modelo `nutri-qwen`. A maior janela usada pelo sistema foi de 1.712 tokens, e o teto de 6.000 por chamada é conferido em `estouro`.

## 7. O estado que atravessa o grafo

### 7.1 Os campos

A tabela completa (campo, tipo, quem escreve, quem lê, de onde veio) está em [arquitetura.md §7.1](arquitetura.md#71-os-campos-do-estado-e-quem-mexe-em-cada-um).

### 7.2 Os reducers, e o que acontece sem eles

| Campo | Reducer | Por quê |
|---|---|---|
| `fontes`, `escolhas`, `agente_msgs`, `recuperacoes`, `descartes_oms`, `rejeitadas` | `por_turno` ([estado.py](../src/estado.py)): acumula dentro do turno; `None` zera | vários nós acrescentam (três deles **no mesmo passo**). E o checkpointer guarda o estado **entre turnos**: com `operator.add`, as fontes do turno anterior apareceriam na saída deste. O `inicio` manda `None`, e o reducer zera |
| `uso` | `somar_uso` | soma tokens, chamadas e segundos; guarda a **maior** janela, para o teto por chamada |
| `conversa` | `janela_conversa` | acumula e corta pelo **início**: mantém os 6 últimos turnos ([memoria.md §5.5](memoria.md#55-a-conversa-e-o-que-sobra-dela)) |

**A demonstração**, com o mesmo grafo e `fontes` sem reducer ([E03](evidencias/E03-reducer.txt), `python -m scripts.experimentos reducer`):

```text
--- reducer em `fontes`: SIM (por_turno)
  carregar_estoque     escreveu fontes=['estoque']
  carregar_perfil      escreveu fontes=['perfil']
  carregar_historico   escreveu fontes=['historico', 'historico']
  estado depois da junção: fontes=['estoque', 'historico', 'historico', 'perfil']
--- reducer em `fontes`: NÃO (último valor)
  carregar_estoque     escreveu fontes=['estoque']
  carregar_perfil      escreveu fontes=['perfil']
  carregar_historico   escreveu fontes=['historico', 'historico']
  EXCEÇÃO InvalidUpdateError: At key 'fontes': Can receive only one value per step. Use an Annotated key to handle multiple values.
```

**O resultado contradiz o que esperávamos, e é um achado.** No LangGraph 1.2.16, duas escritas no **mesmo passo** num campo sem reducer **não** são sobrescritas em silêncio: a execução para com `InvalidUpdateError`. O defeito silencioso continua existindo, mas em outro lugar: escritas em **passos diferentes**. Sem reducer, as fontes gravadas pelos carregadores seriam substituídas pela fonte gravada por `registrar`, sem erro, e a saída listaria só a receita. Isso é a semântica de "último valor"; não foi demonstrado em execução, porque o grafo sem reducer para antes, na junção. É por isso que `fontes` tem reducer, mesmo depois da junção.

### 7.3 O que NÃO está no estado

**O que ficou na lista de mensagens.** Só `conversa` (o texto que a pessoa disse e o que ela leu) e `agente_msgs` (o rascunho do laço do turno, com resultados de ferramenta). Decisão (`veredito`, `proposta`), contador (`passos_agente`, `rodadas`) e identificador (`usuario_id`, `execucao_id`) são campos tipados, e nenhum nó os procura dentro de mensagens.

**O que é derivado e não guardado:**
- o **contexto das ferramentas** (`ctx_de`): o que está disponível, os alérgenos bloqueados, os ids recentes e os rejeitados. É recalculado do estado a cada nó, porque guardá-lo criaria uma segunda fonte de verdade sobre o estoque;
- a **nutrição** de uma receita no histórico: só a kcal vai para a linha, e o resto é recalculado da TBCA, porque um valor guardado ficaria errado sem aviso se a TBCA mudasse ([memoria-v1.md](memoria-v1.md) §3);
- o **texto do prompt montado**: o log guarda versão@hash de cada prompt, não o texto;
- o **detector de laço**: deriva as chamadas já feitas de `agente_msgs`, em vez de manter uma lista paralela.

### 7.4 O estado entre agentes

O sistema tem três papéis com modelo (chef, avaliador, consultor), mas não é multiagente: os três leem o **mesmo estado**. Quem limita o que cada um vê é o **prompt montado** por nó:
- o chef recebe objetivo, alergias, restrições, estoque e histórico recente;
- o avaliador recebe só o objetivo, a receita, a nutrição e um trecho da OMS;
- o consultor recebe só a pergunta.

Passar o estado inteiro acopla os papéis a cada campo novo. A escolha é **provisória**: na Parte 3, chef e avaliador viram agentes, e o contrato entre eles será um objeto próprio (`Proposta` → `Veredito`).
