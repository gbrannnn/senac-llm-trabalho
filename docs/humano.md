# Human-in-the-loop — onde o grafo para, e o que acontece se ninguém responder

**Versão do sistema:** commit `fffe38f` · código em [src/grafo.py](../src/grafo.py) (`casar_catalogo`, `pausa_estoque`, `confirmar_estoque`, `extrair_perfil`, `confirmar_perfil`) e [src/main.py](../src/main.py)

## 8.1 Onde o grafo para, e por qual critério

| Ponto de parada (no diagrama: `⏸`) | Critério | Por quê |
|---|---|---|
| **`confirmar_estoque`**, antes de **somar** itens ao estoque | **confiança baixa** + ação com efeito persistente | o texto "comprei leite" não diz qual leite, e escolher por palpite grava um fato errado que as recomendações seguintes vão usar. Mesmo sem ambiguidade, a pessoa confere a quantidade: "quantidade não informada: supus 1" |
| **`confirmar_perfil`**, antes de **remover uma alergia** | **ação mais perigosa do sistema** | tirar "amendoim" das alergias libera receitas com amendoim. Se o modelo entender errado "não tenho mais alergia a amendoim, mas tenho a castanha", o erro chega ao prato |

**O que não para, e por quê:**
- **a recomendação** é uma sugestão, e a pessoa decide se cozinha. O que a tornaria perigosa (alérgeno) é barrado em código, não por aprovação;
- **adicionar uma alergia** é a escrita que só deixa o sistema **mais** cauteloso;
- **mudar o objetivo** é reversível e de baixo impacto.

O sistema **não move dinheiro nem escreve em sistema de terceiro**. Por isso o critério de custo acima de um teto não se aplica.

## 8.2 O que a pessoa vê, e o que ela devolve

O texto da pausa é um prompt versionado ([pausa_estoque.md](../src/prompts/pausa_estoque.md)), sem LLM. Ele mostra **a ação exata, com os argumentos e a consequência**. Copiado do log `caso6a_pausa` (commit `fffe38f`):

```text
Vou SOMAR estes itens ao seu estoque (ana):
  - ovo: 6 un
Pendentes:
  ? leite: ambíguo entre leite_desnatado, leite_integral — NÃO será gravado, a menos que você edite
Consequência: as quantidades acima passam a contar nas próximas recomendações. Nada foi gravado ainda.
Responda até 2026-10-21T23:02:18:
  aprovar               -> grava exatamente a lista acima
  editar <json>         -> grava a lista que você mandar, por exemplo [{"item_id":"leite_integral","quantidade":1,"unidade":"l"}]
  rejeitar              -> não grava nada
Sem resposta até o prazo, nada é gravado.
```

