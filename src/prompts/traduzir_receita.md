---
id: traduzir_receita
versao: 1.1.0
tecnica: instrução com glossário de unidades, saída estruturada com número de linhas fixo; cada linha é conferida em código
---
Traduza para o português do Brasil o nome e os ingredientes da receita abaixo. É só tradução: não adapte, não resuma, não junte linhas e não acrescente nada.

Regras:
- traduza SEMPRE o nome do prato ("Chocolate Cake" -> "Bolo de chocolate"; "Potato Latkes" -> "Latkes de batata");
- devolva uma linha traduzida para cada linha numerada, na mesma ordem, sem o número da linha;
- copie todos os números exatamente como estão, inclusive frações ("1/2" continua "1/2");
- unidades: teaspoon = colher de chá; tablespoon = colher de sopa; cup = xícara; ounce = onça; pound = libra; pint = pint. Não converta para gramas;
- use o nome comum do ingrediente em português: broccoli = brócolis; scallions = cebolinha; parsley = salsinha; cilantro = coentro; mayonnaise = maionese; whole milk = leite integral; heavy cream = creme de leite; sour cream = creme azedo; egg yolk = gema; egg white = clara; salt = sal; pepper = pimenta; chopped = picado; minced = bem picado. Se não souber uma palavra, deixe-a em inglês em vez de inventar.

Exemplo:
nome: "Butter-Sugar Crepes"
ingredientes:
1. 1 cup all-purpose flour
2. 2 large eggs
3. 1 1/2 teaspoons sugar
-> {"nome": "Crepes de manteiga e açúcar", "ingredientes": ["1 xícara de farinha de trigo", "2 ovos grandes", "1 1/2 colheres de chá de açúcar"]}

nome: {{nome}}
ingredientes:
{{ingredientes}}
