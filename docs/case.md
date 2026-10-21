# Case — Agente Nutricionista Pessoal

**Grupo:** Daniel de Araujo Carvalho · Eduardo Dias Santos · Gabriel Brandão Vehchani de Freitas · Pedro Henrique Gomes
**Versão:** 2.0 (Parte 2) · **Data:** 20/10/2026

> **Nota de histórico.** O `case.md` e o `modelos.md` da Parte 1 se perderam: não estão em nenhum commit do repositório.
> Esta versão reconstrói a Parte 1 a partir dos documentos de desenho que sobreviveram
> ([arquitetura-v1.md](arquitetura-v1.md), [base-de-conhecimento-v1.md](base-de-conhecimento-v1.md),
> [memoria-v1.md](memoria-v1.md), [aula-11-avaliacao.md](aula-11-avaliacao.md)) e acrescenta o item 0 da Parte 2,
> o que o domínio ensinou, na [§0](#0-complemento-o-que-o-domínio-ensinou).

**O problema em uma frase:** decidir o que cozinhar hoje com o que já existe em casa, respeitando alergias e objetivo de quem vai comer, e sem inventar número de nutrição.

---

## 0. Complemento: o que o domínio ensinou

Estas são coisas que não estavam escritas em lugar nenhum e que o sistema só respeita porque viraram código. Cada uma aponta para o arquivo onde virou regra ou para o teste que a confere.

### 0.1 Vocabulário que quem é de fora não entende

| Termo | O que significa aqui | Onde virou regra |
|---|---|---|
| **despensa básica** | sal, pimenta, água, óleo, azeite, açúcar, vinagre e temperos secos. Toda cozinha tem, e a receita não deve ser descartada por falta deles. | `basicos` em [catalogo_ingredientes.json](../dados/catalogo_ingredientes.json) |
| **"for serving" / "accompaniment"** | acompanhamento opcional. Uma receita chamada *"…with Roasted Broccoli"* pode não exigir brócolis: o brócolis vem numa linha "(for serving)". | `opcionais_en` no catálogo |
| **"leite"** | no uso brasileiro, "leite" sozinho é leite de vaca, mas falta saber se é integral ou desnatado. Não é creme de leite, leite de coco nem leite condensado. | família `leite` em [catalogo.py](../src/catalogo.py) · `test_leite_e_ambiguo` |
| **"Ovo, galinha, branco" (TBCA)** | ovo de **casca** branca, inteiro. O modelo leu "clara do ovo" (log do caso `quanta proteína tem um ovo?`). | limite conhecido, ver [§2.11](#211-o-maior-risco) |
| **receita inteira** | o acervo não informa porções nem tempo de preparo. Toda kcal é da receita inteira, e o sistema diz isso em vez de dividir por um número inventado. | `Nutricao.base` em [esquemas.py](../src/esquemas.py) |

### 0.2 A regra que todo mundo da área conhece e nenhum documento registra

- **Sal de salmoura e óleo de fritura não são ingeridos inteiros.** A receita *Kefir-Battered Fried Chicken* leva "1 cup kosher salt" para a salmoura e "1½ cups oil" para fritar. A conta ingênua deu **117.809 mg de sódio** e 4.940 kcal, números que parecem precisos e são falsos. Agora, sal acima de 20 g e óleo de fritura ficam fora do cálculo, com o motivo declarado ([nutricional.py](../src/nutricional.py) · `test_sal_de_salmoura_nao_entra_no_sodio`).
- **Mostarda e gergelim não são alérgenos de rotulagem obrigatória no Brasil.** A lista da RDC 26/2015 da Anvisa é diferente da europeia. O catálogo segue a brasileira ([catalogo_ingredientes.json](../dados/catalogo_ingredientes.json) · `test_alergenos_seguem_a_rdc_26`).
- **Alergia se escreve no plural.** "Camarões" e "amendoins" não casavam com o alérgeno, porque tirar só o "s" final dá "camaroe" e "amendoin". O plural do português tem regras (-ões, -ães, -ns), e agora elas estão no código ([catalogo.py](../src/catalogo.py) `singular` · `test_singular`).

### 0.3 A exceção que aparece em um caso a cada vinte e decide a arquitetura

**O alérgeno escondido no nome composto.** No acervo, *"almond butter"* casava com *manteiga*: "almond" e "butter" empataram na regra do termo mais longo, e o alérgeno *castanhas* sumia. *"Egg noodles"* casava com *macarrão*, e o ovo sumia. O mesmo vale para *"peanut butter"*.

Isso decidiu a arquitetura de três formas:
1. O alérgeno de uma receita vem de **duas fontes unidas**: o item casado **e** um termo no texto bruto do ingrediente. A regra é conservadora de propósito: "coconut milk" bloqueia alergia a leite ([catalogo.py](../src/catalogo.py) `alergenos_por_texto` · `test_alergeno_por_texto`).
2. O modelo **não vê** receita com alérgeno do perfil: a ferramenta de busca só devolve receitas viáveis ([ferramentas.py](../src/ferramentas.py) `buscar_receitas`).
3. Mesmo assim, um portão em código confere a proposta antes de qualquer registro ([grafo.py](../src/grafo.py) `conferir_proposta` · [test_portao.py](../tests/test_portao.py)).

O modelo nunca é o controle sobre alergia.

### 0.4 O passo que parecia um e são três

"Registrar a compra" parecia uma escrita. São três passos, e cada um tem dono diferente:
1. **extrair** o que a pessoa disse ("comprei leite e 6 ovos"). Quem faz é o modelo, sem escolher variante.
2. **casar** com o catálogo. Quem faz é o código: "leite" é ambíguo, "quinoa" não está no catálogo.
3. **aprovar**. Quem faz é a pessoa, que vê a lista exata e pode corrigir ("leite integral, 1 l").

Escrever direto, como a v1 previa ([arquitetura-v1.md](arquitetura-v1.md) §2), gravaria "leite" escolhendo uma variante por palpite. Ver [humano.md](humano.md).

### 0.5 O que mudou de ideia desde a v1, e por quê

| v1 dizia | Agora | Por quê |
|---|---|---|
| entrada pode ser foto de nota fiscal | entrada é **texto**; a nota fiscal chega colada como texto | regra da Parte 2 (§1.1), e visão local custaria a GPU inteira |
| base de receitas: Eight Portions (~125 mil) | recorte de 300 receitas da Epicurious (Kaggle, CC BY-SA 3.0) | o link do Eight Portions saiu do ar (HTTP 404, 20/10/2026); a Epicurious é uma das três fontes que ele raspava |
| sem aprovação humana | pausa antes de somar ao estoque e antes de remover uma alergia | a escrita de estoque tinha ambiguidade real ("leite"), e remover alergia é a escrita mais perigosa |
| "6.000 tokens por pedido" | 6.000 por **chamada** (janela) e 40.000 por **execução** | a v1 não dizia qual dos dois; o laço do chef usa ~4.600 por execução ([E06](evidencias/E06-frase.txt)) |
| perfil com idade, altura, peso e rotina | perfil com objetivo, alergias, restrições, preferências e equipamentos | nada no sistema usa idade, peso, altura ou rotina; guardar seria ferir a minimização (lacuna L25 do [model-card.md](model-card.md)) |

---

## 1. O tema e o contexto

### 2.1 O problema

Quem cozinha em casa decide o cardápio em cima da hora, com o que tem na geladeira. Essa decisão erra de três jeitos:
- a pessoa desperdiça o que vence;
- ela não sabe se a refeição combina com o objetivo dela;
- quem tem alergia precisa ler cada ingrediente.

Aplicativos de receita respondem "o que fazer com frango", mas não sabem o que **esta** pessoa tem em casa nem o que ela não pode comer.

### 2.2 Os usuários, e como o agente conversa com eles

**Quem são.** Pessoas que cozinham para si ou para a família, com um objetivo declarado (manter o peso, emagrecer, ganhar massa) e, às vezes, alergia ou restrição. Os usuários do sistema são fictícios (`ana`, `bruno`, `carla` em [preparar.py](../scripts/preparar.py)).

**Como é a interação.** Por texto livre, numa linha de comando. A pessoa pede o que comer, registra o que comprou, muda o perfil ou faz uma pergunta de nutrição. Exemplos reais estão em [io.md](io.md).

**A complexidade que a disciplina pede.** O sistema precisa **descobrir** o que a pessoa quer:
- usuária nova pede jantar → o sistema pergunta objetivo e alergias antes de recomendar;
- "tenho abobrinha", mas o estoque não registra → o sistema declara a divergência e considera a abobrinha só naquela recomendação;
- "comprei leite" → ambíguo, a pessoa escolhe;
- "amanhã vou comprar brócolis" → não registra nada sobre o futuro;
- "quantas cápsulas de ômega 3 devo tomar?" → dose de suplemento é prescrição, fora do escopo.

### 2.3 O workflow do agente

Triagem → (recomendar | registrar estoque | atualizar perfil | responder pergunta | recusar). O grafo completo, com quem decide cada aresta, está em [arquitetura.md](arquitetura.md).

### 2.4 O sistema

Python 3.13; biblioteca `openai` apontada para o Ollama local (qwen2.5 7B); LangGraph para o grafo; SQLite para perfil, estoque, histórico e checkpoints; índice vetorial em arquivo (bge-m3, 1024 dimensões). Tudo roda em um computador comum com GPU de 8 GB ([modelos.md](modelos.md)).

### 2.5 A justificativa de negócio

**Por que um agente, e não software comum.** Um filtro "receitas com os ingredientes que tenho" é software comum, e ele está **dentro** do sistema (a busca só devolve receitas viáveis). O que um filtro não faz é entender texto livre, como "tenho abobrinha, me sugere algo", "NF: ARROZ TIPO1 5KG" ou "não tenho mais alergia a amendoim". O que o modelo decide em tempo de execução está apontado no diagrama ([arquitetura.md §3.3](arquitetura.md#33-a-defesa-do-nível-de-autonomia)).

**O ganho esperado, com a conta à vista.** **Não há linha de base medida.** A estimativa abaixo é hipótese, a conferir na Parte 3:

| | sem o sistema | com o sistema | origem do número |
|---|---|---|---|
| tempo para decidir o jantar | ~10 min (procurar receita, conferir a geladeira, ler os ingredientes) | ~1 min (pedir, ler, aceitar) | **estimativa do grupo, não medida** |
| tempo de resposta do sistema | — | 4–7 s por recomendação | medido: logs de [E06](evidencias/E06-frase.txt) e caso 1 |
| custo por recomendação | — | R$ 0 marginal (modelo local); energia da GPU por ~5 s | medido o tempo; energia não medida |

Denominador para conferir na Parte 3: minutos economizados por refeição decidida, numa amostra de pessoas reais.

**O ganho para o usuário, que não é o mesmo do negócio.** Para a pessoa com alergia, o ganho não é tempo: é não precisar confiar na própria leitura de cada ingrediente em inglês. Para isso, o filtro precisa ser determinístico, e ele é.

**O outro lado da conta.** O sistema não substitui nutricionista. Os valores nutricionais são da receita inteira e às vezes parciais, e a saída diz isso.

### 2.6 O verificador

Quatro verificadores, todos fora do modelo:
1. **portão de recomendação** em código (alérgeno, restrição, ingrediente faltando) — [test_portao.py](../tests/test_portao.py);
2. **portão de citação**: todo número da resposta precisa estar nas fontes — [citacao.py](../src/citacao.py);
3. **verificador de suporte**: o modelo cita um trecho e o código confere que ele existe literalmente — `verificar_resposta` em [grafo.py](../src/grafo.py);
4. **conjunto de avaliação**: triagem (20 casos), extração (6), dez perguntas com trecho conhecido ([E07](evidencias/E07-etapas.txt), [E08](evidencias/E08-perguntas.txt)) e os 20 casos planejados na [aula-11-avaliacao.md](aula-11-avaliacao.md).

### 2.7 O critério de sucesso

- **zero** recomendação com alérgeno do perfil (portão em código + teste);
- **zero** número inventado em resposta de nutrição (portão de citação);
- triagem ≥ 18/20 (medido: 20/20) e extração ≥ 5/6 (medido: 5/6) — [E07](evidencias/E07-etapas.txt);
- recomendação em menos de 10 s (medido: 4–7 s).

### 2.8 Dados

| Fonte | O que é | Licença | No repositório? |
|---|---|---|---|
| Epicurious (Kaggle, espelho Hugging Face) | 13.501 receitas → recorte curado de 300 | CC BY-SA 3.0 | sim, o recorte em `dados/corpus/receitas.jsonl` |
| TBCA (USP/FoRC) | composição de 62 alimentos (58 itens do catálogo + 4 básicos) | **não permite reprodução** | **não**: o script baixa em cada máquina |
| OMS — fichas *Healthy diet* (2026), *Sodium reduction* (2026), *Salt reduction* (2018, revogada) | diretrizes | © OMS, uso não comercial com atribuição ([fontes.md](fontes.md)) | sim, em `dados/corpus/oms/` |
| usuários `ana`, `bruno`, `carla` | perfil e estoque | fictícios | gerados por `scripts/preparar.py` |

Detalhes em [rag.md](rag.md) e [fontes.md](fontes.md).

### 2.9 Dado sensível

Alergia, restrição e objetivo de saúde são **dado pessoal sensível** (LGPD, art. 5º, II). Neste trabalho, todo dado de pessoa é **fictício**. O desenho para dado real (base legal no art. 11, minimização, remoção com cobertura verificada) está em [memoria.md](memoria.md) e no [model-card.md](model-card.md).

### 2.10 Espaço para o que ainda vem (Parte 3)

- **Multiagente:** chef, avaliador e consultor já são papéis separados; viram agentes com coordenação declarada.
- **MCP:** as ferramentas de leitura (receitas, TBCA, OMS) viram um servidor MCP.
- **Segurança:** injeção em texto de receita (caso C20 da avaliação).
- **Custo:** medição de energia por execução.

### 2.11 O maior risco

O maior risco é **o modelo afirmar algo que soa certo e não está nas fontes**. Medido nesta entrega:
- "200 mg de cafeína para grávidas", número que não está no corpus;
- "a cafeína deve ser limitada, pois pode ter efeitos negativos no feto", afirmação sem fonte;
- "130 kcal" para quinoa, que não está na TBCA do sistema;
- "5,3 g de sal" para 2000 mg de sódio (a OMS diz 5 g);
- "clara do ovo" para "Ovo, galinha, branco".

Os quatro primeiros foram barrados pelos portões em código. O último **passou**, porque o número (9,04 g) estava certo e só a interpretação estava errada. O portão de citação cobre números e trechos; não cobre interpretação. Ver [rag.md §4.4](rag.md) e [model-card.md](model-card.md).
