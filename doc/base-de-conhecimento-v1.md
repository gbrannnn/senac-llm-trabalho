# Base de Conhecimento v1 — Agente Nutricionista Pessoal

## 1. Qual informação especializada o agente precisa, e por que ela não está no modelo

O agente proposto tem como objetivo atuar como um nutricionista pessoal, considerando o estoque doméstico, o perfil do usuário, as receitas disponíveis e informações nutricionais para recomendar refeições adequadas ao contexto informado. Na arquitetura definida anteriormente, o fluxo envolve consulta ao estoque e ao perfil, busca de receitas, cálculo nutricional, avaliação da receita e registro da recomendação. Dessa forma, parte do conhecimento necessário é externo ao modelo de linguagem e precisa ser recuperado de fontes específicas.

A primeira fonte de conhecimento será uma **base de receitas**, utilizada pelo agente-chef para encontrar possibilidades de refeições a partir dos ingredientes disponíveis, das preferências do usuário e das condições da solicitação. Será utilizado como fonte principal o dataset de receitas do **Eight Portions**, complementado, quando necessário, pelo dataset *Recipe Ingredients Dataset*, disponível no Kaggle. A base é necessária principalmente por ser **específica demais**: embora um modelo de linguagem conheça diversas receitas, não há garantia de que conheça exatamente os registros, ingredientes, quantidades e instruções presentes no conjunto de dados utilizado pelo sistema.

Para cada receita, serão considerados, quando disponíveis, os seguintes campos:

* identificador da receita;
* nome;
* lista de ingredientes;
* quantidade ou medida dos ingredientes;
* modo de preparo;
* número de porções;
* tempo de preparo;
* categoria ou tipo de refeição;
* fonte da receita;
* imagem, quando disponível.

Esses dados permitem que o agente considere não apenas a existência de uma receita, mas também fatores como disponibilidade dos ingredientes, quantidade de pessoas, tempo disponível e contexto da refeição.

A segunda fonte será uma **base de composição nutricional**, utilizando a **Tabela Brasileira de Composição de Alimentos (TBCA)**. Diferentemente da base de receitas, a TBCA será tratada como uma **base estruturada de composição nutricional**. Ela será utilizada para obter informações quantitativas dos alimentos, como energia, proteínas, carboidratos, lipídios, fibras, vitaminas e minerais, conforme a disponibilidade dos dados para cada alimento.

A TBCA é necessária porque esses valores são dados específicos de composição dos alimentos e não devem ser obtidos apenas a partir da estimativa do modelo de linguagem. A utilização de uma fonte estruturada permite que o cálculo nutricional das receitas seja baseado em dados externos e reproduzíveis.

Além da composição dos alimentos, serão utilizadas **diretrizes nutricionais da Organização Mundial da Saúde (OMS)** como fonte de conhecimento textual para a avaliação das recomendações. Entre as fontes previstas estão os materiais relacionados à alimentação saudável e à redução do consumo de sódio. Nesse caso, a necessidade de uma fonte externa está relacionada ao fato de que o agente deve utilizar diretrizes definidas por uma organização de referência, em vez de depender somente do conhecimento geral do modelo.

Por fim, o sistema utilizará informações de **preços dos alimentos** por meio de uma API Mock desenvolvida para o projeto. Essa fonte será necessária porque preços são informações dinâmicas e específicas do sistema. O modelo de linguagem não possui acesso confiável ao preço atual dos produtos utilizados pelo agente.

O conjunto de fontes especializadas, portanto, pode ser resumido da seguinte forma:

| Conhecimento            | Fonte                     | Motivo para ser externo           |
| ----------------------- | ------------------------- | --------------------------------- |
| Receitas                | Eight Portions / Kaggle   | Específico demais                 |
| Composição nutricional  | TBCA                      | Dados quantitativos específicos   |
| Diretrizes nutricionais | OMS                       | Informação normativa e específica |
| Estoque                 | Banco de dados do sistema | Privado e dinâmico                |
| Perfil do usuário       | Banco de dados do sistema | Privado e específico do usuário   |
| Preços                  | API Mock                  | Dinâmico e específico do sistema  |

