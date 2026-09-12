# Arquitetura v1 — Agente Nutricionista Pessoal

## 1. Entrada

**O quê:** dois tipos de material bem diferentes chegam ao sistema — texto livre (pedido de recomendação, atualização de perfil, dúvida) e mídia (foto de compra, geladeira, armário, ou nota fiscal digitalizada).

**De onde, quem dispara:** o usuário sempre inicia — manda uma mensagem ou sobe uma foto. Nesta v1 o sistema não acorda sozinho (um lembrete de item vencendo seria uma extensão natural, mas fica fora do escopo — ver nota na seção de Registro).

**Quão heterogêneo:** ~55% pedido de recomendação em texto ("o que eu como hoje?", "tem algo com frango?"), ~30% foto/nota fiscal para atualizar estoque, ~10% atualização de perfil ("mudei meu objetivo pra emagrecimento"), ~5% fora de escopo (ex.: pedido de diagnóstico ou prescrição médica). Três naturezas de pedido diferentes, em proporção relevante cada uma → há o que rotear.

## 2. System

**System prompt (uma frase):** *"Você é um nutricionista pessoal que recomenda refeições com base no estoque doméstico e no perfil do usuário; você não substitui acompanhamento médico, não prescreve suplementação nem trata condições clínicas."*

**Ferramentas:**

| Ferramenta | Leitura/Escrita | Reversível? |
|---|---|---|
| `estoque.consultar(usuario_id)` | leitura | — |
| `estoque.extrair_da_imagem(imagem)` | leitura (visão) | — (não grava sozinha) |
| `estoque.atualizar(usuario_id, itens)` | escrita, idempotente (upsert item+usuário) | sim — usuário edita/apaga manualmente |
| `perfil.consultar(usuario_id)` | leitura | — |
| `perfil.atualizar(usuario_id, campo, valor)` | escrita, idempotente | sim |
| `receitas.buscar(ingredientes)` | leitura | — |
| `nutricional.calcular(receita)` | leitura/função determinística | — |
| `recomendacao.registrar(usuario_id, receita_final)` | escrita, idempotente (upsert usuário+dia) | sim |

**Estado que sobrevive entre passos:** perfil do usuário (objetivo, restrições, alergias), estoque atual, receita candidata (rascunho corrente do chef), veredito e motivo da última avaliação do nutricionista, contador de rodadas.

**Orçamento:**
- `MAX_PASSOS_CHEF = 5`
- `MAX_RODADAS_AVALIACAO = 3`
- `MAX_PASSOS_ESTOQUE = 3` (tentativas de casar item extraído com o catálogo)
- `MAX_TOKENS_POR_PEDIDO = 6000`
- `TIMEOUT_RESPOSTA_TEXTO = 15s`

## 3. Processamento

A triagem tem dois níveis: o primeiro (imagem vs. texto) é checagem de tipo de arquivo, código puro, sem LLM. O segundo — classificar a *intenção* dentro do texto — é o Router de fato.

## Esboço do fluxo

```
1. ENTRADA         texto livre, ou foto/nota fiscal do usuário             [—]

2. TRIAGEM         nível 0: tipo de mídia (código, sem LLM)
                     imagem -> segue para 3
                     texto  -> nível 1, classifica intenção        [ROUTER]
                       pedido  -> segue para 4
                       perfil  -> regra em código, grava direto, sem LLM
                       fora    -> recusa

3. ESTOQUE         extrai itens da imagem, casa com o catálogo
                   e grava                          [AGENTE-ESTOQUE, 3 passos]
                                                     [ESCRITA - idempotente]
                   -> retorna direto ao usuário, não passa por 4-8

4. CONSULTA        busca estoque atual + perfil do usuário                 [—]

5. RECEITA         gera proposta de receita com o estoque
                   disponível                          [AGENTE-CHEF, 5 passos]

6. AVALIAÇÃO       avalia a receita contra objetivo/restrições    [AVALIADOR
                   do perfil                          NUTRICIONISTA, 3 rodadas]
                     reprovado -> volta para 5 com o motivo
                     aprovado  -> segue para 7

7. REGISTRO        grava a recomendação aprovada no histórico       [ESCRITA -
                                                                     idempotente]

8. RETORNO         devolve a receita ao usuário, em até 3 linhas           [—]
```

