# Memória — Agente Nutricionista Pessoal

Este documento decide como o agente **lembra** e como o agente **esquece**.
As duas decisões são de projeto, não de implementação, e precedem qualquer
código de persistência sobre o fluxo já definido em
[arquitetura-v1.md](arquitetura-v1.md) e sobre as fontes descritas em
[base-de-conhecimento-v1.md](base-de-conhecimento-v1.md).

> **O que o agente não guarda, e o que ele perde quando perde** — resposta ao
> final, em [§3](#3-o-que-o-agente-não-guarda).

---

## 1. Como o agente lembra

### 1.1 Os dois níveis, no domínio do case

| | curto prazo | longo prazo |
|---|---|---|
| **o que é** | o pedido corrente do usuário, do momento em que ele escreve ou sobe uma foto até a etapa 8 (RETORNO) | o que atravessa pedidos diferentes, do mesmo usuário ou de usuários diferentes |
| **conteúdo** | system prompt do nutricionista; o pedido em si ("o que eu como hoje?"); a trajetória entre AGENTE-ESTOQUE / AGENTE-CHEF / AVALIADOR-NUTRICIONISTA (incluindo o motivo de cada reprovação); estoque e perfil consultados nesta execução; receita candidata corrente | episódica (histórico de recomendações), semântica (perfil do usuário), procedural (regras de preferência aprendidas) |
| **persistido como** | **checkpoint** — um registro por execução, identificado por um `execucao_id` | tabela SQL (perfil, estoque, histórico), índice vetorial (histórico por similaridade), texto injetado no system prompt (regras) |
| **lido** | uma vez, ao retomar a etapa em que a execução parou | por relevância, a cada volta do laço (RECEITA e AVALIAÇÃO consultam de novo a cada rodada) |
| **acesso** | por `execucao_id` | por `usuario_id` (perfil, estoque, histórico) ou por similaridade (histórico, quando a busca é "algo parecido com o que recomendei antes") |
| **ciclo de vida** | morre quando a etapa 8 devolve a resposta ao usuário, ou é retido por um prazo curto só para depuração | acumula, sujeito às políticas da [Decisão 2](#2-como-o-agente-esquece) |

O checkpoint precisa responder às três perguntas do exercício, e a resposta é
específica ao fluxo desta arquitetura:

- **Retomada sem repetir efeito colateral?** Sim, porque as duas escritas do
  fluxo (`estoque.atualizar` e `recomendacao.registrar`) já são upsert
  idempotente (usuário+item e usuário+dia, respectivamente — ver
  [arquitetura-v1.md §2](arquitetura-v1.md)). O checkpoint ainda assim grava
  o `recomendacao_id` assim que REGISTRO responde, porque a v1 já antecipa
  uma extensão fora de escopo — descontar o estoque quando o usuário
  confirmar "cozinhei isso" — e essa confirmação futura vai precisar
  correlacionar com uma recomendação específica, não com a execução que a
  gerou.
- **Aprovação humana chegando horas depois?** Esta v1 não tem etapa de
  aprovação humana no fluxo (RETORNO já entrega a receita). Mas a mesma
  forma de correlação serve para a confirmação de consumo citada acima: ela
  chega como uma nova mensagem, em outro processo, e precisa encontrar o
  `recomendacao_id` correto — não o `execucao_id` da execução original, que
  já morreu.
- **Estado defeituoso reproduzível?** O checkpoint grava a entrada bruta
  (texto ou referência à imagem), o estoque e o perfil consultados nesta
  execução (não um ponteiro para o estado atual, que já pode ter mudado), a
  receita em cada rodada e o veredito com motivo de cada avaliação. Isso
  permite recarregar exatamente o estado que gerou um bug, mesmo que o
  estoque real do usuário já tenha sido alterado depois.

Campos do checkpoint: `execucao_id`, `usuario_id`, `etapa_atual`, `entrada_bruta`,
`estoque_snapshot`, `perfil_snapshot`, `receita_candidata`, `contador_passos_chef`,
`contador_rodadas_avaliacao`, `veredito_ultima_rodada` (com motivo),
`recomendacao_id` (quando REGISTRO já ocorreu).

### 1.2 O orçamento da janela

`MAX_TOKENS_POR_PEDIDO = 6000` já está declarado em
[arquitetura-v1.md](arquitetura-v1.md). Esse teto se reparte entre cinco
fontes:

| Fonte | Teto | Por quê |
|---|---:|---|
| system prompt | 150 | fixo, uma frase, nunca varia dentro de uma execução |
| objetivo (pedido do usuário) | 300 | texto curto por natureza; a triagem já resume a intenção |
| trajetória (chef + avaliador) | 2500 | maior fonte — cresce com até 5 passos do chef e 3 rodadas do avaliador, cada uma com motivo de reprovação |
| trechos recuperados (receitas candidatas + diretrizes OMS) | 2000 | busca vetorial de receitas e, na avaliação, trechos normativos da OMS |
| memória de longo prazo | 1050 | perfil resumido + fatos de histórico mais relevantes |

**Ordem de descarte quando o total estoura**, do mais barato de recompor ao
mais caro:

1. **Trechos recuperados** — reduz o *top-k* de receitas candidatas (de 5
   para 3, depois para 1) e de trechos da OMS. É barato: uma nova busca
   reconstrói o que falta.
2. **Memória de longo prazo** — reduz para os *k* fatos de histórico mais
   relevantes ao pedido atual; o perfil (poucos campos, chave-valor) nunca é
   cortado, só o histórico.
3. **Trajetória** — mas não se trunca o fim, que é onde está o motivo mais
   recente de reprovação e é exatamente o que o próximo passo do chef
   precisa. Em vez disso, resumem-se as rodadas mais antigas (mantendo
   pedido original e motivo mais recente intactos) até caber.
4. **System prompt e objetivo nunca são cortados** — são o contrato mínimo
   da execução; cortá-los muda o que o agente é, não só o que ele sabe.

### 1.3 As três memórias de longo prazo, no domínio do case

| Tipo | O que guarda no case | Estrutura | Como é recuperada |
|---|---|---|---|
| **episódica** | histórico de recomendações: receita sugerida, veredito, kcal/macros, data, e se o pedido seguinte do mesmo usuário indicou rejeição implícita (pediu de novo, mudou de assunto) | índice vetorial (embedding do par pedido+receita), com `usuario_id` e `data` como metadado | por similaridade ao pedido atual, sempre filtrado por `usuario_id` — usada para não repetir receita recente e para inferir preferência não declarada no perfil |
| **semântica** | perfil do usuário: objetivo, restrições, alergias, preferências, equipamentos disponíveis — já existe como a tabela `perfil` de [base-de-conhecimento-v1.md §2](base-de-conhecimento-v1.md) | chave-valor (SQL), chave = `usuario_id` | por chave, sempre lida inteira no início de RECEITA e AVALIAÇÃO — nunca por similaridade, porque é exata e barata |
| **procedural** | regras de preferência aprendidas a partir de padrões repetidos (ex.: "para o padrão de usuários com objetivo emagrecimento e estoque com menos de 3 itens, priorizar receitas de 1 porção com poucos ingredientes"), curadas por humano antes de valer | texto fixo, injetado no system prompt do chef e do avaliador | sempre carregada por inteiro — é um conjunto pequeno de regras vigentes, não um índice de busca |

A escolha de estrutura segue o padrão de acesso, não a preferência: o perfil
é resolvido por chave porque é exato e não precisa de aproximação; o
histórico é resolvido por similaridade porque a pergunta ("algo parecido com
o que já recomendei") é semântica por natureza.

### 1.4 Quem escreve, e o volume por execução

| Memória | Quem escreve | Volume por execução |
|---|---|---|
| semântica (perfil) | **código extrai por regra determinística** — a TRIAGEM já classifica a rota "perfil" e grava direto, sem LLM (ver [arquitetura-v1.md §3](arquitetura-v1.md)) | 0 ou 1 atualização, só quando o pedido é dessa rota (~10% dos pedidos, por [arquitetura-v1.md §1](arquitetura-v1.md)) |
| episódica (histórico) | **código**, ao final de REGISTRO, sempre que uma recomendação é aprovada | exatamente 1 registro por execução aprovada; campos fixos e pequenos |
| procedural (regras) | **humano corrige** — o avaliador pode propor um padrão observado, mas a regra só entra no system prompt depois de curadoria humana, porque um erro ali se repete em toda execução futura, não só na que o gerou | raro; não é por execução, é por revisão periódica |

O agente nunca decide sozinho o que vai para a memória procedural — é a
única das três onde o custo de um erro é alto o bastante (afeta todas as
execuções futuras) para não delegar ao próprio agente.

---

## 2. Como o agente esquece

### 2.1 Contradição — o fato que mudou

**Exemplo real do domínio:** as diretrizes da OMS sobre redução de sódio
([base-de-conhecimento-v1.md §1](base-de-conhecimento-v1.md)) são revisadas
periodicamente. Se o índice vetorial contém o chunk de uma versão anterior
do material (ex.: um limite de sódio recomendado em uma publicação de 2012)
e o chunk da versão revisada (ex.: um limite diferente, em publicação mais
recente), os dois respondem igualmente bem, por similaridade, à pergunta
"qual o limite de sódio recomendado?" — a busca vetorial não enxerga qual
dos dois é mais novo, porque o embedding não representa anterioridade.

**Regra de desempate:** todo chunk da base OMS carrega `data_publicacao`
como metadado, extraído do próprio documento na ingestão. Na leitura, quando
dois ou mais chunks recuperados respondem à mesma pergunta normativa, vale
`max(data_publicacao)` — determinístico, sem chamada ao modelo.

**O descarte é registrado:** o log da chamada de AVALIAÇÃO grava qual chunk
foi descartado e por qual mais recente, mesmo que o resultado final não
mencione isso ao usuário. Sem esse registro, um agente que ignora o chunk
de 2012 é indistinguível, no log, de um que nunca o recuperou — e não dá
para saber se a regra de desempate está de fato funcionando.

### 2.2 Decaimento — o fato que envelheceu sem ser contradito

**Corte: 90 dias**, aplicado ao histórico de recomendações (episódica).
Justificativa: o estoque doméstico se renova em semanas — uma recomendação
de três meses atrás não reflete o padrão de compra atual do usuário — mas
90 dias ainda é curto o bastante para capturar um padrão de preferência
razoavelmente estável (ex.: "esse usuário sempre pede receita vegetariana
às segundas").

**Efeito: rebaixado, não removido.** O registro segue na tabela e no
índice, mas seu peso na ordenação de similaridade decai com a idade. Dois
motivos para não remover: (a) ele continua sendo sinal de preferência de
longo prazo, mesmo sem servir mais para "não repetir receita recente"; (b)
remover de fato exige a varredura de cobertura da [§2.3](#23-remoção--o-titular-solicitou),
que é mais cara que uma rotina de decaimento e não deveria rodar só porque
um registro envelheceu.

A memória procedural tem uma regra distinta: uma regra aprendida a partir de
um padrão que não é reforçado por novas execuções em 180 dias tem sua
prioridade rebaixada na curadoria seguinte — regras normativas (perfil,
diretrizes OMS) não decaem por tempo, só por revisão explícita (contradição).

### 2.3 Remoção — o titular solicitou

O requisito é de cobertura: o `usuario_id` precisa sair de **todas** as
estruturas em que caiu, não só das três memórias de longo prazo.

| Estrutura | Onde o identificador aparece | Ação |
|---|---|---|
| `perfil` (SQL) | chave primária | apagar a linha |
| `estoque` (SQL) | coluna `usuario` | apagar todas as linhas |
| histórico de recomendações (episódica) | metadado do chunk no índice vetorial + linha na tabela de registro | apagar a linha; remover ou marcar como tombstone o vetor — ver ressalva abaixo |
| **checkpoints** | `usuario_id`, `estoque_snapshot`, `perfil_snapshot` de execuções retidas para depuração | apagar todo checkpoint retido que referencie o usuário |
| **logs** | argumentos de `estoque.consultar`, `perfil.atualizar`, `recomendacao.registrar` etc. — todas essas ferramentas recebem `usuario_id` | expurgar ou redigir as entradas de log correspondentes |
| memória procedural | só se uma regra tiver sido indevidamente presa a um `usuario_id` específico em vez de generalizada (o que a curadoria humana da [§1.4](#14-quem-escreve-e-o-volume-por-execução) deveria ter impedido) | revisar e reescrever a regra sem a referência |

Checkpoint e log são os dois itens que a taxonomia de memória não cobre e
que mais facilmente escapam da lista.

**Verificação, independente da remoção:** grava-se um `usuario_id`
sintético, aciona-se a remoção, e então varre-se cada estrutura acima
procurando esse identificador — nas tabelas SQL por `SELECT`, no índice
vetorial por busca exata em metadado (não por similaridade textual, que
poderia simplesmente não trazer o vetor de volta sem ele ter sido de fato
removido), nos logs por busca textual, na memória procedural por revisão
humana do texto do system prompt. Uma remoção que se declara concluída sem
essa varredura não cumpre a obrigação.

**Ressalva sobre o índice vetorial:** se o mecanismo de banco vetorial usado
não suportar exclusão pontual eficiente — só *tombstone* seguido de
reconstrução do índice — isso precisa ser dito explicitamente: entre a
remoção lógica e a reconstrução, o vetor ainda pode influenciar buscas por
similaridade. Para privacidade e custo isso ainda serve; para atender uma
solicitação de remoção de titular, não serve até a reconstrução acontecer —
na prática, o dado é removido só na próxima janela de manutenção do índice.

### 2.4 O preço: o sistema deixou de ser reprodutível

O mesmo pedido ("o que eu como hoje?"), do mesmo usuário, pode gerar
respostas diferentes em execuções distintas — porque o perfil foi
atualizado, o estoque mudou, uma nova entrada no histórico passou a evitar a
receita de ontem, ou uma regra procedural nova entrou em vigor. Isso é
consequência deliberada da Decisão 1, não um defeito.

Isso importa porque um conjunto de avaliação (aula 11) rodado contra este
sistema em produção mede duas coisas de uma vez: se o modelo/prompt
melhorou, e se a memória mudou o contexto entre uma rodada de teste e
outra. Separar as duas exige congelar um snapshot fixo de perfil, estoque e
histórico para o conjunto de avaliação, em vez de deixá-lo ler o estado de
produção — que muda a cada execução real.

---

## 3. O que o agente não guarda

- **Dado sensível além do que o próprio usuário forneceu ao perfil.** A
  imagem bruta de uma foto de geladeira ou nota fiscal não é retida após
  `estoque.extrair_da_imagem` — só o resultado estruturado (itens
  reconhecidos) persiste; a imagem em si não tem por que sobreviver à
  execução. O sistema também não grava diagnóstico ou prescrição médica,
  porque o system prompt já recusa esse tipo de pedido antes de chegar a
  qualquer etapa de escrita.
- **Item extraído sem confirmação.** Itens que `estoque.extrair_da_imagem`
  devolve como `nao_reconhecidos` não viram fato de estoque — entram como
  memória de longo prazo só depois de casados com o catálogo, nunca antes.
- **O que é derivável.** Valores nutricionais (kcal, macros) calculados por
  `nutricional.calcular` não são persistidos como fato de longo prazo
  separado — são recalculados a partir da TBCA a cada vez que uma receita
  precisa deles. Guardar o valor calculado seria dívida: se a TBCA for
  atualizada, um valor guardado ficaria errado sem que nada avisasse.
- **A receita candidata de uma rodada reprovada.** Só a receita final
  aprovada vira registro episódico; rascunhos intermediários do chef morrem
  com o checkpoint da execução.

O que o sistema perde, quando perde por decaimento: histórico de
recomendações com mais de 90 dias deixa de pesar contra repetir uma receita
— o usuário pode ver a mesma sugestão de três meses atrás sem o sistema
"lembrar" que já a fez. O que ele perde por remoção é tudo: perfil, estoque,
histórico e qualquer regra procedural presa ao usuário deixam de existir, e
essa é a diferença deliberada entre as duas causas.
