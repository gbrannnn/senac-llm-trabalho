---
id: triagem
versao: 1.1.0
tecnica: few-shot (10 exemplos) com saída estruturada
---
Classifique a mensagem da pessoa em UMA rota.

Rotas:
- recomendar: quer uma sugestão de refeição ou receita para fazer agora ("o que eu como?", "faz algo com frango").
- estoque: informa algo que JÁ comprou, recebeu ou tem em casa, para registrar ("comprei", "chegou", uma lista de nota fiscal).
- perfil: informa um dado permanente sobre si — objetivo, alergia, restrição, preferência, equipamento ("sou alérgico a", "virei vegetariano", "meu objetivo agora é").
- pergunta: dúvida de nutrição ou alimentação que pede uma informação, não uma receita ("quanto sal posso comer?", "ovo tem quanta proteína?").
- fora_escopo: qualquer outra coisa — inclusive diagnóstico, tratamento, dose de suplemento ou remédio, lembretes, agenda, assuntos que não são comida.

Campos:
- acao_futura: true quando a pessoa fala do que AINDA VAI fazer ("vou comprar", "amanhã", "pretendo"). Nada é registrado sobre o futuro.
- ingredientes_citados: ingredientes que a pessoa diz que tem ou quer usar, em português, no singular.
- pessoas e tempo_max_min: só se ela disser explicitamente.

Conversa anterior (pode estar vazia; use para entender respostas curtas como "pode ser" ou "2 pessoas"):
{{conversa}}

Exemplos:
"o que eu faço pra janta hoje?" -> recomendar
"tenho frango e limão, me sugere algo em 20 minutos" -> recomendar, ingredientes_citados=["frango","limão"], tempo_max_min=20
"comprei 2kg de frango, uma dúzia de ovos e leite" -> estoque
"NF: ARROZ TIPO1 5KG 1UN; FEIJAO CARIOCA 1KG 2UN" -> estoque
"amanhã vou comprar brócolis, me lembra?" -> fora_escopo, acao_futura=true
"descobri que tenho alergia a camarão" -> perfil
"qual o limite de sal por dia que a OMS recomenda?" -> pergunta
"quantos gramas de creatina eu devo tomar?" -> fora_escopo
"quantos mg de vitamina C eu tomo por dia?" -> fora_escopo (dose de suplemento é prescrição, mesmo parecendo pergunta)
"ganhei um liquidificador" -> perfil (equipamento de cozinha vai no perfil, não no estoque de comida)

Mensagem: {{entrada}}
