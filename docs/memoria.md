# Memória — o que o agente lembra, o que esquece, e a conversa

**Versão do sistema:** commit `d16e6b7` · código em [src/db.py](../src/db.py), [src/memoria.py](../src/memoria.py), [src/estado.py](../src/estado.py), [src/remover.py](../src/remover.py)

As decisões de projeto estão em [memoria-v1.md](memoria-v1.md), escrito antes do código. Este documento diz o que foi **implementado**, o que mudou e o que foi medido. Quando os dois divergem, vale este.

## 5.1 Os dois níveis, e a fronteira entre três estruturas

| | curto prazo | longo prazo |
|---|---|---|
| **o que é, no case** | um turno: da mensagem da pessoa até a `Saida` (ou até a pausa) | o que atravessa turnos e sessões da mesma pessoa |
| **conteúdo** | prompt de sistema + pedido + `agente_msgs` (busca, resultados, reprovações) + perfil e estoque **lidos neste turno** + proposta corrente | episódica (histórico de recomendações), semântica (perfil), procedural (regras curadas) |
| **persistido como** | **checkpoint** do LangGraph (`SqliteSaver`, `dados/checkpoints.sqlite`): o estado inteiro a cada passo | tabelas SQLite (`perfil`, `historico` com o vetor na linha) e texto ([regras_procedurais.md](../src/prompts/regras_procedurais.md)) |
| **ciclo de vida** | um turno vale até o próximo turno da mesma sessão; os campos `por_turno` são zerados no `inicio` | acumula, com decaimento (episódica) e remoção (todas) |

### O que precisa estar no checkpoint para retomar sem reaplicar efeito

A retomada só acontece na pausa (`interrupt`). Para que ela não reaplique nada, três coisas estão gravadas **antes** do `interrupt`:
- `itens_propostos` e `pendentes`: a pessoa aprova exatamente o que viu;
- `expira_em`, gravado em `casar_catalogo`, e não no nó que pausa. A retomada **roda o nó de novo desde o começo**: se o prazo fosse calculado ali, ele recomeçaria a cada retomada e nunca venceria;
- nenhum efeito colateral antes do `interrupt` em `confirmar_estoque`/`confirmar_perfil`. A escrita está no nó seguinte e é idempotente.

