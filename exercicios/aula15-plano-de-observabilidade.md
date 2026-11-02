# Plano de observabilidade — agente de trocas

Grupo: Daniel de Araujo Carvalho, Eduardo Dias Santos, Gabriel Brandão Vehchani de Freitas, Pedro Henrique Gomes · Data: 2026-11-01

**Números do case usados abaixo:** cerca de 500 conversas/dia, ou ~14.000 em 28 dias; orçamento de 6 passos; promessa de **60% resolvidas sem atendente** e **menos de 1% de trocas aprovadas fora da política**.

---

## 1. Perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| o negócio | Que fração das trocas o agente resolve sem atendente (aprovadas + recusadas, sobre o total)? A promessa é 60%. | manter o agente, ampliar para outras categorias ou retirá-lo; se a fração cair por excesso de encaminhamento, revisar o prompt ou as condições da política |
| a operação | Quantas conversas terminam **sem decisão** (orçamento esgotado ou erro), e em que ferramenta ou chamada elas param? | reverter a versão no ar, se a alta começou com um *deploy*; ou acionar o time do sistema de pedidos, se o erro está em `consultar_pedido` |
| quem paga | Quanto custa, em tokens, cada troca **resolvida**? A conta divide o custo de todas as conversas, inclusive as encaminhadas, pelas resolvidas. | trocar de modelo, cortar contexto (por exemplo, enviar só a condição da categoria em vez da política inteira) ou reduzir o orçamento de passos |
| quem responde pelo sistema | Alguma troca foi **registrada** fora da política, ou registrada **duas vezes** para o mesmo pedido? | suspender o registro automático (toda aprovação passa a ir para o atendente) até achar a causa, e mandar desfazer os registros indevidos no sistema da loja |

---

## 2. O *trace* de uma conversa

**Árvore de *spans* de uma conversa típica** (troca aprovada, 4 chamadas ao modelo, dentro do orçamento de 6 passos):

```text
invoke_agent  agente-de-trocas
├── chat <modelo>                        (pede consultar_pedido com o número informado)
├── execute_tool consultar_pedido
├── chat <modelo>                        (pede consultar_politica com a categoria do pedido)
├── execute_tool consultar_politica
├── chat <modelo>                        (decide aprovar e pede registrar_troca)
├── execute_tool registrar_troca         (o único span que muda o mundo)
└── chat <modelo>                        (responde ao cliente com o resultado)
```

Em cada `chat` ficam `gen_ai.request.model` (a versão exata do modelo), `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` e `gen_ai.response.finish_reasons`. Em cada `execute_tool` ficam `gen_ai.tool.name` e `gen_ai.tool.call.id`. A versão do agente (prompt e código) vai em `service.version`, um atributo padrão do OpenTelemetry. É ela que permite comparar uma versão com a anterior.

**Atributos próprios na raiz:**

| Atributo | Valores possíveis | Para que serve |
|---|---|---|
| `troca.decisao` | `aprovada`, `recusada`, `encaminhada` | conta a **resolução sem atendente** (aprovada + recusada sobre o total), que é a promessa de 60%. Sem ele, o *trace* mostra que a conversa acabou, mas não como |
| `agente.termino` | `decidiu`, `orcamento_esgotado`, `erro_ferramenta`, `erro_modelo` | separa o encaminhamento **por incerteza** (o agente decidiu encaminhar) do encaminhamento **por falha** (o orçamento acabou ou algo quebrou). Os dois aparecem como `encaminhada` para o cliente |
| `troca.dentro_da_politica` | `sim`, `nao`, `nao_se_aplica` (não houve aprovação) | **calculado em código**, no momento de `registrar_troca`: compara a data da compra (de `consultar_pedido`) com o prazo da categoria (de `consultar_politica`). A categoria usada é a que veio do pedido, e não a que o modelo passou. É o numerador do "menos de 1% fora da política". O modelo não decide esse valor |

---

## 3. Modos de falha

