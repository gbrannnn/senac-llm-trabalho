# Model card — Agente Nutricionista Pessoal

**Versão do documento:** 1.0.0 · **Data:** 16/10/2026 · **Commit descrito:** `d2eb10a` · **Exercício:** Aula 12 — Governança

> **Nota de 20/10/2026 (Parte 2).** Este card descreve o sistema **antes do código** (commit `d2eb10a`), e o texto abaixo continua valendo como registro daquele estado. A Parte 2 (commit `d16e6b7`) fechou parte das lacunas, com evidência:
> - **L05:** ferramentas implementadas, só de leitura, com lista por agente ([arquitetura.md §3.2](arquitetura.md#as-ferramentas)).
> - **L06:** `usuario_id` injetado pelo código ([ferramentas.py](../src/ferramentas.py) `Ctx`).
> - **L07:** alérgeno barrado por dois controles em código ([test_portao.py](../tests/test_portao.py)).
> - **L08:** escrita de estoque só soma, após aprovação.
> - **L09:** cada regra procedural registra aprovador e data no arquivo versionado ([regras_procedurais.md](../src/prompts/regras_procedurais.md)).
> - **L11:** orçamento em código ([config.py](../src/config.py), `estouro`).
> - **L13:** modelo local com digest registrado no log, sem envio a provedor ([modelos.md](modelos.md)).
> - **L14:** pausas para estoque e para remoção de alergia ([humano.md](humano.md)).
> - **L15:** escrita só depois de aprovar; prazo vencido não grava.
> - **L18:** `perfil.atualizar` não é ferramenta do modelo.
> - **L25:** perfil sem idade, peso, altura e rotina.
> - **L28 (parcial):** log JSONL com versões, ferramentas e saída ([registro.py](../src/registro.py)).
> - **L30:** remoção executada e verificada por varredura ([E05](evidencias/E05-remocao.txt)).
> - **L31 (parcial):** execuções reais em `logs/`.
>
> Continuam abertas, entre outras: **L01** (papéis), **L04** (idade e condição clínica), **L12** (gasto, sem sentido com modelo local), **L16** (interrupção), **L23** (consentimento), **L32** (juiz) e o expurgo automático do checkpoint ([memoria.md §5.4](memoria.md#54-como-o-agente-perde-a-memória)). A revisão completa do card fica para a Parte 3.

> **Como ler este documento.** Cada campo tem duas colunas: a **afirmação** e a
> **evidência** que a sustenta. A evidência é um caminho no repositório (arquivo
> e linha, saída de comando). Quando não há evidência, a afirmação traz a marca
> **LACUNA (Lnn)**, com o número da lacuna na [seção final](#lacunas).
>
> **O estado do sistema, em uma frase:** na versão `d2eb10a` o agente existe
> **só como desenho**. O repositório tem 6 arquivos, todos Markdown, e nenhum
> código, teste, prompt versionado, configuração ou registro de execução
> ([E01.1–E01.3](evidencias/E01-inventario-repositorio.txt)). Por isso, este
> documento separa sempre duas coisas:
>
> - **declarado** — o que os documentos de desenho dizem que o sistema fará; a
>   evidência é a linha do documento, e ela prova **a decisão**, não o
>   comportamento;
> - **aplicado** — o que um componente fora do modelo garante; a evidência
>   seria código, teste, permissão de plataforma ou registro. **Hoje nenhum
>   limite é aplicado**, e todo limite aparece como lacuna.

**Abreviações das evidências**

| Sigla | Arquivo |
|---|---|
| A | [docs/arquitetura-v1.md](arquitetura-v1.md) |
| B | [docs/base-de-conhecimento-v1.md](base-de-conhecimento-v1.md) |
| M | [docs/memoria-v1.md](memoria-v1.md) |
| V | [docs/aula-11-avaliacao.md](aula-11-avaliacao.md) |
| G | [docs/grupo.md](grupo.md) |
| E01 | [docs/evidencias/E01-inventario-repositorio.txt](evidencias/E01-inventario-repositorio.txt) — saídas de comando sobre o repositório |

Uma referência como `A:13` significa *arquivo A, linha 13*.

---

## 1. Identificação

| Afirmação | Evidência |
|---|---|
| Nome: **Agente Nutricionista Pessoal**. | [A:1](arquitetura-v1.md?plain=1#L1) |
| Versão do sistema: **v1 (desenho)**, correspondente ao commit `d2eb10a`. Não existe *tag* nem número de versão do software, porque não existe software. | [E01.1–E01.2](evidencias/E01-inventario-repositorio.txt), [E01.6](evidencias/E01-inventario-repositorio.txt) |
| Data desta versão: 09/10/2026 (último commit) · data do documento: 16/10/2026. | [E01.6](evidencias/E01-inventario-repositorio.txt) |
| Equipe responsável: Daniel de Araujo Carvalho, Eduardo Dias Santos, Gabriel Brandão Vehchani de Freitas, Pedro Henrique Gomes. | [G:2-5](grupo.md?plain=1#L2-L5) |
| **Quem responde quando algo dá errado** (um nome por papel: produto, desenvolvimento, operação, risco). | **LACUNA (L01)** — os documentos listam o grupo, mas não atribuem papéis. Uma lista de quatro nomes sem papel é a "coluna *responde* ambígua" da matriz de responsabilidade. |

## 2. Finalidade

| Afirmação | Evidência |
|---|---|
| O agente **recomenda refeições** a partir do estoque doméstico e do perfil do usuário, e **mantém o estoque** a partir de foto ou nota fiscal. Atende o próprio usuário final, que sempre inicia a interação. | [A:7](arquitetura-v1.md?plain=1#L7), [A:13](arquitetura-v1.md?plain=1#L13) |
| Executa três tipos de pedido: recomendação (~55%), atualização de estoque por imagem (~30%) e atualização de perfil (~10%). | [A:9](arquitetura-v1.md?plain=1#L9) — estimativa de desenho, **não medida** (L02) |
| **Fora de escopo:** diagnóstico, tratamento de condição clínica, prescrição de suplementação, substituição de acompanhamento médico e qualquer assunto que não seja nutrição (por exemplo, investimentos). | declarado em [A:13](arquitetura-v1.md?plain=1#L13) e [A:51](arquitetura-v1.md?plain=1#L51); casos de teste planejados [V:30-32](aula-11-avaliacao.md?plain=1#L30-L32) (C17–C19). Aplicado **só pelo prompt e pelo roteador LLM** → **LACUNA (L03)** |
| **Fora de escopo da v1:** descontar do estoque os itens de uma receita "cozinhada" (única ação de efeito potencialmente irreversível). | [A:119](arquitetura-v1.md?plain=1#L119) |
| **Classificação regulatória.** Não é sistema de alto risco no sentido do AI Act (recomendação de refeição doméstica, sem decisão sobre emprego, crédito ou acesso a serviço essencial). Quanto ao ECA Digital, o sistema **pode** ser usado por adolescentes, porque nada impede o cadastro. | justificativa do grupo, sem evidência no sistema. A ausência de verificação de idade é **LACUNA (L04)** |

## 3. Autoridade

Formato da [nota sobre governar a ação, §8](https://github.com/celsocrivelaro/senac-agentes-llm/blob/main/aula-12-governanca/notas-de-aula/01-governar-a-acao.md).
A coluna **Onde deveria ser aplicado** é a decisão de projeto. A coluna
**Aplicado hoje?** responde com evidência ou com lacuna.

| Item | Especificação | Onde deveria ser aplicado | Aplicado hoje? |
|---|---|---|---|
| **Escopo — ferramentas** | Oito ferramentas: `estoque.consultar`, `estoque.extrair_da_imagem`, `perfil.consultar`, `receitas.buscar`, `nutricional.calcular` (leitura); `estoque.atualizar`, `perfil.atualizar`, `recomendacao.registrar` (escrita idempotente, reversível). Declarado em [A:17-26](arquitetura-v1.md?plain=1#L17-L26). **Revisão contra a necessidade:** ver §3.1, com três privilégios a remover. | lista de ferramentas por subagente, no código | **Não.** Nenhuma ferramenta implementada ([E01.3](evidencias/E01-inventario-repositorio.txt)) → **LACUNA (L05)** |
| **Escopo — dados** | O agente só lê e escreve dados do **usuário da sessão**. Nunca lê perfil, estoque ou histórico de outro usuário. Declarado como propriedade a testar em [V:26](aula-11-avaliacao.md?plain=1#L26) (C13). | **código**: `usuario_id` vem da sessão autenticada, nunca de argumento gerado pelo modelo · **plataforma**: *row-level security* por `usuario_id` | **Não.** As ferramentas declaradas recebem `usuario_id` como argumento ([A:19-26](arquitetura-v1.md?plain=1#L19-L26)), ou seja, o modelo escolheria de quem são os dados → **LACUNA (L06)** |
| **Ação proibida — prescrever, diagnosticar, tratar** | Recusa. | **prompt** ([A:13](arquitetura-v1.md?plain=1#L13)) + **roteador LLM** ([A:51](arquitetura-v1.md?plain=1#L51)) | **Só prompt.** O modelo pode desobedecer → **LACUNA (L03)** |
| **Ação proibida — recomendar receita com alérgeno ou restrição do perfil** | Nenhuma receita aprovada pode conter ingrediente que conste em `perfil.alergias`/`restricoes`. Declarado como propriedade determinística em [V:44](aula-11-avaliacao.md?plain=1#L44) e caso crítico C05 [V:18](aula-11-avaliacao.md?plain=1#L18). | **código**: filtro determinístico antes de `recomendacao.registrar` e do RETORNO; o avaliador LLM ([A:63-65](arquitetura-v1.md?plain=1#L63-L65)) **não** é o controle | **Não.** No desenho, quem verifica é o avaliador LLM → **LACUNA (L07)**, a mais grave |
| **Ação proibida — descontar estoque por consumo** | Fora da v1. | **ausência de ferramenta**: não há ferramenta de "consumir" ([A:17-26](arquitetura-v1.md?plain=1#L17-L26), [A:119](arquitetura-v1.md?plain=1#L119)) | **Parcial.** A ausência está na lista declarada, mas `estoque.atualizar(usuario_id, itens)` aceita qualquer quantidade e poderia ser usada para zerar itens → **LACUNA (L08)** |
| **Ação proibida — alterar a memória procedural (regras no prompt)** | Só um humano promove uma regra. | **ausência de ferramenta**: nenhuma das oito ferramentas escreve no prompt ([A:17-26](arquitetura-v1.md?plain=1#L17-L26)); processo de curadoria em [M:108](memoria-v1.md?plain=1#L108) | **Declarado.** A ausência pode ser conferida na lista de ferramentas. O processo de curadoria não tem registro (quem aprovou qual regra) → **LACUNA (L09)** |
| **Ação proibida — enviar dados a terceiros** | O agente não envia e-mail, mensagem nem chama API externa com dado do usuário. | **ausência de ferramenta**: nenhuma ferramenta de envio em [A:17-26](arquitetura-v1.md?plain=1#L17-L26) | **Declarado.** Exceção não declarada: o próprio provedor do modelo recebe o dado (ver §5 e §6) |
| **Credencial** | Conta de serviço própria do agente: leitura nas tabelas `estoque`, `perfil`, `historico`; escrita só em `estoque`, `historico` e campos não sensíveis de `perfil`; nenhum acesso a DDL nem a outras bases; segredo fora do repositório. | **plataforma** (permissões do banco, cofre de segredos) | **Não definida** ([E01.5](evidencias/E01-inventario-repositorio.txt): nenhuma ocorrência de "credencial") → **LACUNA (L10)** |
| **Limite por execução** | 5 passos do chef, 3 rodadas de avaliação, 3 passos de estoque, 6.000 tokens, *timeout* de 15 s no texto. Declarado em [A:31-35](arquitetura-v1.md?plain=1#L31-L35) e repartição em [M:63-69](memoria-v1.md?plain=1#L63-L69). | **código** (`Orcamento` do agente) + teste | **Não.** Sem código nem teste → **LACUNA (L11)** |
| **Limite de gasto por janela** | Não especificado. Não há valor em reais nem por dia/mês nem chave exclusiva. | **plataforma** (limite do provedor) + código | **LACUNA (L12)** — [E01.5](evidencias/E01-inventario-repositorio.txt) |
| **Modelos aprovados / reserva** | Não especificado. | ponto de aplicação | **LACUNA (L13)** — ver §5 |
| **Limiar de aprovação humana** | A v1 **não pausa nenhuma ação** para aprovação ([M:39-41](memoria-v1.md?plain=1#L39-L41)). Proposta desta versão: pausar para **confirmação do próprio usuário** (1) a remoção de uma alergia ou restrição do perfil e (2) a gravação de itens de estoque ambíguos (C07, [V:20](aula-11-avaliacao.md?plain=1#L20)). | código (término "aguardando confirmação") | **Não.** Nenhuma pausa existe → **LACUNA (L14)**. A ausência de aprovação por recomendação é um **risco aceito** (R1, §9) |
| **Comportamento quando um controle falha** | Proposta: *fail-closed* para as escritas e para o filtro de alergia (sem filtro, nenhuma recomendação sai); *fail-open* com registro para leitura de receitas e OMS. | código | **Não declarado** antes desta versão → **LACUNA (L15)** |
| **Quem pode suspender o agente** | Não especificado. Proposta: o responsável de operação desativa a chave do agente; o responsável de produto decide a retomada. | código (*kill switch*) + plataforma (revogar credencial) | **LACUNA (L16)**, depende de L01 |
| **Revisão de autoridade** | Não especificado. Proposta: a cada ferramenta ou permissão nova, comparar a autoridade efetiva com esta tabela. | processo | **LACUNA (L17)** |

### 3.1 Ferramentas e credenciais contra o que o agente precisa

| Privilégio declarado | Precisa? | Decisão |
|---|---|---|
| `perfil.atualizar(usuario_id, campo, valor)` disponível ao agente | **Não.** A rota "perfil" grava **por regra em código, sem LLM** ([A:50](arquitetura-v1.md?plain=1#L50), [M:104](memoria-v1.md?plain=1#L104)). Além disso, `campo` livre permite ao modelo apagar `alergias`. | **Remover** do conjunto do agente. Fica só no código da rota de perfil (L18). |
| `usuario_id` como argumento de toda ferramenta | **Não.** O usuário é conhecido pela sessão. | **Remover** o argumento e injetar o valor no código (L06). |
| `estoque.atualizar` visível ao agente-chef e ao avaliador | **Não.** Só o agente-estoque escreve estoque ([A:53-56](arquitetura-v1.md?plain=1#L53-L56)). | **Restringir** a lista de ferramentas por subagente (L05). |
| API Mock de preços | Citada como fonte ([B:30](base-de-conhecimento-v1.md?plain=1#L30)), mas **sem ferramenta** na arquitetura ([A:17-26](arquitetura-v1.md?plain=1#L17-L26)). | **Inconsistência** entre documentos. Declarar se entra ou não (L19). |

## 4. Ferramentas e integrações

| Ferramenta | Permissão | Quem usa | Evidência |
|---|---|---|---|
| `estoque.consultar` | leitura (estoque do usuário) | consulta (etapa 4) | [A:19](arquitetura-v1.md?plain=1#L19) |
| `estoque.extrair_da_imagem` | leitura + **envio da imagem a serviço de visão** (terceiro) | agente-estoque | [A:20](arquitetura-v1.md?plain=1#L20). O destino da imagem não foi declarado → L20 |
| `estoque.atualizar` | escrita, *upsert* usuário+item | agente-estoque | [A:21](arquitetura-v1.md?plain=1#L21) |
| `perfil.consultar` | leitura (inclui dado de saúde) | consulta, chef, avaliador | [A:22](arquitetura-v1.md?plain=1#L22) |
| `perfil.atualizar` | escrita (inclui dado de saúde) | **a remover do agente** (§3.1) | [A:23](arquitetura-v1.md?plain=1#L23) |
| `receitas.buscar` | leitura no índice vetorial | agente-chef | [A:24](arquitetura-v1.md?plain=1#L24), [B:121-174](base-de-conhecimento-v1.md?plain=1#L121-L174) |
| `nutricional.calcular` | função determinística sobre a TBCA | avaliador | [A:25](arquitetura-v1.md?plain=1#L25) |
| `recomendacao.registrar` | escrita, *upsert* usuário+dia | etapa 7 | [A:26](arquitetura-v1.md?plain=1#L26) |
| Busca de diretrizes OMS | leitura no índice vetorial | avaliador | descrita em [B:176-191](base-de-conhecimento-v1.md?plain=1#L176-L191), **sem ferramenta nomeada** na arquitetura → L19 |
| **Servidores MCP** | nenhum declarado | — | [E01.3](evidencias/E01-inventario-repositorio.txt) (nenhum arquivo de configuração) |
| **Outros agentes (A2A)** | nenhum externo; os subagentes (estoque, chef, avaliador) são internos e herdam a mesma credencial | — | [A:43-65](arquitetura-v1.md?plain=1#L43-L65). Credencial compartilhada → L10 |

Todas as linhas acima são **declaradas**. Nenhuma ferramenta está implementada → **LACUNA (L05)**.

## 5. Modelo e provedor

| Afirmação | Evidência |
|---|---|
| Modelo (versão datada, não *alias*) | **LACUNA (L13).** Nenhum modelo foi escolhido ([E01.4](evidencias/E01-inventario-repositorio.txt): 0 ocorrências de nome de modelo ou provedor). |
| Modelo de visão para `extrair_da_imagem` | **LACUNA (L20).** |
| Modelo de *embedding* do índice de receitas e da OMS | **LACUNA (L21).** Sem ele, a versão do índice não é reproduzível ([M:186-192](memoria-v1.md?plain=1#L186-L192)). |
| Provedor e região de processamento | **LACUNA (L13).** Como o perfil contém dado de saúde (§6), a região determina se há **transferência internacional** (LGPD, art. 33). |
| Retenção no provedor e uso para treino | **LACUNA (L13).** Requisito do grupo: o provedor não pode usar os dados para treino e deve reter por, no máximo, o prazo de monitoramento de abuso. |
| Parâmetros de amostragem | Planejados `temperature=0`, `top_p=1` para avaliação ([V:72](aula-11-avaliacao.md?plain=1#L72)). Em produção, não definidos → L13. |

## 6. Dados

### 6.1 Fontes não pessoais

| Fonte | Estado | Evidência |
|---|---|---|
| Receitas Eight Portions (~125 mil), complemento Kaggle | declarada, não ingerida | [B:7](base-de-conhecimento-v1.md?plain=1#L7), [B:53](base-de-conhecimento-v1.md?plain=1#L53), [E01.1](evidencias/E01-inventario-repositorio.txt). Licença de uso **não verificada** → L22 |
| TBCA (composição nutricional) | declarada, não ingerida | [B:24](base-de-conhecimento-v1.md?plain=1#L24). Licença não verificada → L22 |
| Diretrizes da OMS | declaradas, com `data_publicacao` como metadado | [B:28](base-de-conhecimento-v1.md?plain=1#L28), [M:127-130](memoria-v1.md?plain=1#L127-L130) |
| API Mock de preços | declarada, sem ferramenta | [B:103](base-de-conhecimento-v1.md?plain=1#L103) → L19 |

### 6.2 Inventário do dado pessoal: onde entra, onde fica, para onde vai

**Classificação.** Alergias, restrições alimentares, peso, altura e objetivo
de saúde ("emagrecimento") são **dado pessoal sensível referente à saúde**
(LGPD, art. 5º, II). A base legal para eles é o **art. 11**, não o art. 7º: o
único inciso aplicável a um app de consumo é o **consentimento específico e
destacado** (art. 11, I). Os demais dados pessoais (estoque, histórico,
identificador) se apoiam na **execução de contrato** com o usuário (art. 7º, V).

Base legal e prazos abaixo são **decisões propostas por este documento**. O
sistema não tem tela de consentimento nem rotina de expurgo → **LACUNA (L23)**.

| Lugar | Dado pessoal | Finalidade | Base legal | Prazo de guarda | Evidência | Minimização |
|---|---|---|---|---|---|---|
| **Entrada — texto** | pedido livre; pode trazer dado de saúde não pedido ("sou diabético") | entender o pedido | art. 7º, V; art. 11, I se houver saúde | duração da execução | [A:5-9](arquitetura-v1.md?plain=1#L5-L9) | ok, se não for copiado para outro lugar |
| **Entrada — imagem** (foto, nota fiscal) | foto da casa; **nota fiscal pode conter nome, CPF, endereço e final do cartão** | extrair itens | art. 7º, V | **não retida** após a extração | [M:214-216](memoria-v1.md?plain=1#L214-L216) | ⚠ **Fere.** O CPF e os demais dados não servem à finalidade e não são mascarados antes do envio ao modelo de visão → L24 |
| **Prompt → provedor externo** (LLM e visão) | pedido, perfil completo (inclui saúde), estoque, histórico recente, imagem | gerar e avaliar a receita | art. 11, I (saúde) + art. 33 se houver transferência internacional | o do provedor | [M:63-69](memoria-v1.md?plain=1#L63-L69) (o perfil entra na janela) | ⚠ **Fere.** Idade, peso, altura e rotina vão ao provedor mesmo quando o pedido não precisa deles. Provedor e retenção desconhecidos → L13, L25 |
| **SQL `perfil`** | idade, altura, peso, objetivo, preferências, **restrições, alergias**, refeições, rotina, equipamentos | personalizar e impedir alérgeno | art. 11, I (saúde); art. 7º, V (demais) | enquanto a conta existir; apagado a pedido | [B:86-97](base-de-conhecimento-v1.md?plain=1#L86-L97), remoção em [M:167](memoria-v1.md?plain=1#L167) | ⚠ **Fere.** Nenhuma ferramenta, regra ou caso de avaliação usa `idade`, `altura`, `peso` nem `rotina` ([A:17-26](arquitetura-v1.md?plain=1#L17-L26), [V:14-33](aula-11-avaliacao.md?plain=1#L14-L33)). Coletar só quando houver finalidade (L25) |
| **SQL `estoque`** | itens, quantidades, datas de compra (revelam hábito de consumo) | recomendar com o que existe | art. 7º, V | enquanto a conta existir | [B:77-84](base-de-conhecimento-v1.md?plain=1#L77-L84) | ok |
| **Histórico de recomendações** (SQL + índice vetorial) | receita, data, kcal, rejeição implícita, **embedding do par pedido+receita** | não repetir receita; inferir preferência | art. 7º, V | **sem prazo final**: após 90 dias é rebaixado, **não removido** | [M:91](memoria-v1.md?plain=1#L91), [M:140-152](memoria-v1.md?plain=1#L140-L152) | ⚠ **Fere.** Guarda por tempo indefinido. A finalidade declarada ("não repetir receita recente") se esgota em 90 dias → L26 |
| **Checkpoint** | `usuario_id`, `entrada_bruta`, `estoque_snapshot`, **`perfil_snapshot` (saúde)** | retomar e depurar | art. 7º, V | "prazo curto", **não fixado** | [M:25](memoria-v1.md?plain=1#L25), [M:46](memoria-v1.md?plain=1#L46), [M:52-55](memoria-v1.md?plain=1#L52-L55) | ⚠ **Fere.** (1) prazo não definido; (2) duplica o perfil de saúde inteiro; (3) `entrada_bruta` guarda "referência à imagem", o que contradiz "imagem não retida" ([M:214](memoria-v1.md?plain=1#L214)): se há referência, a imagem está guardada em algum lugar → L27 |
| **Registro de execução (logs/trace)** | argumentos das ferramentas com `usuario_id`; formato do restante não definido | prova e depuração | art. 7º, V e art. 7º, IX (legítimo interesse, para segurança) | **não fixado** | [M:171](memoria-v1.md?plain=1#L171) | ⚠ Prazo e conteúdo não definidos → L28 |
| **Memória procedural** (texto no prompt) | nenhum, por regra (regras são gerais, curadas) | — | — | até revisão | [M:93](memoria-v1.md?plain=1#L93), [M:172](memoria-v1.md?plain=1#L172) | ok, mas depende de curadoria sem registro (L09) |
| **Golden dataset de avaliação** | nenhum hoje (todos sintéticos) | avaliação | — | — | [V:35](aula-11-avaliacao.md?plain=1#L35) | ⚠ O plano é incluir "incidentes reais anonimizados". A anonimização precisa de procedimento verificável → L29 |

**Remoção a pedido do titular** (LGPD, art. 18, VI): o procedimento cobre perfil,
estoque, histórico, checkpoints, logs e memória procedural, e tem verificação
por `usuario_id` sintético ([M:165-181](memoria-v1.md?plain=1#L165-L181)). **Não
foi executado nenhuma vez.** Também não cobre a cópia no provedor externo nem
o golden dataset → **LACUNA (L30)**.

## 7. Avaliação

| Afirmação | Evidência |
|---|---|
| Suíte: golden dataset **v1.0.0**, 20 casos sintéticos em 5 classes; rubrica do juiz **v1.0.0**. | [V:3](aula-11-avaliacao.md?plain=1#L3), [V:14-35](aula-11-avaliacao.md?plain=1#L14-L35) |
| Métrica: `pass^5` por caso, `macro_pass^5` por classe; regra de promoção fixada em 09/10/2026, antes dos resultados. | [V:74-76](aula-11-avaliacao.md?plain=1#L74-L76) |
| **Resultados agregados e por fatia** | **LACUNA (L31).** "Nenhuma execução ou taxa de acerto é alegada" ([V:4](aula-11-avaliacao.md?plain=1#L4)). |
| **Concordância juiz × humano** | **LACUNA (L32).** Protocolo planejado (40 saídas, limiar ≥90%), "nada foi medido ainda" ([V:66](aula-11-avaliacao.md?plain=1#L66)). |
| Revisão nutricional humana do gabarito | **LACUNA (L33).** "Falta revisão humana, especialmente nutricional" ([V:35](aula-11-avaliacao.md?plain=1#L35)). |

## 8. Limites conhecidos

**Modos de falha observados:** nenhum, porque o sistema nunca foi executado →
**LACUNA (L31)**. A lista abaixo traz **modos de falha previstos no desenho**,
cada um com o caso de teste que o exercitaria.

| Limite previsto | Evidência |
|---|---|
| Estoque muito restrito pode esgotar 3 rodadas sem receita aprovada. | [A:123](arquitetura-v1.md?plain=1#L123) |
| Item ambíguo ("leite") pode ser casado com a variante errada. | [V:20](aula-11-avaliacao.md?plain=1#L20) (C07) |
| Ingrediente ausente na TBCA impede o cálculo; o agente pode inventar kcal. | [V:29](aula-11-avaliacao.md?plain=1#L29) (C16) |
| Texto de receita recuperada pode conter instrução maliciosa (injeção indireta). | [V:33](aula-11-avaliacao.md?plain=1#L33) (C20) |
| Mesmo pedido gera respostas diferentes conforme a memória muda; não é reproduzível sem *snapshot*. | [M:196-209](memoria-v1.md?plain=1#L196-L209) |

**Casos em que o agente não deve ser usado, mesmo dentro da finalidade:**
alergia com histórico de anafilaxia, doença que exige dieta terapêutica
(diabetes, doença renal, transtorno alimentar), gestação e usuários menores de
18 anos. São decisões do grupo. O sistema não pergunta nem bloqueia nenhum
desses casos → **LACUNA (L04)**.

## 9. Riscos aceitos

Cada risco traz a razão e o que o limita. A coluna **Registro** diz se a
aceitação já estava documentada antes deste *model card*. Os riscos que só
aparecem aqui ainda precisam do aceite formal do responsável de risco (L01) →
**LACUNA (L34)**.

| ID | Risco | Razão para aceitar | O que o limita | Registro |
|---|---|---|---|---|
| R1 | Nenhuma recomendação passa por aprovação humana antes de chegar ao usuário. | A ação é uma sugestão. O usuário decide se cozinha, e nenhuma escrita é irreversível. | Filtro determinístico de alergia (**ainda não existe**, L07). **Sem L07 resolvida, R1 não pode ser aceito.** | [M:39-41](memoria-v1.md?plain=1#L39-L41), [A:119](arquitetura-v1.md?plain=1#L119) |
| R2 | Entre a remoção lógica (*tombstone*) e a reconstrução do índice vetorial, o vetor de um titular removido ainda influencia buscas. | Custo de reconstruir o índice a cada pedido. | Janela de manutenção do índice (prazo **não fixado**, L30). | [M:186-192](memoria-v1.md?plain=1#L186-L192) |
| R3 | O sistema não é reproduzível sobre o estado de produção. | É consequência deliberada da memória. | Avaliação roda sobre *snapshots* congelados. | [M:196-209](memoria-v1.md?plain=1#L196-L209), [V:72](aula-11-avaliacao.md?plain=1#L72) |
| R4 | O roteador LLM pode deixar passar um pedido fora de escopo (falso negativo). | Um classificador de conteúdo sempre tem falso negativo. | Ausência de ferramenta de prescrição e de envio: no pior caso, o dano é **texto**, não ação. Mitigação de texto = L03. | só neste documento |
| R5 | Valores de kcal e proteína podem divergir do real por imprecisão da TBCA e das quantidades. | Limite da fonte. | Resposta cita a ferramenta e não arredonda para "exato" (C14, C16). | só neste documento |

## 10. Supervisão humana

| Afirmação | Evidência |
|---|---|
| Nenhuma ação do fluxo pausa para aprovação humana na v1. | [M:39-41](memoria-v1.md?plain=1#L39-L41) |
| O único ponto com humano é a **curadoria da memória procedural**: uma regra aprendida só vale depois de revisão humana. | [M:93](memoria-v1.md?plain=1#L93), [M:104-110](memoria-v1.md?plain=1#L104-L110). Quem cura, em que prazo e onde fica o registro → **LACUNA (L09)** |
| Supervisão *on-the-loop*: alguém monitora negações, gasto e recusas. | **LACUNA (L16, L28).** Não há painel, alerta nem responsável. |
| Interrupção: quem pode, como, em que estado o sistema fica, como se testa. | **LACUNA (L16).** Nenhum dos quatro itens está definido nem foi exercitado. |

## 11. Registro e retenção

| Afirmação | Evidência |
|---|---|
| O checkpoint de cada execução registra entrada bruta, snapshots de estoque e perfil, receita de cada rodada, contadores e veredito com motivo. | declarado em [M:45-55](memoria-v1.md?plain=1#L45-L55) |
| O descarte de um trecho antigo da OMS é registrado no log da avaliação. | declarado em [M:132-137](memoria-v1.md?plain=1#L132-L137) |
| **O registro de decisão completo** R = (id, t, x, C, V, Φ, P, H, y): a versão do modelo **pedido e servido**, do prompt e do índice; a política avaliada; a revisão humana, inclusive a ausência registrada; o `recomendacao_id` citado na resposta ao usuário. | **LACUNA (L28).** O checkpoint não tem versões (V), política (P) nem revisão (H). A resposta ao usuário ([A:105](arquitetura-v1.md?plain=1#L105)) não cita identificador. |
| Prazo de guarda do registro. | **LACUNA (L28).** Proposta: 90 dias, igual à janela de histórico útil, com eliminação registrada. |
| Quem tem acesso ao registro; armazenamento *append-only*. | **LACUNA (L28).** |
| Exemplo de execução real registrada. | **LACUNA (L31).** Não existe nenhuma ([E01.2](evidencias/E01-inventario-repositorio.txt)). |

## 12. Histórico de mudanças

| Versão | Data | O que mudou | Autor do commit | Aprovou |
|---|---|---|---|---|
| `9e9eafd` | 11/09/2026 | Arquitetura v1 | Gabriel B. V. de Freitas | — |
| `285c61c` | 11/09/2026 | README e lista do grupo | Gabriel B. V. de Freitas | — |
| `ff4beba` | 18/09/2026 | Base de conhecimento v1 | Pedro Henrique Gomes | — |
| `212e970` | 25/09/2026 | Memória | Gabriel B. V. de Freitas | — |
| `d2eb10a` | 09/10/2026 | Plano de avaliação (golden dataset v1.0.0, rubrica v1.0.0) | Gabriel B. V. de Freitas | — |
| *(este commit)* | 16/10/2026 | *Model card* v1.0.0 e evidência E01 | Pedro Henrique Gomes | — |

Evidência: [E01.6](evidencias/E01-inventario-repositorio.txt). O autor do commit
não é necessariamente o autor do conteúdo, que é do grupo. **Ninguém aprova as
mudanças:** os commits vão direto para `main`, sem *pull request* nem revisão →
**LACUNA (L35)**.

---

## Lacunas

Prioridade: **P0** impede afirmar que o agente é seguro para uso, **P1** impede
auditar uma decisão, **P2** é melhoria de governança.

| ID | Lacuna | Correção proposta | Prioridade |
|---|---|---|---|
| L07 | Alérgeno barrado só pelo avaliador LLM | Função determinística `checar_alergenos(receita, perfil)` antes de registrar e de responder, *fail-closed*, com teste unitário para C05 e C11 | **P0** |
| L06 | `usuario_id` é argumento escolhido pelo modelo | Injetar o `usuario_id` da sessão no código; *row-level security* no banco; teste C13 | **P0** |
| L05 | Nenhuma ferramenta implementada; sem lista por subagente | Implementar as ferramentas com a lista restrita por subagente (§3.1) e teste que confere a lista | **P0** |
| L18 | `perfil.atualizar` com campo livre exposto ao agente | Remover do agente e manter só na rota de perfil em código | **P0** |
| L23 | Sem consentimento para dado de saúde | Tela de consentimento específico (art. 11, I) antes do primeiro cadastro de alergia ou peso, com registro do aceite | **P0** |
| L04 | Sem barreira de idade nem de condição clínica | Pergunta de idade no cadastro e recusa para menores de 18; aviso e recusa para os casos da §8 | **P0** |
| L13 | Modelo, provedor, região, retenção e treino não definidos | Escolher modelo com versão datada; registrar provedor, região e termos (*zero retention*/sem treino) | **P0** |
| L24 | Nota fiscal com CPF vai ao modelo de visão | Mascarar CPF, nome e cartão antes do envio; teste com nota fiscal sintética | P1 |
| L25 | Perfil inteiro (idade, peso, altura, rotina) no prompt e sem uso | Enviar só os campos que a etapa usa; deixar de coletar os campos sem finalidade | P1 |
| L26 | Histórico sem prazo final | Expurgo após 90 dias, ou nova finalidade declarada para guardar mais | P1 |
| L27 | Checkpoint sem prazo, com perfil de saúde, e contradição sobre a imagem | Fixar prazo (ex.: 7 dias), guardar hash e não cópia do perfil, apagar a imagem após extração e corrigir M:46 | P1 |
| L28 | Registro de decisão incompleto (sem V, P, H, id ao usuário, prazo, acesso) | Definir o *schema* do trace; citar `recomendacao_id` na resposta; prazo de 90 dias; *append-only*; acesso só para operação e risco | P1 |
| L31 | Nenhuma execução, resultado nem modo de falha observado | Rodar a suíte da Aula 11 e versionar os traces em `doc/evidencias/` | P1 |
| L32 | Concordância do juiz não medida | Executar o protocolo de 40 saídas e publicar a matriz 2×2 | P1 |
| L03 | Recusa de prescrição e diagnóstico só no prompt | Classificador de saída com padrões (dose, "diagnóstico", suplemento) além do prompt; teste C17 e C18. Continua sendo redução, não garantia (R4) | P1 |
| L11 | Orçamento por execução sem código | Classe `Orcamento` com os tetos de A:31-35 e teste que força o quarto ciclo de avaliação | P1 |
| L08 | `estoque.atualizar` pode zerar itens | Aceitar só incremento ou valor vindo da extração; zerar exige confirmação do usuário | P1 |
| L10 | Credencial não definida; subagentes compartilham a mesma | Conta de serviço com os privilégios da §3; segredo em cofre | P1 |
| L14 | Nenhuma pausa para confirmação | Término "aguardando confirmação" para remover alergia e para item ambíguo | P1 |
| L15 | Comportamento em falha de controle não definido | Implementar *fail-closed* nas escritas e no filtro de alergia, com teste | P1 |
| L16 | Interrupção não definida nem testada | *Kill switch* por chave, responsável nomeado e exercício de desligamento registrado | P1 |
| L01 | Responsáveis sem papel | Atribuir um integrante a cada papel (produto, desenvolvimento, operação, risco) neste documento | P1 |
| L30 | Remoção de titular nunca executada; não cobre provedor nem dataset | Executar a verificação de M:177 com usuário sintético e salvar a saída como E02 | P1 |
| L12 | Sem limite de gasto por janela | Chave exclusiva; limite diário e mensal no provedor; alerta a 80% | P2 |
| L09 | Curadoria da memória procedural sem registro | Arquivo versionado de regras, em que cada regra tem aprovador e data | P2 |
| L19 | API de preços e busca OMS sem ferramenta declarada | Declarar as ferramentas ou retirar as fontes | P2 |
| L20 | Modelo de visão e destino da imagem não definidos | Junto com L13 | P2 |
| L21 | Modelo de *embedding* não definido | Fixar o modelo e o *hash* do índice | P2 |
| L22 | Licenças das bases não verificadas | Conferir as licenças do Eight Portions, do Kaggle e da TBCA e registrar | P2 |
| L29 | Anonimização futura do dataset sem procedimento | Definir o procedimento antes de incluir caso real | P2 |
| L33 | Gabarito sem revisão nutricional | Revisão por nutricionista ou docente, registrada | P2 |
| L34 | Riscos R4 e R5 sem aceite formal | Aceite assinado pelo responsável de risco (depende de L01) | P2 |
| L35 | Mudanças sem aprovação | *Pull request* com revisão de outro integrante para cada mudança em `main` | P2 |
| L02 | Distribuição de pedidos estimada, não medida | Medir nos traces depois das primeiras execuções | P2 |
| L17 | Sem revisão periódica de autoridade | Revisar esta tabela a cada ferramenta nova e ao fim de cada aula | P2 |

---

## Resposta à questão do exercício

> *Um auditor que nunca falou com o grupo, com o model card e o repositório na
> mão, consegue decidir se uma decisão concreta do agente estava dentro da
> autoridade dele?*

**Hoje, não.** Faltam as duas coisas de que a decisão depende.

1. **Não existe decisão concreta para auditar.** O repositório não tem código
   nem registro de execução ([E01.2](evidencias/E01-inventario-repositorio.txt)).
   Sem um registro R com identificador citado na resposta ao usuário (L28,
   L31), o auditor não tem por onde começar.
2. **A autoridade está declarada, mas não aplicada.** Com este documento, o
   auditor sabe o que o agente *deveria* poder fazer (§3) e consegue conferir
   cada linha contra o documento de desenho. Mas os limites que importam
   dependem só do modelo ou não existem: alérgeno (L07), isolamento entre
   usuários (L06), recusa clínica (L03). Uma recomendação que estivesse "dentro
   da autoridade" só estaria lá porque o modelo obedeceu, e isso não é
   verificável depois.

**O que o auditor já consegue fazer:** dada uma ação proposta, dizer se ela
está no escopo declarado. Por exemplo, "descontar estoque" ou "prescrever" não
estão. Também consegue ver quais limites são só intenção, porque estão
marcados aqui como lacuna, e não escondidos.

**O que transforma o "não" em "sim":** as lacunas P0 (L05, L06, L07, L18) mais
L28 e L31. Ou seja: limites em código com teste, e um trace por decisão com
versões, política avaliada e identificador. Com isso, a pergunta "esta
recomendação estava dentro da autoridade?" vira uma consulta: abrir o registro
pelo `recomendacao_id`, ver qual política foi avaliada e com qual resultado, e
conferir no teste que a regra faz o que este documento afirma.