O conhecimento pessoal do usuário, como perfil, estoque e histórico de recomendações, não será colocado como conhecimento geral no modelo. Essas informações pertencem ao estado do sistema e serão recuperadas conforme o usuário da solicitação.

---

## 2. Onde esses dados estão, e em que estado

As fontes serão mantidas em diferentes estruturas de acordo com a natureza da informação. A decisão de projeto é não utilizar uma única estratégia de armazenamento para todos os dados.

### Base de receitas

A base principal será o dataset de receitas do **Eight Portions**, com aproximadamente 125 mil receitas. O dataset será obtido a partir da fonte disponibilizada pelo projeto e armazenado para processamento e indexação. O dataset do Kaggle poderá ser utilizado como fonte complementar caso sejam necessários campos ou informações que não estejam adequadamente disponíveis na primeira fonte.

Os registros serão transformados para um formato padronizado antes da indexação. O objetivo é que diferentes formatos de origem produzam uma representação consistente para o agente.

A propriedade principal dessa fonte é que seu conteúdo é relativamente estável. A base poderá ser atualizada em versões futuras, mas não será alterada a cada solicitação do usuário.

### Base nutricional

A **TBCA** será utilizada como fonte da composição nutricional dos alimentos. Seus dados serão armazenados de forma estruturada, permitindo consultas por alimento e obtenção dos respectivos componentes nutricionais.

A representação seguirá a lógica de uma base de dados, e não de documentos textuais destinados exclusivamente à busca semântica. Dessa forma, uma consulta como "qual a quantidade de proteína do alimento X?" será resolvida por uma consulta estruturada.

A base será utilizada principalmente pelo módulo responsável pelo cálculo nutricional da receita.

### Diretrizes nutricionais

Os documentos da **OMS** relacionados à alimentação saudável, nutrição e redução de sódio serão mantidos como documentos textuais e poderão ser processados para recuperação semântica.

Diferentemente dos registros da TBCA, esses documentos possuem conteúdo explicativo e normativo, fazendo sentido recuperá-los a partir da similaridade semântica de uma pergunta ou critério de avaliação.

### Estoque e perfil

O estoque e o perfil serão armazenados em um **banco de dados SQL**.

O estoque terá informações como:

* usuário;
* alimento;
* quantidade;
* unidade;
* data de aquisição;
* validade, quando disponível.

O perfil poderá armazenar informações como:

* idade;
* altura;
* peso;
* objetivo;
* preferências alimentares;
* restrições;
* alergias;
* quantidade de refeições;
* rotina;
* equipamentos disponíveis.

Esses dados não serão transformados em documentos para um banco vetorial. São informações estruturadas, privadas e relacionadas diretamente ao usuário.

### Preços

Os preços serão disponibilizados por uma **API Mock** criada especificamente para o projeto. A API terá como objetivo simular uma fonte externa de preços, permitindo que o agente consulte o preço de determinado produto.

A API poderá retornar informações como:

* produto;
* preço;
* unidade;
* data da consulta;
* eventualmente histórico de preços.

A utilização da API Mock permite implementar e testar a funcionalidade sem depender de uma API comercial ou de dados reais de supermercados durante o desenvolvimento.

---

## 3. O que vai para o índice — e o que não vai

A base de conhecimento será dividida entre **informações adequadas para busca semântica** e **informações que devem ser recuperadas por consultas estruturadas**.

### 3.1 Base vetorial de receitas

As receitas serão indexadas em um **banco vetorial**.

A unidade básica de indexação será:

> **uma receita = um chunk.**

Assim, uma receita completa será mantida como uma unidade semântica, contendo seu nome, ingredientes, quantidades, modo de preparo e metadados relevantes.

A representação conceitual de um registro será:

