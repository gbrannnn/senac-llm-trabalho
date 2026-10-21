---
id: extrair_itens
versao: 1.0.0
tecnica: few-shot (3 exemplos) com saída estruturada
---
Extraia os itens de comida que a pessoa diz ter comprado ou ter em casa.

Regras:
- nome em português, no singular, como a pessoa diria ("ovo", "leite", "peito de frango"). NÃO escolha variante que ela não disse: se ela disse "leite", escreva "leite", e não "leite integral".
- quantidade e unidade só se estiverem no texto; se não estiverem, deixe null. Não invente.
- "dúzia" = 12 un. "kg" e "g" ficam como estão.
- ignore o que não é comida (sacola, detergente) e o que ela ainda vai comprar.

Exemplos:
"comprei 2kg de frango e uma dúzia de ovos" -> [{"nome":"frango","quantidade":2,"unidade":"kg"},{"nome":"ovo","quantidade":12,"unidade":"un"}]
"NF: ARROZ TIPO1 5KG 1UN; DETERGENTE 500ML 1UN" -> [{"nome":"arroz","quantidade":5,"unidade":"kg"}]
"chegou leite e queijo cottage" -> [{"nome":"leite","quantidade":null,"unidade":null},{"nome":"queijo cottage","quantidade":null,"unidade":null}]

Mensagem: {{entrada}}
