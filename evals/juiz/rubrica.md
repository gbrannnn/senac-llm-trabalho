---
id: adequacao_receita
versao: 1.0.0
data: 2026-11-23
modelo_juiz: llama3.1:8b
limiar_declarado_em: 2026-11-23, antes de qualquer saída ser julgada ou rotulada
---
# Rubrica do juiz — a receita atende ao pedido?

## Por que esta propriedade vai para um juiz

Alergia, ingrediente faltando, restrição e números são conferidos em código (docs/evals.md §2).
O que sobra sem gabarito é se a receita **é o que a pessoa pediu**: "o que eu almoço?" respondido
com *Garlic Croutons* passa em todas as verificações determinísticas, porque o crouton usa o que
está no estoque e não tem alérgeno, e mesmo assim não é almoço. Nenhuma lista de palavras separa
"prato" de "acompanhamento" no acervo (os nomes estão em inglês e variam: *dressing*, *vinaigrette*,
*relish*, *topping*, *sauce*...), e a regra R1 da memória procedural, que pede isso ao chef, é só
texto no prompt.

## Critério (binário)

**ADEQUADA (`adequada: true`)** quando as duas condições valem:
1. a receita é algo que se come como a refeição pedida: um prato para "jantar" ou "almoço"; para
   "lanche" ou "café da manhã" vale também algo leve, um sanduíche ou uma panqueca; para
   "sobremesa" ou "doce", um doce;
2. se a pessoa citou explicitamente um ingrediente ou um tipo de prato, a receita é desse ingrediente
   ou desse tipo de prato.

**NÃO ADEQUADA (`adequada: false`)** quando ao menos uma vale:
- a receita é um acompanhamento isolado ou um componente (molho, molho de salada, vinagrete,
  tempero, calda, cobertura, crouton, caldo base) e a pessoa pediu uma refeição;
- a receita é doce ou sobremesa e a pessoa pediu almoço ou jantar;
- a receita ignora o ingrediente ou o tipo de prato que a pessoa pediu.

**Não julgue:** calorias, nutrição, alergia, estoque, tempo ou porções (são conferidos em código),
nem a qualidade do texto. Um pedido vago ("o que eu como?") aceita qualquer prato.

## Exemplos

- **ADEQUADA.** Pedido: "oi! o que eu posso fazer pra jantar hoje?". Receita: *Lemony Chicken Milanese
  with Arugula Salad* (frango, limão, ovo, folhas). É um prato de jantar.
- **NÃO ADEQUADA.** Pedido: "to com fome, o que eu almoço?". Receita: *Garlic Croutons* (pão, alho,
  manteiga). Crouton é acompanhamento, não almoço.

## Saída

`{"adequada": true | false, "motivo": "uma frase"}`

## Limiar de adoção (declarado antes de medir)

O juiz é adotado na suíte só se, nas 20 saídas rotuladas à mão:
- **concordância ≥ 85%** (17 de 20), **e**
- **no máximo 1 falso positivo** (juiz diz adequada, humano diz não). O falso positivo é o erro que
  importa: é o juiz deixando passar o crouton como almoço.

Abaixo do limiar, o juiz **não é adotado**: os vereditos continuam sendo registrados nas rodadas,
mas não entram no "passou" de nenhum caso, e o resultado negativo é reportado em docs/evals.md.