Medido: um turno grava **9 a 18 checkpoints** (um por passo do grafo). O arquivo chegou a ~600 KB para 4 conversas de um turno, porque o checkpoint guarda o estado inteiro, inclusive os resultados de ferramenta em `agente_msgs`. Isso é dado pessoal: o perfil lido no turno vai junto. A remoção cobre o checkpoint ([§5.4](#54-como-o-agente-perde-a-memória)).

### A ordem de descarte quando a janela não cabe

A v1 decidiu uma ordem de descarte dinâmico: trechos → histórico → trajetória → nunca o prompt e o pedido. **A implementação fez diferente**: em vez de descartar em tempo de execução, cada fonte tem tamanho **limitado por construção**, e o estouro vira término.

| Fonte | Limite | O que nunca sai |
|---|---|---|
| prompt de sistema + prompt da etapa | fixo (a triagem inteira usa ~790 tokens, medido) | **nunca é cortado** |
| pedido da pessoa | o texto inteiro | **nunca é cortado** |
| trechos da OMS | 3 trechos × até 1.200 caracteres | — |
| receitas | 5 resumos (id, nome, itens, faltando) | — |
| preparo de receita (`detalhar_receita`) | 800 caracteres | — |
| histórico (episódica) | 3 recomendações mais relevantes | — |
| conversa | 6 turnos, corte pelo **início** | o turno mais recente |

Se ainda assim uma chamada passar de 6.000 tokens, a execução termina em `teto_tokens`, **em vez de truncar**. O motivo: o truncamento do Ollama corta o início, que é onde está o prompt de sistema ([E02](evidencias/E02-janela.txt)). Medido: a maior janela em todos os logs foi **1.712 tokens**.

### Checkpoint × memória × RAG, no case

| | checkpoint | memória | RAG |
|---|---|---|---|
| **escopo** | uma sessão (`ana:caso6`) | todas as sessões da pessoa (`ana`) | nenhuma pessoa |
| **propósito** | **retomar** a pausa de aprovação do estoque | **lembrar** que ontem foi sugerida a *Summer Squash Pasta* e que a pessoa é alérgica a amendoim | **consultar** a meta de sódio da OMS, a proteína do ovo, a receita de abobrinha |
| **forma** | o estado inteiro do grafo, a cada passo | linha de perfil; linha de histórico com vetor | fichas da OMS, TBCA, receitas |
| **leitura** | uma vez, na retomada (`Command(resume=...)`) | todo turno: perfil por chave, histórico por similaridade | quando o chef ou o consultor pedem |
| **quem escreve** | o LangGraph | o código (`registrar`, `gravar_*`), após o portão ou a pessoa | ninguém em execução: curadoria em [baixar_dados.py](../scripts/baixar_dados.py) |

**O que a recuperação por relevância traz que a serialização não traria:** a serialização de todas as execuções da Ana seria arquivo morto, centenas de KB de resultados de ferramenta. O que o chef recebe são 3 linhas: as recomendações passadas **mais parecidas com o pedido atual**, para não repetir. **O que ela deixa para trás:** o motivo de cada reprovação, as buscas que não deram em nada e a conversa. Se a pessoa disser "aquela de ontem que você recusou", o sistema não sabe do que ela fala.

## 5.2 As três memórias

| Tipo | O que guarda | Estrutura | Onde no código |
|---|---|---|---|
| **episódica** | receita sugerida, data, kcal, pedido original | tabela `historico` + **vetor `bge-m3` na mesma linha**; lida por similaridade ao pedido, sempre filtrada por `usuario_id`, com decaimento | [db.py](../src/db.py) `registrar_recomendacao`, [memoria.py](../src/memoria.py) `lembrar` |
| **semântica** | objetivo, alergias, restrições, preferências, equipamentos | chave-valor (`perfil`, chave `usuario_id`), lido inteiro a cada turno | [db.py](../src/db.py) `perfil` |
| **procedural** | regras curadas ("acompanhamento não é refeição") | texto injetado no prompt do chef | [regras_procedurais.md](../src/prompts/regras_procedurais.md) |

**Por que o vetor episódico mora na linha SQL, e não num índice separado:** a remoção fica pontual. A v1 previa um índice vetorial com *tombstone* e reconstrução ([memoria-v1.md](memoria-v1.md) §2.3). Com o vetor na linha, `DELETE` apaga o vetor, e a ressalva da reconstrução deixa de existir. O custo é a busca linear, que é irrelevante para dezenas de linhas por pessoa.

**O perfil foi enxugado:** idade, altura, peso e rotina saíram do perfil, porque nenhuma parte do sistema os usa.

## 5.3 A política de escrita

| Memória | Política | Volume por execução (medido) |
|---|---|---|
| semântica (perfil) | **modelo extrai, código valida, humano aprova o perigoso.** `extrair_perfil` devolve (campo, operação, valor) num schema; o código aceita só campos de uma lista fechada; remover alergia pausa para a pessoa | 0 ou 1 linha alterada + 1 registro no livro de escritas |
| episódica (histórico) | **código, por regra:** só a recomendação que passou no portão e no avaliador | 1 linha de ~85 bytes de texto + **4.096 bytes de vetor** (1024 × float32) |
| procedural | **humano corrige.** O agente não escreve aqui. As duas regras atuais foram redigidas a partir da inspeção do acervo e **aprovadas por Pedro Henrique Gomes em 20/10/2026**; o aprovador e a data ficam registrados ao lado de cada regra, no arquivo versionado (fecha a lacuna L09 do model card) | 0 por execução |
| estoque (não é memória do agente, mas é escrita) | **humano aprova**, depois de o modelo extrair e o código casar com o catálogo | N linhas + 1 registro no livro |

**A escrita de memória é escrita.** Todas passam por `escrever_uma_vez` ([db.py](../src/db.py)), com a chave derivada do **conteúdo**:

| Escrita | Chave = sha256 de | `ja_existia` demonstrado |
|---|---|---|
| estoque | usuário + itens normalizados + dia | caso 6c: a mesma aprovação reapresentada no ponto da pausa → `ja_existia: true, gravados: 0` (log `caso6c_aprovacao_repetida`) |
| perfil | usuário + campo + operação + valor | [db.py](../src/db.py) `atualizar_perfil` |
| recomendação | usuário + dia + receita | E08 pergunta 9: "Essa recomendação já estava registrada hoje" (a mesma receita do caso 2, no mesmo dia) |

**O preço do dia na chave:** a mesma compra feita duas vezes no mesmo dia é tratada como repetição. Aceitamos isso: é mais provável ser a mesma nota reenviada do que duas compras idênticas.

## 5.4 Como o agente perde a memória

| Causa | Escolhida? | O que faz no sistema | Evidência |
|---|---|---|---|
| **contradição** | **sim**, na base da OMS | na leitura, entre trechos da mesma `familia`, só a maior `data_publicacao` sobrevive; o descarte vai para `descartes_oms` e para o log | [E04](evidencias/E04-revogado.txt) |
| **decaimento** | **sim**, na episódica | histórico com mais de **90 dias** tem peso **× 0,5** na similaridade: é **rebaixado, não apagado**. 90 dias porque o estoque doméstico se renova em semanas, mas preferência leva meses para mudar ([memoria-v1.md](memoria-v1.md) §2.2) | [test_memoria.py](../tests/test_memoria.py) `test_decaimento_rebaixa_e_nao_apaga` (sem execução com dado de 90 dias: os usuários fictícios não têm histórico tão antigo) |
| **remoção** | **sim**, para toda estrutura | `python -m src.remover <usuario_id>` | [E05](evidencias/E05-remocao.txt) |

**As três razões, no case:**
- **privacidade:** alergia é dado de saúde, e a pessoa pode pedir para sair;
- **custo:** o checkpoint cresce ~150 KB por turno, e esta é a pressão real de custo do sistema. Hoje **não há** expurgo automático do checkpoint, e isso é lacuna;
- **recuperação de incidente:** uma regra procedural envenenada é texto num arquivo versionado. Um `git revert` a remove, e ela não volta.

### A cobertura da remoção

| Estrutura | Ação | Escapa com frequência? |
|---|---|---|
| `perfil`, `estoque`, `historico` (com o vetor na linha), `escritas` | `DELETE` + `VACUUM` + checkpoint do WAL | — |
| **checkpoints** do LangGraph (tabelas `checkpoints` e `writes`, `thread_id LIKE 'usuario:%'`) | `DELETE` + `VACUUM` + `wal_checkpoint(TRUNCATE)` | **sim**: guarda o perfil lido em cada passo |
| **logs** (`logs/*.jsonl`) | apaga o arquivo do titular; em outro arquivo, troca o id por `[removido]` | **sim**: o log registra argumentos e resultados |
| **memória procedural** | **não** editada por código: a varredura acusa, e um humano reescreve | **sim** |
| `logs/remocoes.jsonl` | o registro da remoção guarda o **hash** do titular, não o id | — |
| índices de receitas e OMS | sem dado de pessoa; entram na varredura para provar isso | — |

**A verificação é independente da remoção:** `varrer()` procura o identificador nos **bytes** dos arquivos SQLite (inclusive no `-wal`), no texto dos logs, nas regras e no corpus. Ela não pergunta à remoção o que foi apagado. O fluxo do E05:
1. grava o titular (perfil, alergia e estoque);
2. o sistema recomenda usando esses dados;
3. remove;
4. a varredura dá **zero em todas as estruturas**;
5. a mesma pergunta recebe "Ainda não conheço você".

**O que a verificação pegou:** na primeira versão, a remoção fazia `DELETE` e `VACUUM`. A varredura ainda achou o id do titular em **1.469 bytes** do banco de checkpoints, porque o SQLite em modo WAL guardava as páginas antigas no arquivo `-wal`, e o `VACUUM` não limpa esse arquivo. A correção foi `PRAGMA wal_checkpoint(TRUNCATE)` antes e depois do `VACUUM` ([remover.py](../src/remover.py) `_compactar`). Sem a varredura por bytes, a remoção teria sido declarada concluída com o dado ainda no disco.

**A reconstrução de índice não é necessária:** nenhum índice tem dado de pessoa, e o vetor episódico sai com a linha. Por isso a remoção serve também à recuperação de incidente.

## 5.5 A conversa, e o que sobra dela

**O que identifica uma conversa.** `thread_id = "{usuario}:{sessao}"`, montado em [main.py](../src/main.py) a partir de `--usuario` e `--sessao`, e **nunca** a partir do texto. Mesma sessão, mesma conversa: a triagem vê os últimos turnos, e a pausa pendente é retomada. Sessão nova começa com conversa vazia, mas com a **mesma** memória de longo prazo, porque perfil, estoque e histórico são chaveados por `usuario`.

**Duas conversas da mesma pessoa ao mesmo tempo** são dois `thread_id`, com checkpoints separados e o mesmo estoque. Se as duas aprovarem a mesma lista no mesmo dia, a chave de idempotência impede a soma dupla. **Limitação:** dois processos na **mesma** sessão ao mesmo tempo não são tratados, e o último checkpoint vence.

**Onde o checkpoint é gravado.** Em arquivo: `SqliteSaver` em `dados/checkpoints.sqlite`. A conversa e a **pausa pendente sobrevivem** ao fim do processo. Demonstrado com dois processos separados: `python -m src.main --usuario ana --sessao cli "chegaram 2 kg de batata e 1 kg de cenoura"` pausou, e um segundo `python -m src.main --usuario ana --sessao cli --aprovar` gravou (logs `humano_cli_1_pausa` e `humano_cli_2_aprovar`). Não há expurgo automático, e isso é lacuna ([§5.4](#54-como-o-agente-perde-a-memória)).

**O que acontece quando a janela enche.** A política é **truncar o início** da conversa: o reducer `janela_conversa` mantém os **6 últimos turnos** ([estado.py](../src/estado.py), `test_janela_da_conversa_corta_o_inicio`). O que se perde: o que a pessoa disse há mais de 6 turnos ("lembra que eu disse que hoje somos três?"). O que é fato durável, alergia por exemplo, não depende da conversa: está no perfil, lido a cada turno. Os resultados de ferramenta (`agente_msgs`) não atravessam turnos: são zerados no `inicio`.

**O que passa da conversa para o longo prazo.** **Só o que virou escrita aprovada:** a recomendação registrada (episódica), o perfil alterado (semântica) e o estoque aprovado. O texto da conversa **não** vira memória de longo prazo. Se a pessoa disser no meio da conversa "não gosto de coentro" sem pedir para registrar, isso morre com a janela. Para a Parte 3, fica a pergunta de se a triagem deve propor gravar preferências ditas de passagem.
