# Entrada e saída — o contrato do sistema

**Versão do sistema:** commit `fffe38f` · schemas em [src/esquemas.py](../src/esquemas.py) · exemplos **copiados dos logs** por script, e não escritos à mão. Os seis casos completos do §9 estão em [logs/](../logs/) (`caso1` … `caso6d`).

## 1.1 A entrada é texto

A pessoa digita **texto livre**: pedido de refeição, compra, mudança de perfil, dúvida. Uma nota fiscal entra **colada como texto** ("NF: ARROZ TIPO1 5KG 1UN"), nunca como arquivo no lugar da pergunta.

**O que acompanha o texto sem ser digitado** (vem da linha de comando, e **nunca** do modelo):

| Campo | De onde | Para quê |
|---|---|---|
| `usuario_id` | `--usuario` | chave de perfil, estoque e histórico; injetado nas ferramentas pelo código |
| `sessao` | `--sessao` | com o usuário, forma o `thread_id = usuario:sessao`, endereço do checkpoint ([memoria.md §5.5](memoria.md#55-a-conversa-e-o-que-sobra-dela)) |
| resposta a uma pausa | `--aprovar`, `--rejeitar`, `--editar '<json>'` | é o `Command(resume=...)` do LangGraph |

## 1.2 O contrato de saída

`Saida` ([esquemas.py](../src/esquemas.py)), validada pelo Pydantic em toda execução, inclusive em erro e em pausa:

| Campo | O que é | Os três obrigatórios do §1.2 |
|---|---|---|
| `resultado` | o texto que a pessoa lê | **o resultado** |
| `receita` | `ReceitaSaida` (id, nome, ingredientes, `faltando_no_estoque`, `nutricao`), só em recomendação | parte do resultado |
| `fontes` | lista de `{tipo, id, detalhe}`; `tipo ∈ {receita, tbca, oms, perfil, estoque, historico, usuario, regra}`. Só o que **sustenta** o resultado: na recusa, a lista é vazia | **a fonte** |
| `suficiencia` | `suficiente` · `parcial` · `insuficiente` · `incompleta` · `fora_de_escopo` | **a suficiência** |
| `motivo_suficiencia` | por que não é `suficiente` | — |
| `escolhas_declaradas` | o que o sistema decidiu sozinho e está avisando: divergência com o estoque, cálculo parcial, justificativa substituída, resposta descartada | — |
| `pendencia` | numa pausa, a ação exata aguardando a pessoa; numa escrita, o efeito (`chave`, `ja_existia`) | — |
| `termino` | um dos 14 motivos ([arquitetura.md](arquitetura.md#o-término)) | — |
| `tipo` | `recomendacao` · `estoque` · `perfil` · `resposta` · `pergunta` · `recusa` · `aguardando_aprovacao` · `erro` | — |
| `execucao_id`, `thread_id` | identificam a execução no log | — |
| `uso` | tokens, chamadas, segundos, maior janela (acrescentado por [main.py](../src/main.py)) | — |

A **recusa** é parte do contrato: `tipo: recusa`, `suficiencia: insuficiente` ou `fora_de_escopo`, e um `resultado` que diz o que o sistema faz no lugar.

**Os schemas das etapas internas** (o que o modelo devolve) também são Pydantic e estão no mesmo arquivo: `Triagem`, `ItensExtraidos`, `AtualizacaoPerfil`, `FechamentoChef`, `FechamentoConsultor`, `Suporte`, `Veredito`. A tabela de cada um está em [prompts.md](prompts.md).

## 9. Os seis casos demonstrados

Gerados por `python -m scripts.preparar --banco && python -m scripts.demonstrar` no commit `fffe38f`, em 20/10/2026, a partir do estado inicial dos usuários fictícios.

| # | O caso | Entrada | Log | O que prova |
|---|---|---|---|---|
| 1 | caminho feliz | "oi! o que eu posso fazer pra jantar hoje?" | [`caso1`](../logs/20261020-230141_caso1.jsonl) | busca (1) → proposta → portão → avaliador → registro; 4 chamadas, 7 s |
| 2 | **divergência** | "tenho abobrinha aqui, me sugere alguma coisa com abobrinha" | [`caso2`](../logs/20261020-230150_caso2.jsonl) | a pessoa diz ter abobrinha, o estoque não registra. O sistema declara a divergência em `escolhas_declaradas`, considera a abobrinha **só nesta recomendação** e **não altera o estoque** |
| 3 | **registro inexistente** | "quanta proteína tem 100 g de tofu e 100 g de ovo?" | [`caso3`](../logs/20261020-230155_caso3.jsonl) | `consultar_alimento("tofu")` devolve erro ("não está no recorte da TBCA"). O modelo **contorna**: responde o ovo e diz que faltou o tofu (`suficiencia: parcial`) |
| 4 | **não deve disparar a ação principal** | "amanhã vou comprar brócolis e frango, me lembra de cozinhar?" | [`caso4`](../logs/20261020-230204_caso4.jsonl) | `sem_acao`: nenhuma escrita no estoque, nenhuma receita, nenhum lembrete |
| 5 | **fora do corpus** | "o que a OMS recomenda sobre cafeína na gravidez?" | [`caso5`](../logs/20261020-230205_caso5.jsonl) | recusa com algo útil (o que o sistema consegue responder); a resposta inventada do modelo foi descartada pelo verificador |
| 6 | **para e espera** | "comprei leite e 6 ovos" → editar → a mesma aprovação de novo → aprovar sem pendência | [`caso6a`](../logs/20261020-230216_caso6a_pausa.jsonl) · [`6b`](../logs/20261020-230218_caso6b_aprovar_editando.jsonl) · [`6c`](../logs/20261020-230218_caso6c_aprovacao_repetida.jsonl) · [`6d`](../logs/20261020-230218_caso6d_aprovar_sem_pendencia.jsonl) | pausa com "leite" ambíguo; a pessoa **aprova editando** (leite integral, 1 l); a segunda aprovação devolve `ja_existia: true, gravados: 0` ([humano.md §8.5](humano.md#85-aprovar-duas-vezes)) |

Logs extras da mesma rodada: [`io_incompleta`](../logs/20261020-230218_io_incompleta.jsonl) (usuária sem perfil) e [`io_alergia`](../logs/20261020-230219_io_alergia.jsonl). Neste último, o Bruno, alérgico a amendoim, pediu "um lanche com banana e pão": das 15 receitas candidatas, 2 foram descartadas **em código** por amendoim e 14 por ingrediente faltando, e o sistema recusou em vez de sugerir o sanduíche de pasta de amendoim.

## 1.3 e 1.4 Os exemplos

### 1. O caminho feliz

**Commit:** `fffe38f` · **data:** 2026-10-20T23:01:41 · **log:** [`logs/20261020-230141_caso1.jsonl`](../logs/20261020-230141_caso1.jsonl) · **usuário:** `ana` (fictício)

**Entrada exata:**

```text
oi! o que eu posso fazer pra jantar hoje?
```

`python -m src.main --usuario ana --sessao caso1 "oi! o que eu posso fazer pra jantar hoje?"`

**Saída completa:**

```json
{
  "execucao_id": "7530f90f57",
  "thread_id": "ana:caso1",
  "tipo": "recomendacao",
  "resultado": "Sugestão: Stir-Fried Black Rice with Fried Egg and Roasted Broccoli. Usa arroz, ovo, que estão no seu estoque. A receita inteira tem cerca de 1652 kcal e 35 g de proteína (TBCA).",
  "receita": {
    "id": "R03115",
    "nome": "Stir-Fried Black Rice with Fried Egg and Roasted Broccoli",
    "ingredientes": [
      "2 tablespoons vegetable oil, divided",
      "2 large eggs",
      "Kosher salt",
      "2 cups cooked black rice (from about 1 cup uncooked)",
      "Coconut-Oil Roasted Broccoli with Nutritional Yeast, some Toasted Nori Mayonnaise, sliced avocado, and cilantro leaves with tender stems (for serving)"
    ],
    "faltando_no_estoque": [],
    "nutricao": {
      "energia_kcal": 1651.5,
      "proteina_g": 35.1,
      "carboidrato_g": 295.4,
      "lipidio_g": 37.8,
      "sodio_mg": 151.1,
      "completa": false,
      "fora_do_calculo": [
        "Kosher salt"
      ],
      "base": "receita inteira (o dataset não informa porções)"
    }
  },
  "fontes": [
    {
      "tipo": "estoque",
      "id": "ana",
      "detalhe": "18 itens"
    },
    {
      "tipo": "perfil",
      "id": "ana",
      "detalhe": "tabela perfil"
    },
    {
      "tipo": "oms",
      "id": "oms-alimentacao-saudavel-2026#01",
      "detalhe": "critério do avaliador (2026-01-26)"
    },
    {
      "tipo": "receita",
      "id": "R03115",
      "detalhe": "Epicurious via Kaggle 'Food Ingredients and Recipe Dataset with Images' (CC BY-SA 3.0)"
    },
    {
      "tipo": "tbca",
      "id": "BRC0001A,BRC0012J",
      "detalhe": "composição por 100 g"
    }
  ],
  "suficiencia": "suficiente",
  "motivo_suficiencia": null,
  "escolhas_declaradas": [
    "cálculo nutricional parcial: fora do cálculo Kosher salt",
    "justificativa do modelo substituída por texto em código: prometia benefício ('boa opção')"
  ],
  "pendencia": null,
  "termino": "concluido",
  "uso": {
    "tokens": 4585,
    "chamadas": 4,
    "segundos": 7.01,
    "maior_janela": 1541
  }
}
```

**O que ler aqui:** `faltando_no_estoque` vazio e `suficiencia: suficiente`: a receita usa só ovo e arroz, que estão no estoque da Ana. O brócolis do nome vem numa linha "(for serving)", que é acompanhamento opcional. `fontes` traz o que sustenta cada parte: o estoque e o perfil lidos, a receita (com licença), os códigos TBCA do cálculo e o trecho da OMS que o avaliador usou. Duas escolhas declaradas: o sal sem medida ficou fora do cálculo (`nutricao.completa: false`), e a justificativa do modelo foi **substituída em código**, porque prometia benefício ("boa opção"). A kcal é da receita inteira (`nutricao.base`), porque o acervo não informa porções.

### 2. A recusa

**Commit:** `fffe38f` · **data:** 2026-10-20T23:02:05 · **log:** [`logs/20261020-230205_caso5.jsonl`](../logs/20261020-230205_caso5.jsonl) · **usuário:** `ana` (fictício)

**Entrada exata:**

```text
o que a OMS recomenda sobre cafeína na gravidez?
```

`python -m src.main --usuario ana --sessao caso5 "o que a OMS recomenda sobre cafeína na gravidez?"`

**Saída completa:**

```json
{
  "execucao_id": "2146bf402e",
  "thread_id": "ana:caso5",
  "tipo": "recusa",
  "resultado": "Não encontrei nas minhas fontes (TBCA e fichas da OMS) a informação para responder isso. Consigo informar a composição de alimentos como abacate, abobrinha, abóbora, alho, amendoim, amido de milho, arroz, aveia, azeitona, açúcar mascavo, banana, batata, e as recomendações da OMS sobre alimentação saudável e sódio. Para outros alimentos, consulte um nutricionista.",
  "receita": null,
  "fontes": [],
  "suficiencia": "insuficiente",
  "motivo_suficiencia": "término: recusa_sem_base; resposta do modelo descartada: o verificador não achou nas fontes o assunto da pergunta (OMS não forneceu diretamente recomendações específicas sobre a cafeína durante a gravidez)",
  "escolhas_declaradas": [
    "resposta do modelo descartada: o verificador não achou nas fontes o assunto da pergunta (OMS não forneceu diretamente recomendações específicas sobre a cafeína durante a gravidez)"
  ],
  "pendencia": null,
  "termino": "recusa_sem_base",
  "uso": {
    "tokens": 5740,
    "chamadas": 5,
    "segundos": 10.53,
    "maior_janela": 1445
  }
}
```

**O que ler aqui:** `suficiencia: insuficiente`, `fontes` **vazias** (o que foi recuperado não sustentava nada) e `escolhas_declaradas` com o motivo: o modelo escreveu uma resposta, e o verificador não achou o assunto nas fontes. O texto que a pessoa lê foi montado **por código**: diz o que o sistema não encontrou e o que ele consegue responder. Nas versões anteriores, o modelo, sem base, respondia "não ultrapasse 200 mg", número que não está no corpus.

### 3. Entrada incompleta (§1.4)

**Commit:** `fffe38f` · **data:** 2026-10-20T23:02:18 · **log:** [`logs/20261020-230218_io_incompleta.jsonl`](../logs/20261020-230218_io_incompleta.jsonl) · **usuário:** `carla` (fictício)

**Entrada exata:**

```text
o que eu faço pra janta?
```

`python -m src.main --usuario carla --sessao io "o que eu faço pra janta?"`

**Saída completa:**

```json
{
  "execucao_id": "52765df132",
  "thread_id": "carla:io",
  "tipo": "pergunta",
  "resultado": "Ainda não conheço você. Antes de recomendar, me diga: qual é o seu objetivo (ex.: emagrecer, manter o peso, ganhar massa) e se você tem alguma alergia ou restrição alimentar.",
  "receita": null,
  "fontes": [],
  "suficiencia": "incompleta",
  "motivo_suficiencia": "perfil ausente: preciso do seu objetivo e de alergias antes de recomendar",
  "escolhas_declaradas": [
    "perfil ausente: preciso do seu objetivo e de alergias antes de recomendar"
  ],
  "pendencia": null,
  "termino": "pergunta_ao_usuario",
  "uso": {
    "tokens": 831,
    "chamadas": 1,
    "segundos": 0.96,
    "maior_janela": 786
  }
}
```

**O que ler aqui:** `tipo: pergunta`, `suficiencia: incompleta`, `termino: pergunta_ao_usuario`. A Carla não tem perfil, e o sistema **não recomenda** sem saber objetivo e alergias: pergunta o que falta. Foi **1** chamada ao modelo (a triagem); o portão `checar_pedido` é código.

### 4. Entrada ambígua (§1.4) — e a pausa para aprovação

**Commit:** `fffe38f` · **data:** 2026-10-20T23:02:16 · **log:** [`logs/20261020-230216_caso6a_pausa.jsonl`](../logs/20261020-230216_caso6a_pausa.jsonl) · **usuário:** `ana` (fictício)

**Entrada exata:**

```text
comprei leite e 6 ovos
```

`python -m src.main --usuario ana --sessao caso6 "comprei leite e 6 ovos"`

**Saída completa:**

```json
{
  "execucao_id": "9858acd1d0",
  "thread_id": "ana:caso6",
  "tipo": "aguardando_aprovacao",
  "resultado": "Vou SOMAR estes itens ao seu estoque (ana):\n  - ovo: 6 un\nPendentes:\n  ? leite: ambíguo entre leite_desnatado, leite_integral — NÃO será gravado, a menos que você edite\nConsequência: as quantidades acima passam a contar nas próximas recomendações. Nada foi gravado ainda.\nResponda até 2026-10-21T23:02:18:\n  aprovar               -> grava exatamente a lista acima\n  editar <json>         -> grava a lista que você mandar, por exemplo [{\"item_id\":\"leite_integral\",\"quantidade\":1,\"unidade\":\"l\"}]\n  rejeitar              -> não grava nada\nSem resposta até o prazo, nada é gravado.",
  "receita": null,
  "fontes": [
    {
      "tipo": "estoque",
      "id": "ana",
      "detalhe": "18 itens"
    }
  ],
  "suficiencia": "suficiente",
  "motivo_suficiencia": null,
  "escolhas_declaradas": [],
  "pendencia": {
    "acao": "estoque.somar",
    "usuario_id": "ana",
    "itens": [
      {
        "item_id": "ovo",
        "nome": "ovo",
        "quantidade": 6.0,
        "unidade": "un",
        "quantidade_informada": true
      }
    ],
    "pendentes": [
      {
        "nome": "leite",
        "motivo": "ambiguo",
        "candidatos": [
          "leite_desnatado",
          "leite_integral"
        ]
      }
    ],
    "expira_em": "2026-10-21T23:02:18",
    "texto": "Vou SOMAR estes itens ao seu estoque (ana):\n  - ovo: 6 un\nPendentes:\n  ? leite: ambíguo entre leite_desnatado, leite_integral — NÃO será gravado, a menos que você edite\nConsequência: as quantidades acima passam a contar nas próximas recomendações. Nada foi gravado ainda.\nResponda até 2026-10-21T23:02:18:\n  aprovar               -> grava exatamente a lista acima\n  editar <json>         -> grava a lista que você mandar, por exemplo [{\"item_id\":\"leite_integral\",\"quantidade\":1,\"unidade\":\"l\"}]\n  rejeitar              -> não grava nada\nSem resposta até o prazo, nada é gravado.",
    "respostas_aceitas": [
      "aprovar",
      "rejeitar",
      "editar"
    ]
  },
  "termino": "aguardando_humano",
  "uso": {
    "tokens": 1364,
    "chamadas": 2,
    "segundos": 1.86,
    "maior_janela": 786
  }
}
```

**O que ler aqui:** `"leite"` aparece em `pendencia.pendentes` como **ambíguo** entre integral e desnatado, e **não** está em `itens`: o sistema não escolhe por palpite. Ele para (`termino: aguardando_humano`) e mostra a ação exata, a consequência e o prazo. A continuação (aprovar editando, aprovar de novo sem duplicar) está em [humano.md §8.5](humano.md#85-aprovar-duas-vezes). As `fontes` da pausa são só o estoque: o perfil e o histórico foram lidos, mas não sustentam esta ação.

### 5. Fora do escopo, e o caso que não deve disparar a ação (§1.4, §3.3)

**Commit:** `fffe38f` · **data:** 2026-10-20T23:02:04 · **log:** [`logs/20261020-230204_caso4.jsonl`](../logs/20261020-230204_caso4.jsonl) · **usuário:** `ana` (fictício)

**Entrada exata:**

```text
amanhã vou comprar brócolis e frango, me lembra de cozinhar?
```

`python -m src.main --usuario ana --sessao caso4 "amanhã vou comprar brócolis e frango, me lembra de cozinhar?"`

**Saída completa:**

```json
{
  "execucao_id": "28377f0075",
  "thread_id": "ana:caso4",
  "tipo": "resposta",
  "resultado": "Não registrei nada: você falou do que ainda vai fazer, e eu só registro o que já aconteceu. Também não envio lembretes. Quando comprar, me diga o que chegou.",
  "receita": null,
  "fontes": [],
  "suficiencia": "suficiente",
  "motivo_suficiencia": null,
  "escolhas_declaradas": [],
  "pendencia": null,
  "termino": "sem_acao",
  "uso": {
    "tokens": 865,
    "chamadas": 1,
    "segundos": 1.32,
    "maior_janela": 799
  }
}
```

**O que ler aqui:** `termino: sem_acao`: nada foi registrado no estoque (a compra ainda não aconteceu), nenhuma receita foi recomendada, e o texto diz o que o sistema não faz (lembretes). A decisão é uma **regra em código** sobre o campo `acao_futura`, que a triagem acertou. A rota da triagem para pedidos assim oscilou entre versões do prompt ([prompts.md](prompts.md)).
