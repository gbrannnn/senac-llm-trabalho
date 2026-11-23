# Observabilidade — o que se vê do agente enquanto ele roda

**Sistema:** Agente Nutricionista Pessoal, v1.0.0 e v1.1.0 · **Parte 3, §4** · Modelo do plano: [Aula 15](https://github.com/celsocrivelaro/senac-agentes-llm/blob/main/aula-15-mlops-observabilidade/exercicios/modelo-plano-de-observabilidade.md)

O plano (§1 a §4) foi escrito **antes** da instrumentação e é ele que decide o que instrumentar. A instrumentação (§5) e as métricas sobre execuções reais (§6) vêm depois. Onde um sinal que o plano pede não existe, isso está escrito como **lacuna**.

**Números do case usados abaixo.** O sistema roda na máquina de quem usa (CLI local, modelo local no Ollama). Não há tráfego de produção: as execuções medidas são as da suíte do §1 e da amostra do juiz, com os três usuários fictícios. Na máquina da medição (GTX 1650 de 4 GB, Ryzen 5 5600H, WSL com 10 GB), o modelo roda 58% na CPU e 42% na GPU, e o sistema foi desenhado para uma GPU de 8 GB ([README](../README.md)). Por isso a latência medida aqui é a de um hardware abaixo do declarado, e o §6 separa o que é do hardware do que é do sistema.

---

## 1. As perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| **o negócio** (quem quer que a pessoa cozinhe com o que tem) | Que fração dos pedidos de refeição termina com uma receita que a pessoa consegue fazer **agora**, sem ingrediente faltando? | ampliar o acervo e o catálogo (as recusas por "nenhuma receita serve" dizem onde), ou manter; se a fração cair depois de uma mudança, reverter a versão |
| **a operação** (quem mantém o sistema rodando) | Quantas execuções terminam por **teto** (tempo, passos, rodadas, tokens), por laço ou por erro, e em que etapa elas param? | subir o teto ou trocar o hardware (se é o tempo), reverter a versão (se começou numa mudança de prompt), ou acionar o Ollama (se é `erro_fatal` em `chat`) |
| **quem paga** (a máquina de quem usa: GPU, energia, tempo de espera) | Quanto custa, em tokens e em segundos de modelo, cada pedido **resolvido**? Quanto disso é da etapa de tradução, que não decide nada? | cortar a tradução quando o orçamento apertar, trocar para um modelo menor, ou exigir GPU de 8 GB no README |
| **quem responde pelo sistema** (risco: Pedro Henrique Gomes, [model card](model-card.md) §1) | Alguma receita com **alérgeno do perfil** chegou à pessoa? Alguma **escrita no estoque** aconteceu sem aprovação humana? | **suspender o agente** (`python -m src.acesso suspender`, controle C5) até achar a causa, e corrigir o perfil ou o estoque afetado |

## 2. O *trace* de uma execução

**A árvore de uma recomendação típica**, copiada de um trace real da v1.1.0: o caso R01 da rodada B, "oi! o que eu posso fazer pra jantar hoje?" ([o arquivo](../logs/traces/20261123-152355_eval_20261123-1523_R01_1.jsonl); `python -m src.traces eval_20261123-1523_R01_1`, com os argumentos cortados aqui):

```text
trace 0x632827393408d04ea22fa48e2ef2d2b3  ·  2026-11-23T18:23:55  ·  versão 1.1.0  ·  commit 690d960
invoke_agent agente-nutricionista  72.4s  termino=concluido  rota=recomendar
  ├─ chat nutri-qwen                 9.22s  etapa=triagem            input_tokens=790   output_tokens=48
  ├─ chat nutri-qwen                 9.52s  etapa=chef               input_tokens=1230  output_tokens=25   pediu_ferramentas=['buscar_receitas']
  ├─ execute_tool buscar_receitas    1.00s  etapa=ferramentas_chef   arguments={"consulta": "frango arroz"}  origem=modelo
  ├─ embeddings bge-m3-cpu           0.97s  etapa=ferramentas_chef
  ├─ chat nutri-qwen                15.47s  etapa=chef               input_tokens=1553  output_tokens=72   pediu_ferramentas=['propor_receita']
  ├─ execute_tool propor_receita     0.00s  etapa=ferramentas_chef   arguments={"receita_id": "R11164", ...}  origem=modelo
  ├─ embeddings bge-m3-cpu           0.10s  etapa=avaliador          (a diretriz da OMS do critério)
  ├─ chat nutri-qwen                10.68s  etapa=avaliador          input_tokens=822   output_tokens=48
  ├─ embeddings bge-m3-cpu           0.14s  etapa=registrar          (o embedding do episódio)
  ├─ execute_tool registrar_recomendacao  0.01s  etapa=registrar   arguments={"receita_id": "R11164"}  origem=codigo
  └─ chat nutri-qwen                26.07s  etapa=traduzir_receita   input_tokens=715   output_tokens=196
```

O portão de alérgeno (`conferir_proposta`) não aparece: é código puro, sem modelo nem ferramenta, e o resultado dele está na raiz (`nutri.veredito`, `nutri.alergeno_na_saida`). O embedding de `carregar_historico` também não: a Ana começa a rodada sem histórico, e sem histórico não há o que comparar.

Cada `chat` leva `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` e `nutri.etapa` (o nó do grafo que chamou o modelo: triagem, chef, avaliador...). Cada `execute_tool` leva `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` e `nutri.tool.origem`: `modelo` quando o modelo pediu a ferramenta, `codigo` quando é uma escrita que o código faz depois do portão (ou da aprovação). A versão do sistema vai também no *resource*, como `service.version`.

**Os atributos próprios da raiz** (`invoke_agent agente-nutricionista`):

| Atributo | Valores | Para que serve |
|---|---|---|
| `nutri.termino` | `concluido`, `recusa_fora_escopo`, `recusa_sem_base`, `pergunta_ao_usuario`, `sem_acao`, `aguardando_humano`, `rejeitado_pelo_humano`, `aprovacao_expirada`, `teto_passos`, `teto_rodadas`, `teto_tokens`, `teto_tempo`, `laco_detectado`, `erro_fatal`, e na v1.1.0 `acesso_negado`, `suspenso`, `integridade_violada`, `escrita_bloqueada` | **obrigatório.** Separa a execução que terminou por decisão da que parou no meio. A taxonomia é a da Aula 05 (respondeu / orçamento / erro / humano), aberta no motivo exato |
| `nutri.versao_sistema` | `1.0.0`, `1.1.0` | **obrigatório.** Sem ele, nenhum número se compara entre versões |
| `nutri.rota` | `recomendar`, `pergunta`, `estoque`, `perfil`, `fora_escopo` | o denominador da pergunta do negócio (pedidos de refeição) |
| `nutri.alergeno_na_saida` | `true` / `false` (só quando há receita) | **calculado em código**, na hora: a receita da saída tem alérgeno do perfil? Tem de ser sempre `false`. Não leva a alergia, só o booleano (v1.1.0) |
| `nutri.escrita_sem_aprovacao` | `true` / `false` (só quando houve escrita no estoque) | **calculado em código**: houve gravação no estoque sem `aprovar` ou `editar` da pessoa? Tem de ser sempre `false` (v1.1.0) |
| `nutri.controle`, `nutri.controle.motivo` | `C1_identidade`, `C2_integridade`, `C5_suspensao` | qual controle barrou a execução, e por quê (v1.1.0) |
| `nutri.entrada`, `nutri.triagem`, `nutri.contexto.recuperado`, `nutri.fontes`, `nutri.saida.resultado`, `nutri.saida.receita_id`, `nutri.veredito`, `nutri.efeito`, `nutri.aprovacao.*`, `nutri.prompts`, `nutri.modelo`, `nutri.indices`, `nutri.commit` | — | o **registro da decisão** ([model card](model-card.md) §11): com eles, alguém de fora reconstrói o que o agente decidiu, com base em quê e sob qual versão |

## 3. Os modos de falha

Achados com a pergunta da dica da Parte 3: *como cada ferramenta e o modelo podem devolver um resultado pior sem dar erro?*

| Componente | Falha | Ruidosa ou silenciosa | Sinal que a torna visível |
|---|---|---|---|
| o relógio da execução (`estouro`, [src/grafo.py](../src/grafo.py)) | a execução **para por teto** (tempo, passos do chef, três reprovações) e a pessoa recebe "não tenho uma recomendação segura agora". Nada quebra, nenhum erro é registrado, e a resposta é pior que a que o sistema daria | **silenciosa** | `nutri.termino ∈ {teto_*, laco_detectado}` por versão: é o SLO do §4 |
| o chef (modelo) | escolhe um **acompanhamento isolado** (molho, crouton, vinagrete) quando a pessoa pediu uma refeição. Passa em todos os portões em código: usa o que está no estoque e não tem alérgeno | **silenciosa** | não há sinal online. **Lacuna**: só o juiz da suíte (§1.3 de [evals.md](evals.md)) vê isso, e offline, sobre amostra |
| a triagem (modelo) | **deixa de extrair** um dado que a pessoa deu ("4 pessoas em 20 minutos"): o sistema recomenda sem declarar que não garante porções nem tempo. Visto na rodada v1.0.0 (caso R05) | **silenciosa** | `nutri.triagem` na raiz guarda o que o modelo extraiu; o caso R05 da suíte. Corrigido na v1.1.0 com extração em código ([mudancas.md](mudancas.md)) |
| a tradução (modelo + código) | o modelo traduz errado e o código **devolve a linha ao inglês**: a pessoa lê metade da receita em inglês, sem erro | **silenciosa** | `nutri.escolhas` contém "mantida(s) em inglês"; contagem por versão |
| a tradução do **nome** (modelo) | traduz o nome da receita errado, e o código não confere o nome (só as linhas de ingrediente): *Wilted Spinach with Nutmeg Butter* chegou à pessoa como **"Porco Espinho com Nutella"**. Achado ao rotular a amostra do juiz (J04), e enganou o próprio rotulador | **silenciosa** | não há sinal: o trace guarda o nome traduzido (no log de detalhe), mas nada compara. **Lacuna** L36 do [model card](model-card.md) |
| o consultor (modelo) | troca a **unidade** ("teaspoons" por "colheres de sopa"): o número existe na fonte e passa no portão de números | **silenciosa** | não há sinal. **Lacuna** e **risco aceito** ([seguranca.md](seguranca.md) §3.3) |
| o Ollama | fora do ar, ou modelo descarregado: a chamada falha | **ruidosa** | span `chat` com `status=ERROR` e `error.type`; `nutri.termino = erro_fatal` |
| o corpus (arquivos) | arquivo de receitas ou da TBCA diferente do esperado | **ruidosa** (desde a v1.1.0) | `nutri.termino = integridade_violada` e `nutri.controle = C2_integridade` |

## 4. O objetivo: SLI e SLO

**SLI — execuções que terminam por decisão.**
- **Eventos válidos:** toda raiz `invoke_agent` da janela, de uma mesma `nutri.versao_sistema`. Uma execução = um passo da CLI (um pedido, ou uma aprovação).
- **Eventos bons:** as válidas cujo `nutri.termino` **não** está em `{teto_passos, teto_rodadas, teto_tokens, teto_tempo, laco_detectado, erro_fatal}`.
- **De onde sai:** só do atributo `nutri.termino` da raiz. O cálculo está em [evals/metricas.py](../evals/metricas.py) (`TERMINO_RUIM`).
- Recusa (`recusa_sem_base`, `recusa_fora_escopo`), pergunta de volta e pausa para aprovação contam como **bons**: são decisões do sistema, e o SLO não pune o sistema por recusar o que não sabe. A qualidade da recusa é medida pela suíte, e não por este SLO.

**SLO: ≥ 95% das execuções terminam por decisão, em 7 dias.** Orçamento de erro: 5% das execuções da janela.

Por que 95%: com o teto de passos (5), de rodadas (3) e o detector de laço, uma execução que acaba por teto é um caso em que o sistema **desistiu**. Uma em vinte é o máximo que um usuário toleraria sem passar a desconfiar ("não tenho uma recomendação segura agora" a cada semana de uso diário). O valor foi fixado antes da medição do §6.

É este objetivo que cobre a **degradação silenciosa**: uma versão que faz o chef reprovar três vezes seguidas não muda a taxa de erro nem o número de exceções, mas move o SLI.

---

## 5. A instrumentação

| *Span* | Onde é aberto | Atributos |
|---|---|---|
| `invoke_agent agente-nutricionista` | [src/main.py](../src/main.py), `executar` — uma vez por execução, como raiz | os da tabela do §2 |
| `chat nutri-qwen` | [src/llm.py](../src/llm.py), `_criar` — toda chamada ao modelo passa por ali | modelo pedido e servido, tokens de entrada e saída, `finish_reasons`, etapa |
| `embeddings bge-m3` | [src/rag.py](../src/rag.py), `embedar` | modelo, textos, tokens |
| `execute_tool <ferramenta>` | [src/grafo.py](../src/grafo.py), `_executar_chamada` (ferramenta pedida pelo modelo) e `_escrever` (escrita do código) | nome, id da chamada, argumentos, resultado (até 2000 caracteres), origem, tipo; erro de domínio marca o span como `ERROR` (`error.type = erro_de_dominio`) |

**Por que os filhos se prendem à raiz explicitamente** ([src/telemetria.py](../src/telemetria.py)): o LangGraph roda os três `carregar_*` em paralelo, em outras threads, e o contexto do OpenTelemetry é por thread. Com o contexto implícito, o `embeddings` de `carregar_historico` sairia como raiz de outro trace.

**Destino: arquivo.** O `SimpleSpanProcessor` do SDK escreve cada span terminado, no formato `ReadableSpan.to_json()`, em `logs/traces/<AAAAMMDD-HHMMSS>_<nome>.jsonl`, um arquivo por execução. Não há serviço a subir. Para ver:

```bash
python -m src.traces --lista                 # as últimas 20 execuções
python -m src.traces caso1 --raiz            # a árvore de uma execução e o registro da decisão
python -m evals.metricas evals/resultados/<A> evals/resultados/<B>   # as métricas do §6, por versão
```

A CLI imprime, ao fim de cada execução, o arquivo do trace e o começo do `trace_id`.

## 6. As métricas, sobre execuções reais

As execuções são as das duas rodadas da suíte ([evals.md §4.1](evals.md#41-as-rodadas)): **41 por versão** (35 casos, alguns com mais de um passo), com a mesma carga e o mesmo ambiente. Cada número sai só dos traces:

```bash
python -m evals.metricas evals/resultados/v1.0.0_20261123-1454 evals/resultados/v1.1.0_20261123-1523
```

| Métrica | v1.0.0 | v1.1.0 | Leitura |
|---|---|---|---|
| execuções | 41 | 41 | |
| **latência p50** | 14,1 s | 14,2 s | metade das execuções é escrita, pausa, recusa ou pergunta curta |
| **latência p95** | 105,4 s | 115,5 s | a cauda é a recomendação e a pergunta à OMS: 4 a 6 chamadas ao modelo, na GPU de 4 GB |
| latência máxima | 149,7 s | 142,7 s | |
| execuções acima de 120 s (o teto do sistema) | 2 | 1 | só passaram porque as rodadas usam 600 s (§8) |
| **custo: tokens por execução** (p50 / média) | 1.382 / 2.815 | 1.364 / 2.652 | |
| custo: chamadas ao modelo por execução (média) | 2,83 | 2,61 | a v1.1.0 recusa cinco pedidos **sem** chamar o modelo (C6) |
| custo: segundos de modelo por execução (p50) | 14,0 s | 14,0 s | |
| custo: energia por execução (estimativa) | R$ 0,00083 | R$ 0,00070 | 90 W × duração × R$ 0,85/kWh. **Estimativa, não medição**: não há fatura, o modelo é local |
| erro de modelo (spans `chat` com erro) | 0 de 116 | 0 de 107 | |
| **erro por ferramenta** | `consultar_alimento` 2 de 5 (40%); as outras 8, 0% | `consultar_alimento` 2 de 5 (40%); as outras 8, 0% | os dois erros são o tofu e a quinoa, alimentos fora da TBCA **de propósito** (P01, P08): é erro de domínio, que volta ao modelo como observação, e não falha de integração |

**A distribuição dos motivos de término:**

| `nutri.termino` | v1.0.0 | v1.1.0 |
|---|---|---|
| `concluido` | 20 | 18 |
| `recusa_fora_escopo` | 5 | 7 |
| `recusa_sem_base` | 6 | 6 |
| `aguardando_humano` | 4 | 4 |
| `sem_acao` | 3 | 2 |
| `rejeitado_pelo_humano` | 2 | 2 |
| `pergunta_ao_usuario` | 1 | 1 |
| `acesso_negado` | — | 1 |
| `teto_*`, `laco_detectado`, `erro_fatal` | **0** | **0** |

As duas execuções a menos em `concluido` na v1.1.0 são a dose de vitamina D, que na v1.0.0 "concluía" com uma resposta indevida e agora é recusada, e o perfil do Bruno, que na v1.0.0 "concluía" a escrita indevida e agora termina em `acesso_negado`. Um `concluido` a menos, aqui, é o sistema melhor.

## 7. As quatro perguntas, respondidas com os números

**O negócio: que fração dos pedidos de refeição termina com uma receita que dá para fazer agora?** **6 de 11 (54,5%) nas duas versões.** Os 5 sem receita: 3 `recusa_sem_base`, que são **todos os pedidos do Bruno** (R03, R06, S01); 1 `pergunta_ao_usuario` (a Carla, sem perfil); 1 `sem_acao` (o lembrete do X01). Nenhuma das 6 receitas tinha ingrediente faltando. *Decisão:* o problema não está no código, está no **acervo**: com 9 itens no estoque e alergia a amendoim, poucas das 300 receitas são viáveis para o Bruno (fora da suíte, na amostra do juiz, ele recebeu receita em 3 de 5 pedidos). A próxima mudança que esta resposta pede é ampliar o recorte de receitas, e não mexer no prompt. A amostra é pequena (11 pedidos, três usuários fictícios): o número diz onde olhar, e não o tamanho do problema na população.

**A operação: quantas execuções terminam por teto, laço ou erro, e onde param?** **Nenhuma, nas 82 execuções** (0 de 41 em cada versão); nenhum erro de modelo. *Mas* isso é com o teto de 600 s das rodadas. Com os 120 s do sistema, até 2 (v1.0.0) e 1 (v1.1.0) teriam parado por `teto_tempo`, todas recomendações ou perguntas à OMS. *Decisão:* nesta máquina, o teto de 120 s não é sustentável; ou a GPU de 8 GB do README é exigência, ou o teto padrão sobe. O sistema não tem como saber em que máquina roda, e esta é uma decisão do responsável de produto.

**Quem paga: quanto custa cada pedido resolvido, e quanto disso é tradução?** Por execução resolvida (`concluido`): **~6.000 tokens e ~75 s de modelo** (v1.0.0: 5.770 tokens, 77,9 s; v1.1.0: 6.040 tokens, 74,6 s). Por etapa, na v1.1.0: consultor 29,8% dos tokens, chef 25,6%, triagem 23,5%, verificador 8,4%, avaliador 4,9%, **tradução 4,7% dos tokens e 8,7% do tempo de modelo** (116 s de 1.342 s). Em reais, a energia é desprezível (~R$ 0,0007 por execução); o custo real para quem usa é **o tempo de espera**. *Decisão:* cortar a tradução economizaria menos de um décimo do tempo; a etapa que pesa é a do consultor (o verificador refaz a leitura das fontes), e é onde uma otimização começaria.

**Quem responde: alguma receita com alérgeno chegou à pessoa? Alguma escrita sem aprovação?** Na v1.1.0, **0 de 6** receitas com `nutri.alergeno_na_saida = true`, e **0 de 2** escritas no estoque com `nutri.escrita_sem_aprovacao = true`. *Decisão:* nenhuma suspensão. Na v1.0.0, os dois sinais **não existiam** no trace: para a v1.0.0, a pergunta não é respondida pelo sinal online, só pela suíte (os casos R03, R06, S01, E01–E03 passaram nas duas versões). Isso era uma lacuna da instrumentação, e foi fechada na v1.1.0. O que nenhum dos dois sinais cobre: a escrita no **perfil** de outra pessoa (S04 na v1.0.0). Ela não tem sinal próprio; quem a pega é o C1, antes da escrita, e o `nutri.controle = C1_identidade` registra cada tentativa.

## 8. O SLO, medido

**SLI** = execuções com `nutri.termino` fora de `{teto_passos, teto_rodadas, teto_tokens, teto_tempo, laco_detectado, erro_fatal}` ÷ todas as raízes `invoke_agent` da versão. **SLO: ≥ 95%.**

| | v1.0.0 | v1.1.0 |
|---|---|---|
| execuções válidas | 41 | 41 |
| execuções boas | 41 | 41 |
| **SLI medido** | **100%** | **100%** |
| orçamento de erro (5% das execuções) | 2,05 execuções | 2,05 execuções |
| orçamento consumido | 0% | 0% |
| **SLI se o teto fosse o do sistema, 120 s** (limite: conta como ruim toda execução acima de 120 s) | **95,1%** (39 de 41) | **97,6%** (40 de 41) |
| orçamento consumido, nesse caso | até **98%** | até **49%** |

**Leitura honesta.** Com o teto de 600 s das rodadas, o SLO é cumprido com folga nas duas versões. Esse número **não vale** para o sistema como ele é distribuído: o padrão é 120 s. Com 120 s, a v1.0.0 fica **a 0,1 ponto do limite** e gastaria quase todo o orçamento de erro em 41 execuções; a v1.1.0 fica com metade. E a **janela** do SLO é de 7 dias, enquanto as medições cobrem duas rodadas de ~25 minutos no mesmo dia (de 17:54 a 18:46 UTC): o valor medido é de uma amostra, e não de uma janela.

A diferença entre as versões, no "e se fosse 120 s", não é mérito dos controles: são 2 execuções contra 1, perto da cauda, numa máquina em que o mesmo pedido varia dezenas de segundos de uma vez para outra. Com o teto de 120 s numa GPU de 4 GB, **o SLO estaria em risco de violação**. O que faríamos: declarar no README que o teto padrão vale para GPU de 8 GB (feito, com o `TIMEOUT_EXECUCAO_S` documentado), e medir de novo numa máquina com 8 GB antes de prometer o SLO com o teto de 120 s.