| Resposta | Na linha de comando | O que acontece |
|---|---|---|
| **aprovar** | `python -m src.main --usuario ana --sessao caso6 --aprovar` | grava exatamente `itens_propostos`; os pendentes **não** entram |
| **aprovar editando** | `... --editar '[{"item_id":"leite_integral","quantidade":1,"unidade":"l"}, ...]'` | grava a lista editada. Cada item é validado: `item_id` do catálogo e quantidade > 0. Edição inválida → nada gravado, `rejeitado_pelo_humano` |
| **rejeitar** | `... --rejeitar` | nada gravado |
| *(silêncio)* | — | ver [§8.4](#84-o-que-acontece-se-ninguém-responder) |

**Aprovar editando** foi o que resolveu a ambiguidade no caso 6: a pessoa disse que o leite era integral, 1 litro (log `caso6b_aprovar_editando`).

## 8.3 A implementação, e por que ela depende do checkpoint

- **A pausa** é `interrupt(pausa_estoque(estado))` dentro de `confirmar_estoque`. O valor devolvido pelo `interrupt` é a resposta da pessoa.
- **A retomada** é uma nova invocação: `grafo.stream(Command(resume={"acao": "editar", "itens": [...]}), config)` ([main.py](../src/main.py) `executar`).
- **O nó roda de novo desde o começo** na retomada. Por isso não há efeito colateral antes do `interrupt`, e o prazo (`expira_em`) é gravado no nó **anterior** (`casar_catalogo`). Se fosse calculado em `confirmar_estoque`, o prazo recomeçaria a cada retomada e nunca venceria.
- **O checkpointer** é `SqliteSaver` em `dados/checkpoints.sqlite`, endereçado por `thread_id = usuario:sessao`. Como grava em arquivo, a aprovação pendente **sobrevive ao processo**. Demonstrado com dois processos: um pausou (log `humano_cli_1_pausa`), outro aprovou (log `humano_cli_2_aprovar`):

```text
$ python -m src.main --usuario ana --sessao cli "chegaram 2 kg de batata e 1 kg de cenoura"
Vou SOMAR estes itens ao seu estoque (ana):
  - batata: 2 kg
  - cenoura: 1 kg
...
$ python -m src.main --usuario ana --sessao cli --aprovar          # outro processo
Estoque atualizado: batata (2 kg), cenoura (1 kg).
```

## 8.4 O que acontece se ninguém responder

- **Prazo:** 24 horas (`PRAZO_APROVACAO_S`, configurável), mostrado na própria pausa ("Responda até …").
- **Quando vence:** a execução **expira** e **nada é gravado**. Ela nunca segue sozinha. Há dois caminhos:
  - a qualquer retomada depois do prazo, `confirmar_estoque` compara `time.time()` com `expira_em` e termina em `aprovacao_expirada`, mesmo que a resposta tenha sido "aprovar";
  - `python -m src.main --pendentes --expirar` lista as conversas paradas em `interrupt` e encerra as vencidas. Rotina para agendar.
- **Testado com prazo de 3 s** ([E10](evidencias/E10-prazo.txt), `python -m scripts.experimentos prazo`, logs `E10_prazo_*`): "chegaram 2 kg de batata" → pausa → 4 s de espera → `--pendentes --expirar` → `"O prazo para aprovar acabou. Nada foi gravado."`. A batata continuou em 3 kg, e um `aprovar` enviado depois respondeu "Não há nada aguardando aprovação nesta conversa".

## 8.5 Aprovar duas vezes

A mesma aprovação foi entregue **duas vezes no ponto exato da pausa**. A segunda retoma do checkpoint em que a execução estava parada, como aconteceria se o clique chegasse duplicado ([demonstrar.py](../scripts/demonstrar.py) `caso6`). Dos logs:

```text
caso6b_aprovar_editando     confirmar_estoque  decisao_humana = editar [leite_integral 1 l, ovo 6 un]
                            gravar_estoque     efeito = {"chave": "9bbf9d53f240fe72", "ja_existia": false, "gravados": 2}
caso6c_aprovacao_repetida   confirmar_estoque  decisao_humana = editar [leite_integral 1 l, ovo 6 un]
                            gravar_estoque     efeito = {"chave": "9bbf9d53f240fe72", "ja_existia": true,  "gravados": 0}
                            saída: "Isso já estava registrado (mesma lista, mesmo dia). Nada foi gravado de novo."
caso6d_aprovar_sem_pendencia  NOTA: nada pendente nesta conversa: a retomada não executou nenhum nó
```

**A segunda chamada não criou nada:**
- a chave é derivada do **conteúdo**: sha256 de usuário + itens normalizados + dia ([db.py](../src/db.py) `somar_estoque`);
- a mesma lista produziu a mesma chave (`9bbf9d53f240fe72`);
- o livro `escritas` recusou a segunda inserção, e o estoque não foi tocado.

O caso 6d mostra a outra situação: aprovar uma conversa que não tem nada pendente não executa nenhum nó.

Também testado fora do caso 6 (execução de 20/10, 22h20): a mesma lista ("comprei 6 ovos") enviada em duas conversas diferentes no mesmo dia e aprovada nas duas resultou em `ja_existia: true` na segunda, e o estoque de ovos foi de 12 para 18: a primeira aprovação somou 6, e a segunda não somou nada. O log dessa execução não foi mantido; a prova versionada é o caso 6.