```text
Receita: Salada de frutas

Ingredientes:
- banana
- maçã
- laranja
- mamão

Modo de preparo:
...

Porções: 2
Tempo de preparo: 10 minutos
Categoria: sobremesa
```

Essa decisão busca preservar o contexto completo da receita. Em vez de separar ingredientes e modo de preparo em chunks diferentes, todas as informações necessárias para compreender aquela receita permanecem juntas.

O embedding será construído a partir da representação textual da receita. Dessa forma, receitas semanticamente relacionadas tendem a ocupar regiões próximas no espaço vetorial. Por exemplo, receitas envolvendo banana e maçã poderão apresentar proximidade com receitas de salada de frutas ou outras preparações que utilizem ingredientes e conceitos semelhantes.

A busca vetorial, entretanto, não será responsável sozinha por verificar se o usuário realmente possui os ingredientes necessários.

O fluxo será separado em duas etapas:

```text
Pedido do usuário
        ↓
Interpretação dos ingredientes
        ↓
Consulta ao estoque SQL
        ↓
Ingredientes disponíveis
        ↓
Busca na base vetorial de receitas
        ↓
Receitas candidatas
        ↓
Agente-chef
```

Essa separação permite que a busca semântica encontre receitas relevantes enquanto o banco SQL continua sendo a fonte oficial do estoque do usuário.

### 3.2 Diretrizes da OMS

Os documentos textuais da OMS serão incluídos no índice semântico.

Nesse caso, a unidade de chunking seguirá a estrutura dos próprios documentos, utilizando seções ou subseções quando essa estrutura estiver disponível. O título ou cabeçalho da seção será herdado pelo chunk quando necessário para que o trecho faça sentido isoladamente.

Por exemplo:

```text
Documento: Healthy diet
Seção: Dietary patterns

[conteúdo da seção]
```

O objetivo é permitir que o agente nutricionista recupere trechos relacionados a critérios específicos de avaliação.

### 3.3 TBCA

A TBCA **não será tratada como uma base de chunks semânticos para os valores nutricionais**.

Os dados nutricionais serão mantidos de forma estruturada.

Por exemplo:

```text
alimento: frango
energia_kcal: ...
proteina_g: ...
carboidrato_g: ...
lipidio_g: ...
fibra_g: ...
sodio_mg: ...
```

Quando o agente precisar calcular a composição de uma receita, poderá identificar os alimentos e suas quantidades e consultar a TBCA.

Assim, uma pergunta como:

> "Quanto de proteína tem essa receita?"

será resolvida por consulta e cálculo estruturado, e não pela proximidade entre embeddings.

Essa separação também vale para o estoque, o perfil e os preços. Informações como quantidade, data, validade, preço e identificador são melhor representadas como dados estruturados.

### 3.4 Resumo da estratégia

| Fonte         | Índice vetorial |            Consulta estruturada |
| ------------- | --------------: | ------------------------------: |
| Receitas      |             Sim | Possíveis filtros por metadados |
| OMS           |             Sim |     Não é o mecanismo principal |
| TBCA          |             Não |                             Sim |
| Estoque       |             Não |                             Sim |
| Perfil        |             Não |                             Sim |
| API de preços |             Não |                             Sim |

Com aproximadamente 125 mil receitas, a utilização de um banco vetorial é adequada para recuperar um conjunto reduzido de receitas candidatas sem precisar comparar manualmente todo o conjunto em cada solicitação.

---

## 4. A estratégia de chunking

A estratégia de chunking será definida de acordo com o tipo de fonte, pois receitas, documentos nutricionais e dados estruturados possuem características diferentes.

### 4.1 Receitas

Para as receitas, a unidade natural será a própria receita. Portanto:

> **cada receita será um chunk no banco vetorial.**

O chunk conterá as informações necessárias para que a receita seja compreendida isoladamente:

```text
Nome da receita
Ingredientes
Quantidades
Modo de preparo
Porções
Tempo de preparo
Categoria
```

