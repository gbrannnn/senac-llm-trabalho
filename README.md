# Agente Nutricionista Pessoal

**O problema em uma frase:** decidir o que cozinhar hoje com o que já existe em casa, respeitando as alergias e o objetivo de quem vai comer, sem inventar número de nutrição.

## Integrantes
- Daniel de Araujo Carvalho
- Eduardo Dias Santos
- Gabriel Brandão Vehchani de Freitas
- Pedro Henrique Gomes

**Entrega atual:** Parte 2 — o agente em LangGraph, com RAG, memória e human-in-the-loop. A documentação completa está em [docs/](docs/); comece por [docs/case.md](docs/case.md) e [docs/arquitetura.md](docs/arquitetura.md).

---

## Como rodar

Testado do zero, num clone novo, em **2 min 15 s** com os modelos já baixados (instalação 56 s, preparação 63 s, primeira pergunta 16 s). Baixar os modelos (~6 GB) leva mais, e depende da conexão.

**Requisitos:** Python 3.13, [Ollama](https://ollama.com) 0.40+ e GPU com 8 GB (roda na CPU, mas devagar).

```bash
# 1. Modelos (uma vez). Use o APLICATIVO do Ollama: um `ollama serve` aberto no terminal
#    pode ocupar a porta sem GPU (ver docs/modelos.md §3.2). Confira com `ollama ps`.
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
ollama create nutri-qwen -f Modelfile      # fixa num_ctx=8192 (docs/evidencias/E02)

# 2. Ambiente
python -m venv .venv
.venv\Scripts\activate                     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# opcional: copie .env.example para .env (sem .env, valem os padrões de src/config.py)

# 3. Dados, índice e banco com usuários fictícios (~1 min: baixa receitas, TBCA e OMS e indexa)
python -m scripts.preparar

# 4. Usar
python -m src.main --usuario ana "o que eu faço pra jantar?"

# 5. Testes (69, sem modelo) e conferência do grafo
python -m pytest
python conferir_grafo.py
```

A TBCA não permite reprodução, então `dados/tbca.json` não está no git: o `preparar` baixa o arquivo em cada máquina. Nenhuma chave de API é necessária, porque o modelo roda local.

## Como usar

A pessoa **digita texto livre**. O sistema:
- recomenda uma refeição com o que está no estoque;
- registra compras (com a sua aprovação);
- atualiza o perfil (objetivo, alergias, restrições);
- responde dúvidas de nutrição com base na OMS e na TBCA.

Usuários fictícios já criados: **ana** (perfil completo, estoque com 18 itens), **bruno** (alergia a amendoim, e amendoim no estoque) e **carla** (usuária nova, sem perfil).

### O exemplo principal

Copiado do log [`logs/20261020-230141_caso1.jsonl`](logs/20261020-230141_caso1.jsonl) (commit `fffe38f`). A saída completa e outros exemplos estão em [docs/io.md](docs/io.md).

```text
$ python -m src.main --usuario ana --sessao caso1 "oi! o que eu posso fazer pra jantar hoje?"
Sugestão: Stir-Fried Black Rice with Fried Egg and Roasted Broccoli. Usa arroz, ovo, que estão no seu estoque. A receita inteira tem cerca de 1652 kcal e 35 g de proteína (TBCA).
```

```json
{
  "tipo": "recomendacao",
  "receita": {
    "id": "R03115",
    "nome": "Stir-Fried Black Rice with Fried Egg and Roasted Broccoli",
    "faltando_no_estoque": [],
    "nutricao": { "energia_kcal": 1651.5, "proteina_g": 35.1, "carboidrato_g": 295.4, "lipidio_g": 37.8,
                  "sodio_mg": 151.1, "completa": false, "fora_do_calculo": ["Kosher salt"],
                  "base": "receita inteira (o dataset não informa porções)" }
  },
  "fontes": [ {"tipo": "estoque", "id": "ana"}, {"tipo": "perfil", "id": "ana"},
              {"tipo": "oms", "id": "oms-alimentacao-saudavel-2026#01"},
              {"tipo": "receita", "id": "R03115"}, {"tipo": "tbca", "id": "BRC0001A,BRC0012J"} ],
  "suficiencia": "suficiente",
  "escolhas_declaradas": [
    "cálculo nutricional parcial: fora do cálculo Kosher salt",
    "justificativa do modelo substituída por texto em código: prometia benefício ('boa opção')"
  ],
  "termino": "concluido"
}
```
*(campos `ingredientes`, `detalhe` e `uso` omitidos aqui; estão completos em [docs/io.md](docs/io.md))*

> **Sobre os hashes nos logs:** os logs em `logs/` e as evidências em `docs/evidencias/` registram o commit `d16e6b7`. Esse é o mesmo código do commit `fffe38f` (a árvore é idêntica): só a mensagem do commit foi reescrita antes do envio.

**Como interpretar:**
- `faltando_no_estoque` vazio: dá para fazer agora. O brócolis do nome é acompanhamento opcional, "(for serving)".
- As calorias são da **receita inteira**, porque o acervo não informa porções.
- `escolhas_declaradas` é o que o sistema decidiu sozinho e está avisando.
- `fontes` é o que sustenta a resposta.

### Quando o sistema para e espera você

Ao registrar uma compra, o sistema **não grava nada** antes de você aprovar a lista exata:

```text
$ python -m src.main --usuario ana --sessao compras "comprei leite e 6 ovos"
Vou SOMAR estes itens ao seu estoque (ana):
  - ovo: 6 un
Pendentes:
  ? leite: ambíguo entre leite_desnatado, leite_integral — NÃO será gravado, a menos que você edite
...
Responda até 2026-10-21T23:02:18:
  aprovar | editar <json> | rejeitar
Sem resposta até o prazo, nada é gravado.

$ python -m src.main --usuario ana --sessao compras --editar '[{"item_id":"leite_integral","quantidade":1,"unidade":"l"},{"item_id":"ovo","quantidade":6,"unidade":"un"}]'
Estoque atualizado: leite integral (1 l), ovo (6 un).
```

- A resposta pode vir **de outro processo**, horas depois: a pausa fica gravada em `dados/checkpoints.sqlite`.
- Aprovar duas vezes não soma duas vezes.
- Sem resposta em 24 h, a pausa expira: `python -m src.main --pendentes --expirar`.
- Remover uma alergia também pausa.

Detalhes em [docs/humano.md](docs/humano.md).

### Outras coisas que você pode digitar

| Você digita | O sistema |
|---|---|
| `tenho abobrinha aqui, me sugere alguma coisa com abobrinha` | recomenda com abobrinha e **avisa** que o seu estoque não registra abobrinha (não grava) |
| `quanta proteína tem 100 g de tofu e 100 g de ovo?` | responde o ovo (TBCA) e diz que tofu não está na tabela (`suficiencia: parcial`) |
| `tenho alergia a camarão` | atualiza o perfil |
| `amanhã vou comprar brócolis, me lembra?` | não registra nada sobre o futuro; não envia lembretes |

### O que o sistema não faz

- **não** diagnostica, não trata condição clínica, não prescreve suplemento nem dose ("quantas cápsulas de ômega 3?" → recusa);
- **não** informa porções nem tempo de preparo: o acervo não tem esses dados, e o sistema diz isso em vez de inventar;
- **não** substitui nutricionista;
- **não** desconta do estoque o que você cozinhou;
- **não** lê foto de nota fiscal: cole o texto.

### O que acontece quando ele não sabe

O sistema **recusa e diz o que consegue responder**, com `suficiencia: insuficiente` e as `fontes` vazias:

```text
$ python -m src.main --usuario ana "o que a OMS recomenda sobre cafeína na gravidez?"
Não encontrei nas minhas fontes (TBCA e fichas da OMS) a informação para responder isso. Consigo informar a
composição de alimentos como abacate, abobrinha, ... e as recomendações da OMS sobre alimentação saudável e
sódio. Para outros alimentos, consulte um nutricionista.
```

Toda resposta de nutrição passa por dois controles em código: **todo número precisa estar nas fontes**, e o **trecho citado como prova precisa existir literalmente**. Quando o modelo inventa ("200 mg de cafeína", "130 kcal de quinoa"), a resposta é descartada e o descarte é declarado. Ver [docs/rag.md](docs/rag.md).

---

## Estrutura

```text
README.md            este arquivo
requirements.txt     dependências fixadas (inclusive LangGraph)
.env.example         nomes das variáveis, sem valores
Modelfile            o modelo nutri-qwen (num_ctx 8192)
conferir_grafo.py    imprime nós e arestas do grafo que o sistema executa
docs/                case, modelos, prompts, arquitetura, rag, memoria, grafo, humano, io, fontes, model-card
  evidencias/        E01–E10: saídas de comando dos experimentos
src/                 o sistema (grafo.py é o centro)
  prompts/           os prompts, versionados
scripts/             preparar (do zero), demonstrar (os 6 casos), experimentos (E02–E10)
dados/               catálogo de ingredientes e corpus (receitas, OMS)
logs/                os 6 casos demonstrados e os experimentos, um JSONL por execução
tests/               69 testes das partes determinísticas
```
