# Arquitetura — Agente Nutricionista Pessoal (v2)

**Versão do sistema:** commit `fffe38f` · **Data:** 20/10/2026 · substitui [arquitetura-v1.md](arquitetura-v1.md) (o histórico das decisões está em [case.md §0.5](case.md#05-o-que-mudou-de-ideia-desde-a-v1-e-por-quê))

O grafo detalhado (padrões, quem decide cada aresta, o que o framework não deu) está em [grafo.md](grafo.md). Este documento é a visão do sistema inteiro.

## 3.1 O diagrama

Legenda: `[M]` o **modelo** decide · `[C]` o **código** decide · `[M+C]` o modelo propõe e o código confere · `⏸` **para e espera uma pessoa** · `■` término.

```text
 texto livre da pessoa  +  usuario_id e sessao (da linha de comando, nunca do modelo)
        |
        v
 [C] inicio ── zera os campos do turno, carimba execucao_id e inicio_ts
        |
        +-----------------------+-----------------------+          (paralelo, junção em triagem)
        v                       v                       v
 [C] carregar_perfil     [C] carregar_estoque    [C] carregar_historico
     SQL perfil              SQL estoque             SQL historico + vetor (episódica, decai 90 dias)
        +-----------------------+-----------------------+
        v
 [M] triagem ── Literal: recomendar | estoque | perfil | pergunta | fora_escopo + acao_futura
        |
        |  [C] rota_triagem: acao_futura e rota != pergunta  -> nao_agir
        +---------------+-------------------+------------------+------------------+
        |               |                   |                  |                  |
        v               v                   v                  v                  v
  RECOMENDAR        ESTOQUE              PERFIL             PERGUNTA        recusar / nao_agir
        |               |                   |                  |                  |
 [C] checar_pedido  [M] extrair_itens  [M] extrair_perfil  [M] consultor <-+    ■ recusa_fora_escopo
   perfil? estoque?     |                   |                 |  (laço)    |    ■ sem_acao
   divergência?     [C] casar_catalogo      |                 v            |
   | ■ pergunta_ao_    leite? -> ambíguo    |  [C] ferramentas_consultor --+
   |   usuario          |                   |       buscar_diretrizes (índice OMS)
   v                    v                   |       consultar_alimento (TBCA)
 [M] chef <--------+  ⏸ confirmar_estoque   |       + portão de NÚMEROS [C]
   (laço, ≤5      |    aprovar | editar |   |                 |
    passos por    |    rejeitar | prazo     |                 v
    rodada)       |     |      ■ rejeitado  |   [M+C] verificar_resposta
   |              |     |      ■ expirada   |      trecho citado existe na fonte?
   v              |     v                   |                 |
 [C] ferramentas_chef  [C] gravar_estoque   +--> remover alergia?
   buscar_receitas     idempotente por      |     sim: ⏸ confirmar_perfil
   (índice receitas,   conteúdo+dia         |     não: [C] gravar_perfil
    SÓ viáveis)        (ja_existia)         |
   detalhar_receita                         |
   |  propor_receita | declarar_sem_opcao   |
   v                  ■ recusa_sem_base     |
 [C] conferir_proposta ── alérgeno? restrição? faltando? -> reprova (volta ao chef)
   |                                                     ■ teto_rodadas (3)
   v
 [M+C] avaliador ── nutrição TBCA [C] + 1 trecho OMS (busca fixa) [C] + veredito [M]
   |  reprovado -> volta ao chef
   v
 [C] registrar ── histórico (episódica), chave usuário+dia+receita
        |
        v
 [C] finalizar ── monta Saida (Pydantic): resultado, fontes, suficiência, escolhas, término
        |
        v
       FIM     ■ concluido  · em qualquer nó: ■ teto_tempo  ■ teto_tokens  ■ teto_passos
                                              ■ laco_detectado  ■ erro_fatal
```

## 3.2 As seis perguntas

### As ferramentas

O modelo só tem ferramentas de **leitura**. Toda escrita é um nó de código depois de validação ou de aprovação humana: não existe ferramenta que escreva no banco, e o modelo não tem como pedir uma.

| Ferramenta | Quem usa | O que faz | L/E | Reversível |
|---|---|---|---|---|
| `buscar_receitas(consulta)` | chef | busca vetorial; expande o português pelo catálogo; devolve **só** receitas viáveis para esta pessoa | L | — |
| `detalhar_receita(receita_id)` | chef | ingredientes e preparo; id inexistente → erro recuperável | L | — |
| `propor_receita` / `declarar_sem_opcao` | chef | ferramentas de término do laço | — | — |
| `buscar_diretrizes(consulta)` | consultor | busca vetorial nas fichas da OMS, com desempate por data | L | — |
| `consultar_alimento(nome)` | consultor | composição por 100 g na TBCA; fora do recorte → erro recuperável | L | — |
| `responder` | consultor | término do laço | — | — |
| *nó* `gravar_estoque` | código, após ⏸ | soma ao estoque; idempotente | E | sim (a pessoa edita) |
| *nó* `gravar_perfil` | código (⏸ se remover alergia) | campo de uma lista fechada; idempotente | E | sim |
| *nó* `registrar` | código, após o avaliador | histórico; idempotente | E | sim |

O `usuario_id` nunca é argumento de ferramenta: o código o injeta a partir da sessão ([ferramentas.py](../src/ferramentas.py), `Ctx`).

### O laço

Há dois laços de agente: o chef (recomendação) e o consultor (pergunta).

**O laço do chef**, a cada volta:
1. O modelo recebe o histórico da busca e escolhe: buscar de novo, detalhar, propor ou declarar que não há opção.
2. O código executa a ferramenta.

A volta seguinte existe quando a ferramenta não era de término, ou quando uma proposta foi **reprovada**, pelo portão em código ou pelo avaliador. Nesse caso, a reprovação entra como mensagem no laço ([grafo.py](../src/grafo.py) `_reprovar`).

**O laço do consultor** termina em `responder`, e depois a resposta passa por dois portões: números e trecho citado.

Quando o modelo responde em texto em vez de chamar a ferramenta final (o qwen 7B faz isso), uma chamada com saída estruturada converte a decisão dele na ferramenta final (`_passo_agente`).

### O estado

Objeto explícito, com 34 campos. A tabela completa está em [§7.1 abaixo](#71-os-campos-do-estado-e-quem-mexe-em-cada-um). A lista de mensagens do agente (`agente_msgs`) é só o rascunho do turno; decisão, contador e identificador **não** moram nela.

### O orçamento

| Teto | Valor | Onde é aplicado |
|---|---|---|
| passos do agente por rodada | 5 | `_passo_agente` → `teto_passos` |
| rodadas de reprovação | 3 | `_reprovar` → `teto_rodadas` |
| tokens por chamada (janela) | 6.000 | `estouro` → `teto_tokens`; o Modelfile fixa `num_ctx=8192` ([E02](evidencias/E02-janela.txt)) |
| tokens por execução | 40.000 | `estouro` → `teto_tokens` |
| tempo de parede | 120 s | `estouro` → `teto_tempo` |
| passos do grafo | 40 | `recursion_limit`, declarado em [config.py](../src/config.py) |
| prazo da aprovação humana | 24 h | `expira_em`, gravado antes da pausa |

Medido: uma recomendação usa 4 chamadas, ~4.600 tokens e 4–7 s. A maior janela observada foi de 1.712 tokens ([E06](evidencias/E06-frase.txt), logs).

### O término

Catorze motivos, no campo `termino` de toda saída ([esquemas.py](../src/esquemas.py) `Termino`):

| Motivo | Quando |
|---|---|
| `concluido` | a ação foi feita, ou a resposta foi verificada |
| `pergunta_ao_usuario` | falta perfil ou estoque |
| `recusa_fora_escopo` | diagnóstico, dose, assunto que não é comida |
| `recusa_sem_base` | nenhuma receita serve, ou a resposta não tem fonte |
| `sem_acao` | a pessoa falou do futuro; nada a registrar |
| `aguardando_humano` | ⏸ pausa ativa |
| `rejeitado_pelo_humano` | a pessoa rejeitou, ou mandou uma edição inválida |
| `aprovacao_expirada` | o prazo venceu; nada foi gravado |
| `teto_passos` · `teto_rodadas` · `teto_tokens` · `teto_tempo` | o orçamento acabou |
| `laco_detectado` | a mesma chamada (nome + argumentos) se repetiu no turno |
| `erro_fatal` | o modelo está fora do ar, ou devolveu JSON inválido duas vezes |

### O humano

| Onde | Quem é chamado | O que acontece se não responder |
|---|---|---|
| ⏸ `confirmar_estoque`: antes de somar itens ao estoque | **a própria pessoa**, dona do estoque: ela sabe se o "leite" é integral | em 24 h, `aprovacao_expirada`; **nada é gravado** |
| ⏸ `confirmar_perfil`: antes de remover uma alergia | **a própria pessoa** | idem |
| memória procedural ([regras_procedurais.md](../src/prompts/regras_procedurais.md)) | **um integrante do grupo**, na curadoria | a regra não entra |

A recomendação **não** pausa: é uma sugestão reversível, e o filtro de alergia que a torna segura é código, não pessoa. Detalhes em [humano.md](humano.md).

## 3.3 A defesa do nível de autonomia

**Nível: roteador na entrada + dois agentes pequenos com laço limitado + workflow nas escritas.**

| Parte | Nível | Por que o de baixo não servia |
|---|---|---|
| triagem | roteador (modelo) | as cinco intenções chegam em texto livre ("NF: ARROZ 5KG", "virei vegetariano"). Uma regra por palavra-chave errava "comprei uma air fryer" (perfil, não estoque) |
| estoque e perfil | workflow (extrair → casar → aprovar → gravar) | o caminho é sempre o mesmo; não há decisão em tempo de execução |
| chef | **agente** (laço de até 5 passos) | **a decisão que só o modelo toma:** *que consulta fazer ao acervo, e qual das receitas viáveis atende o pedido*. "Tenho abobrinha, me sugere algo" → `buscar_receitas("abobrinha")` → escolhe *Summer Squash and Basil Pasta* entre as viáveis (log `caso2`). Um workflow com busca fixa pela lista do estoque não sabe que o pedido era abobrinha |
| consultor | **agente** (laço de até 5 passos) | decide **se** busca na OMS, na TBCA ou nas duas. No caso 3 ("tofu e ovo"), chamou `consultar_alimento` duas vezes, uma por alimento, e nenhuma vez a OMS |
| avaliador | avaliador-otimizador | a reprovação devolve um motivo que muda a próxima proposta |

No diagrama, a decisão está na seta `[M] chef → [C] ferramentas_chef` (qual ferramenta, com que consulta) e na seta `propor_receita` (qual receita).

**O que deixou de ser do modelo nesta versão:**
- a viabilidade da receita: a busca já filtra;
- a alergia: dois controles em código;
- a escrita: nenhuma ferramenta escreve;
- a rota para o futuro: decidida pelo campo estável `acao_futura`;
- a justificativa com promessa de saúde: substituída em código.

Cada um desses saiu do modelo depois de um log mostrar que ele errava (ver [prompts.md](prompts.md)).

## 6.1 / 6.4 O grafo desenhado e a conferência contra o código

O desenho acima tem 24 nós de trabalho. A conferência importa **o mesmo objeto** que `src/main.py` executa (`src.grafo.obter_grafo`):

```text
$ python conferir_grafo.py
NÓS (26):
  __start__, inicio, carregar_perfil, carregar_estoque, carregar_historico, triagem, recusar, nao_agir,
  checar_pedido, chef, ferramentas_chef, conferir_proposta, avaliador, registrar, consultor,
  ferramentas_consultor, verificar_resposta, extrair_itens, casar_catalogo, confirmar_estoque,
  gravar_estoque, extrair_perfil, confirmar_perfil, gravar_perfil, finalizar, __end__

ARESTAS (49; [cond] = condicional, com o rótulo da rota):
  __start__ -> inicio
  avaliador -> chef  [cond: chef]
  avaliador -> finalizar  [cond: fim]
  avaliador -> registrar  [cond: registrar]
  carregar_estoque -> triagem
  carregar_historico -> triagem
  carregar_perfil -> triagem
  casar_catalogo -> confirmar_estoque  [cond: confirmar]
  casar_catalogo -> finalizar  [cond: fim]
  checar_pedido -> chef  [cond: chef]
  checar_pedido -> finalizar  [cond: fim]
  chef -> ferramentas_chef  [cond: ferramentas]
  chef -> finalizar  [cond: fim]
  conferir_proposta -> avaliador  [cond: avaliador]
  conferir_proposta -> chef  [cond: chef]
  conferir_proposta -> finalizar  [cond: fim]
  confirmar_estoque -> finalizar  [cond: fim]
  confirmar_estoque -> gravar_estoque  [cond: gravar]
  confirmar_perfil -> finalizar  [cond: fim]
  confirmar_perfil -> gravar_perfil  [cond: gravar]
  consultor -> ferramentas_consultor  [cond: ferramentas]
  consultor -> finalizar  [cond: fim]
  extrair_itens -> casar_catalogo
  extrair_perfil -> confirmar_perfil  [cond: confirmar]
  extrair_perfil -> finalizar  [cond: fim]
  extrair_perfil -> gravar_perfil  [cond: gravar]
  ferramentas_chef -> chef  [cond: chef]
  ferramentas_chef -> conferir_proposta  [cond: conferir]
  ferramentas_chef -> finalizar  [cond: fim]
  ferramentas_consultor -> consultor  [cond: consultor]
  ferramentas_consultor -> finalizar  [cond: fim]
  ferramentas_consultor -> verificar_resposta  [cond: verificar]
  gravar_estoque -> finalizar
  gravar_perfil -> finalizar
  inicio -> carregar_estoque
  inicio -> carregar_historico
  inicio -> carregar_perfil
  nao_agir -> finalizar
  recusar -> finalizar
  registrar -> finalizar
  triagem -> checar_pedido  [cond: recomendar]
  triagem -> consultor  [cond: pergunta]
  triagem -> extrair_itens  [cond: estoque]
  triagem -> extrair_perfil  [cond: perfil]
  triagem -> finalizar  [cond: fim]
  triagem -> nao_agir  [cond: nao_agir]
  triagem -> recusar  [cond: fora_escopo]
  verificar_resposta -> finalizar
  finalizar -> __end__
```

**Conferência.** Os 24 nós do desenho estão no código, e nenhum nó do código falta no desenho. Duas divergências aparecem, e nos dois casos vale o código:
1. **As setas `→ finalizar [cond: fim]` não estão no desenho.** Elas existem em todo nó que pode estourar o orçamento. O desenho as resume na última linha ("em qualquer nó: ■ teto_…").
2. **A pausa não é uma aresta.** `confirmar_estoque` não tem seta para "esperar": a pausa é um `interrupt` dentro do nó. Por isso ela só aparece no desenho, com `⏸`.

## 7.1 Os campos do estado, e quem mexe em cada um

Declarado em [estado.py](../src/estado.py). "Reducer" vazio significa **último valor vence**.

| Campo | Tipo | Reducer | Quem escreve | Quem lê | De onde veio |
|---|---|---|---|---|---|
| `entrada` | str | — | main (entrada do grafo) | triagem, chef, consultor, extrações, registrar | texto da pessoa |
| `usuario_id`, `thread_id` | str | — | main | todos os nós de dados | linha de comando (`--usuario`, `--sessao`), **nunca o modelo** |
| `execucao_id`, `inicio_ts` | str, float | — | inicio | finalizar, `estouro` | gerado |
| `perfil` | dict | — | carregar_perfil | checar_pedido, chef, conferir, avaliador | SQL |
| `estoque` | list | — | carregar_estoque | checar_pedido, `ctx_de` | SQL |
| `recentes` | list | — | carregar_historico | chef, `ctx_de` | SQL + vetor (episódica) |
| **`fontes`** | list | **`por_turno`** | **3 carregadores em paralelo**, avaliador, registrar, consultor, gravar_* | finalizar | vários |
| `triagem` | dict | — | triagem | rotas, checar_pedido, chef, finalizar | modelo |
| `disponiveis_extra` | list | — | checar_pedido | `ctx_de` | o que a pessoa disse ter |
| `escolhas` | list | `por_turno` | checar_pedido, conferir, avaliador, verificar, ferramentas_chef | finalizar | código e modelo |
| `agente_msgs` | list | `por_turno` | chef/consultor (modelo) e ferramentas_* (resultados) | os mesmos, `_laco` | rascunho do turno |
| `passos_agente` | int | — | `_passo_agente`, `_reprovar` (zera) | `_passo_agente` | contador |
| `recuperacoes` | list | `por_turno` | ferramentas_*, avaliador | finalizar, verificar, log | registro de cada busca |
| `descartes_oms` | list | `por_turno` | ferramentas_consultor, avaliador | log | desempate por data |
| `rejeitadas` | list | `por_turno` | `_reprovar` | `ctx_de` (sai das buscas) | ids reprovados no turno |
| `proposta` | dict | — | ferramentas_chef (cria), `_reprovar` (zera) | conferir, avaliador, registrar, finalizar | modelo |
| `nutricao` | dict | — | avaliador | registrar, finalizar | TBCA (código) |
| `veredito` | dict | — | conferir_proposta, avaliador | rotas, chef | código ou modelo |
| `rodadas` | int | — | `_reprovar` | `_reprovar` | contador |
| `resposta_consultor` | dict | — | ferramentas_consultor, verificar_resposta | finalizar | modelo + portões |
| `itens_ditos` | list | — | extrair_itens | casar_catalogo | modelo |
| `itens_propostos`, `pendentes` | list | — | casar_catalogo | confirmar_estoque | código |
| `atualizacao_perfil` | dict | — | extrair_perfil | rota_perfil, confirmar/gravar_perfil | modelo |
| `expira_em` | float | — | casar_catalogo, extrair_perfil | confirmar_* | gravado **antes** da pausa |
| `decisao_humana` | dict | — | confirmar_* | gravar_*, finalizar | a pessoa |
| `efeito` | dict | — | gravar_*, registrar | finalizar | banco (`ja_existia`) |
| `termino`, `erro` | str | — | qualquer nó; `no()` em erro fatal | todas as rotas, finalizar | — |
| `saida` | dict | — | finalizar | main | contrato |
| `uso` | dict | `somar_uso` | todo nó que chama o modelo | `estouro`, saída | resposta do provedor |
| `conversa` | list | `janela_conversa` | finalizar | triagem (próximo turno) | texto conversacional |

**O campo escrito por mais nós é `fontes`**, e os três primeiros escrevem no **mesmo passo** (ramos paralelos). Sem reducer, isso é uma corrida. O que acontece de fato está em [grafo.md §7.2](grafo.md#72-os-reducers-e-o-que-acontece-sem-eles).

`proposta` e `veredito` também são escritos por mais de um nó, mas **nunca no mesmo passo**: o grafo é sequencial depois da junção. "Último valor vence" é, ali, a semântica desejada: a reprovação substitui a proposta.