Além do conteúdo textual utilizado na representação semântica, cada registro possuirá metadados que poderão ser utilizados para filtros e etapas posteriores da recuperação:

```text
id
nome
categoria
porcoes
tempo_preparo
fonte
```

Quando aplicável, também poderão ser armazenadas características nutricionais calculadas posteriormente, mas esses valores não serão utilizados como substitutos da consulta à TBCA.

A escolha de uma receita como unidade de chunk evita separar informações que dependem umas das outras. Por exemplo, um trecho de modo de preparo isolado poderia perder o contexto dos ingredientes aos quais se refere. Mantendo a receita inteira no mesmo chunk, o resultado recuperado possui contexto suficiente para ser utilizado pelo agente-chef.

### 4.2 Documentos da OMS

Para os documentos da OMS, será utilizada a estrutura natural do documento.

Quando houver seções e subseções claramente definidas, cada seção relevante será utilizada como unidade de chunk. O cabeçalho correspondente será mantido junto ao conteúdo para evitar que o trecho fique sem contexto.

Caso uma seção seja excessivamente grande, ela poderá ser subdividida em partes menores, mantendo o cabeçalho da seção original em cada chunk.

O objetivo não é utilizar um tamanho arbitrário de caracteres para todos os documentos, mas preservar a estrutura semântica existente.

### 4.3 TBCA

A TBCA não terá uma estratégia tradicional de chunking para os dados de composição nutricional.

Cada alimento será tratado como um **registro estruturado**, contendo seus componentes nutricionais e respectivas unidades de medida. A consulta será realizada diretamente sobre esses registros.

A estrutura conceitual será:

```text
Alimento
├── identificação
├── energia
├── proteínas
├── carboidratos
├── lipídios
├── fibras
├── vitaminas
└── minerais
```

Essa abordagem permite realizar cálculos sobre quantidades diferentes das referências apresentadas na base. Por exemplo, caso a informação nutricional esteja expressa por 100 g e a receita utilize 200 g, o sistema poderá realizar a conversão e calcular a contribuição daquele alimento para a receita.

### 4.4 Metadados

Os metadados serão utilizados para complementar o conteúdo dos chunks e permitir filtros antes ou depois da busca semântica.

Para as receitas, os principais metadados serão:

| Metadado        | Finalidade                             |
| --------------- | -------------------------------------- |
| `id`            | Identificação da receita               |
| `categoria`     | Filtrar tipo de refeição               |
| `porcoes`       | Ajustar ao número de pessoas           |
| `tempo_preparo` | Considerar tempo disponível            |
| `fonte`         | Rastreabilidade                        |
| `ingredientes`  | Apoiar a correspondência com o estoque |

Para o estoque e a TBCA, os metadados permanecerão no banco estruturado, onde poderão ser utilizados diretamente em filtros e consultas.

Dessa forma, o sistema não utilizará busca semântica para resolver problemas que são essencialmente consultas a dados estruturados. A busca vetorial será utilizada principalmente quando a pergunta exigir **similaridade ou relevância semântica**, enquanto informações como quantidade, validade, preço, identificador e composição nutricional serão obtidas por consultas estruturadas.

## Síntese da versão 1

A base de conhecimento do agente será composta por diferentes fontes e mecanismos de recuperação. A **base de receitas**, com aproximadamente 125 mil registros, será indexada em banco vetorial, utilizando uma receita completa como unidade de chunk. A **TBCA** será utilizada como base estruturada de composição nutricional, enquanto as **diretrizes da OMS** serão utilizadas como documentos textuais para recuperação semântica. O **estoque e o perfil do usuário** serão armazenados em banco SQL, por se tratarem de dados estruturados e específicos de cada usuário. Os **preços** serão disponibilizados por uma API Mock, permitindo simular uma fonte dinâmica externa.

Essa separação evita aplicar uma única estratégia a todos os tipos de informação e permite que cada conhecimento seja recuperado pelo mecanismo mais adequado à sua natureza.