| Componente | Falha | Ruidosa ou silenciosa | Sinal que a torna visível |
|---|---|---|---|
| o modelo, antes de `registrar_troca` | aprova uma troca **fora do prazo**, porque erra a conta de dias ou ignora uma condição da categoria. A troca é registrada, e o cliente recebe "aprovada" | **silenciosa** | `troca.decisao = aprovada` com `troca.dentro_da_politica = nao` |
| o modelo, na decisão | **encaminha demais** por excesso de cautela, por exemplo depois de uma troca de versão do modelo. Nada quebra, mas a resolução cai abaixo de 60% | **silenciosa** | fração de `troca.decisao = encaminhada` com `agente.termino = decidiu`, por `service.version` e por dia |
| `registrar_troca` | **registro duplicado**: o modelo chama a ferramenta duas vezes na mesma conversa, ou a chamada é repetida depois de um *timeout*. Para o cliente, tudo certo; no sistema da loja, há duas trocas | **silenciosa** | mais de um *span* `execute_tool registrar_troca` no mesmo *trace*, ou mais de um registro para o mesmo número de pedido em 24 h |
| a API do modelo | *timeout*, limite de requisições (429) ou indisponibilidade do provedor. A conversa para no meio | **ruidosa** | *span* `chat` com status de erro e `error.type`, e `agente.termino = erro_modelo` na raiz |

---

## 4. Objetivos

| Tipo | Indicador | Objetivo | Janela |
|---|---|---|---|
| operacional | conversas com `agente.termino = decidiu` ÷ total de conversas | **≥ 97%**. Orçamento de erro: 3% de ~14.000, ou cerca de **420 conversas** sem decisão | 28 dias, móvel |
| a promessa da loja (limite) | trocas com `troca.dentro_da_politica = nao` ÷ trocas com `troca.decisao = aprovada` | **< 1%** | 28 dias, móvel |
| a promessa da loja (resolução) | conversas com `troca.decisao ∈ {aprovada, recusada}` ÷ total de conversas | **≥ 60%** | 28 dias, móvel |

O indicador de "fora da política" depende de `troca.dentro_da_politica` estar certo. Por isso, **uma amostra semanal de 50 trocas aprovadas é conferida por um atendente**. Se a conferência humana discordar do atributo, o problema está na regra em código, e não no agente.

---

## 5. Alertas

| Alerta | Condição e limiar | SLO de origem | Quem é avisado | O que faz |
|---|---|---|---|---|
| custo | nas últimas 6 h (~125 conversas), **mais de 15 terminadas com `agente.termino = orcamento_esgotado`** (12%, quatro vezes o orçamento de erro de 3%). Ou tokens médios por conversa acima de **2× a mediana dos 7 dias anteriores** | operacional (≥ 97% com decisão): conversa que esgota os 6 passos paga o máximo de tokens e não resolve | o responsável pelo agente | abre os *traces* que esgotaram o orçamento e procura a chamada repetida (por exemplo, `consultar_pedido` chamado várias vezes). Compara `service.version` com a versão anterior e reverte se a alta começou no *deploy* |
| degradação silenciosa | nas últimas 24 h, **2 ou mais trocas aprovadas com `troca.dentro_da_politica = nao`**: supondo ~200 aprovações/dia, 2 já é 1%, e o SLO pede menos de 1%. Também: qualquer `registrar_troca` duplicado no mesmo pedido | promessa da loja, o limite de **< 1% fora da política** | quem responde pelo sistema, com cópia para o gerente de atendimento | **suspende o registro automático**: as aprovações passam a ir para o atendente até achar a causa. Manda revisar e desfazer as trocas indevidas no sistema da loja. Depois compara a versão do modelo e do prompt com a anterior |

---

## Resposta à questão

**Como saber, sem ler o código, se o agente de trocas está funcionando, e se está funcionando bem?**

- **Funcionando** é responder às conversas: o SLO operacional (≥ 97% com decisão) e os erros nos *spans* `chat` e `execute_tool` mostram isso no painel. Uma queda aparece no alerta de custo antes de virar reclamação.
- **Funcionando bem** é cumprir a promessa, e isso **não aparece como erro**. Um agente que aprova fora do prazo ou encaminha demais responde normalmente. Só os atributos de domínio na raiz tornam isso visível: `troca.decisao` mede a resolução de 60%, e `troca.dentro_da_politica`, calculado em código e conferido por amostra humana, mede o limite de 1%. Sem eles, o *trace* diz que o agente respondeu, mas não se respondeu certo.