## O que sai de cada etapa

```
2. TRIAGEM
   entra:  {"tipo": "texto", "usuario_id": "u123", "conteudo": "o que eu como hoje?"}
   sai:    {"rota": "pedido", "usuario_id": "u123", "texto": "o que eu como hoje?"}

3. ESTOQUE
   entra:  {"tipo": "imagem", "usuario_id": "u123", "arquivo": "<foto>"}
   sai:    {"itens_adicionados": ["ovo", "espinafre", "queijo cottage"],
            "nao_reconhecidos": []}

5. RECEITA
   entra:  {"estoque": [...], "perfil": {...}, "pedido": "o que eu como hoje?"}
   sai:    {"receita": {"nome": "omelete de espinafre com cottage",
            "ingredientes": [...], "porcoes": 1}}

6. AVALIAÇÃO
   entra:  {"receita": {...}, "perfil": {"objetivo": "emagrecimento", ...}}
   sai:    {"veredito": "aprovado", "kcal": 320, "proteina_g": 28}

7. REGISTRO
   entra:  {"usuario_id": "u123", "receita_final": {...}}
   sai:    {"status": "gravado", "recomendacao_id": "r789"}

8. RETORNO
   sai:    o texto que o usuário lê, em até 3 linhas
```

**O que o usuário efetivamente vê:**

> "Hoje: omelete de espinafre com queijo cottage — 320 kcal, 28g de proteína, dá pra fazer com o que você já tem em casa. Quer o passo a passo?"

## Justificativa dos padrões escolhidos

**TRIAGEM — Router (só para texto).** A entrada é heterogênea em três intenções (pedido, perfil, fora de escopo) em proporção relevante cada uma; sem rota, toda etapa seguinte precisaria saber lidar com as três. Parei no Router porque uma única classificação já resolve — não há por que orquestrar ou paralelizar uma decisão que é so-classificação.

**ESTOQUE — Agente pequeno (3 passos).** A extração em si (visão + parsing) é determinística, mas casar "leite" extraído com "leite integral" já cadastrado às vezes exige mais de uma tentativa (sinônimo, abreviação, busca fuzzy). Um passo fixo de código quebraria nesses casos; um agente completo (chef ou avaliador) seria demais para uma tarefa de correspondência. Um agente enxuto com teto de 3 passos resolve sem virar outra coisa.

**RECEITA — Agente-chef (5 passos).** Gerar receita a partir de um estoque variável exige decisões em tempo de execução — quais itens priorizar, como substituir o que falta, como ajustar porção — que não cabem numa regra fixa nem numa chamada única sem ferramentas. Por isso agente, e não *workflow*. O teto evita busca de receita sem fim.

**AVALIAÇÃO — Avaliador-otimizador (nutricionista, 3 rodadas).** Checar se uma receita já pronta atende objetivo/restrição é comparação contra critério, não geração — o par gerador (chef) / crítico (nutricionista) encaixa exatamente no padrão avaliador, mais barato que dar autonomia irrestrita a um único agente sobre o fluxo inteiro. O teto de rodadas evita ping-pong infinito entre os dois.

**CONSULTA e RETORNO — sem padrão.** São leitura e formatação simples, sem decisão em tempo de execução; aplicar qualquer padrão aqui seria custo sem contrapartida.

**REGISTRO — escrita idempotente, e uma decisão deliberada.** Nenhuma escrita deste fluxo é irreversível: estoque e perfil são upsert editável, e o registro da recomendação é upsert por usuário+dia. A única ação potencialmente irreversível do sistema — descontar os itens usados do estoque como consumidos — foi propositalmente deixada **fora** do fluxo v1: fica condicionada a uma confirmação explícita futura do usuário ("cozinhei isso"), porque decrementar estoque sem confirmar que a receita foi de fato preparada seria assumir uma ação que talvez não tenha ocorrido.

---

*v1 — existe para estar errada de um jeito visível. Pontos que mais devem mudar com o código: se o casamento de itens do estoque realmente precisa de agente ou se uma busca fuzzy determinística já resolve; e se 3 rodadas de avaliação são suficientes quando o estoque é muito restrito (poucas opções de substituição).*
