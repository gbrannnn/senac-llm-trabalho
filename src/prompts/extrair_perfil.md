---
id: extrair_perfil
versao: 1.0.0
tecnica: few-shot (4 exemplos) com saída estruturada
---
A pessoa quer mudar um dado permanente do perfil dela. Diga qual campo, qual operação e o valor.

Campos: objetivo (texto livre curto), alergias, restricoes (vegetariano, sem lactose, sem glúten...), preferencias, equipamentos.
Operações: definir (substitui), adicionar (inclui na lista), remover (tira da lista).
Valor: curto, em português, no singular ("amendoim", "vegetariano", "air fryer").

Exemplos:
"mudei meu objetivo para emagrecimento" -> {"campo":"objetivo","operacao":"definir","valor":"emagrecimento"}
"tenho alergia a camarão" -> {"campo":"alergias","operacao":"adicionar","valor":"camarão"}
"não sou mais vegetariano" -> {"campo":"restricoes","operacao":"remover","valor":"vegetariano"}
"comprei uma air fryer" -> {"campo":"equipamentos","operacao":"adicionar","valor":"air fryer"}

Mensagem: {{entrada}}
