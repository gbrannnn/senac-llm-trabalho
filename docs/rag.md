# RAG — o conhecimento de domínio que os agentes consultam

**Versão do sistema:** commit `d16e6b7` · índices `idx-receitas-60d982053e0f` e `idx-oms-9ee6cda7b95b` · código em [src/rag.py](../src/rag.py), [src/ferramentas.py](../src/ferramentas.py), [src/citacao.py](../src/citacao.py)

**A resposta direta:** o nosso RAG é **os dois**:
- **consulta estruturada** para o que é registro: composição na TBCA, estoque, perfil e histórico;
- **busca vetorial** para o que é assunto: qual receita, qual diretriz.

## 4.1 As formas de recuperar, e as que o case usa

### A classificação das perguntas

As perguntas, a forma que cada uma pede e o trecho que a responde estão na [§4.3](#43-as-dez-perguntas-e-o-corte). Resumo:

| Forma | Perguntas do conjunto | Usamos? |
|---|---|---|
| **registro** → consulta estruturada | 1, 2, 11 (TBCA); o estoque e o perfil em toda recomendação | **sim** |
| **termo** → busca textual | 6 ("2000 mg de sódio em gramas de sal"): a resposta está numa linha de conversor, com termos exatos | **não** (ver o achado da pergunta 6) |
| **assunto** → busca vetorial | 3, 4, 5, 7, 8 (OMS); 9 (receitas) | **sim** |
| **relação** → grafo | nenhuma | não |
| **agregação** | nenhuma ("quais receitas você mais me sugeriu?" seria; está fora do escopo) | não |

A classificação **não** concentrou tudo em "assunto": as perguntas vieram do que a pessoa pergunta ao nutricionista (o case), e não do índice. Três delas são registro, e duas não têm resposta no corpus.

### A escolha, com justificativa

| Forma usada | Com o quê | O que ela responde no case |
|---|---|---|
| **consulta estruturada** | SQLite (perfil, estoque, histórico) e `dados/tbca.json` (62 alimentos), acessados por chave: `usuario_id` e código TBCA. O nome dito vira código pelo catálogo, em código ([catalogo.py](../src/catalogo.py) `casar_pt`) | "quanta proteína tem o ovo?", "o que tenho em casa?", "o que recomendei ontem?". **Nunca por similaridade**: proteína do ovo é um número, não uma vizinhança |
| **busca vetorial** | `bge-m3` (Ollama, digest `790764642607`), **1024 dimensões**, vetores normalizados em `dados/indice/*.npz`, produto escalar em `numpy`. **Sem banco vetorial**: são 300 + 41 vetores, e a busca leva menos de 1 ms. Um serviço a mais custaria mais do que resolve | "o que faço com abobrinha?" (receitas); "qual a meta da OMS para o sal?" (diretrizes) |

**Por que o `bge-m3`:** as perguntas chegam em **português** e o corpus está em **inglês**. O `bge-m3` é multilíngue. Mesmo assim, a busca entre línguas foi fraca no acervo de receitas ("omelete de espinafre" não trazia omelete). Por isso a ferramenta **expande** a consulta pelo catálogo, que é a ponte de vocabulário: "abobrinha" vira "abobrinha (zucchini summer squash)" ([ferramentas.py](../src/ferramentas.py) `expandir_consulta`).

## 4.2 O corpus, e o que entra nele

| Documento | De onde | Quem mantém | Muda com que frequência | Consequência para o índice |
|---|---|---|---|---|
| 300 receitas | Epicurious via Kaggle (espelho no Hugging Face), CC BY-SA 3.0 | o grupo, pelo recorte em [baixar_dados.py](../scripts/baixar_dados.py) (semente 42) | **nunca** (dataset congelado) | construído uma vez; versão = hash do corpus |
| *Healthy diet* (26/01/2026) | who.int | OMS | revisão a cada 1–3 anos | reconstruir quando a OMS publicar |
| *Sodium reduction* (11/05/2026) | who.int | OMS | idem | idem |
| *Salt reduction* (versão capturada em 30/04/2018) | Wayback Machine | — | **revogado** | fica no corpus de propósito (abaixo) |
| TBCA (62 alimentos) | tbca.net.br, por código | USP/FoRC | versões anuais | consulta estruturada, sem índice |

**A curadoria do recorte de receitas** ([baixar_dados.py](../scripts/baixar_dados.py) `_curar`) entra no corpus só a receita que passa em todos estes critérios:
- tem de 3 a 10 ingredientes;
- todo ingrediente obrigatório casa com o catálogo;
- não tem bebida alcoólica nem koji;
- tem ao menos 2 itens que não são da despensa básica.

Das 13.501 receitas, 2.148 passaram, e 300 foram sorteadas. O dataset **não informa porções nem tempo de preparo**: o sistema declara isso em toda recomendação, em vez de inventar ([case.md §0.1](case.md#01-vocabulário-que-quem-é-de-fora-não-entende)).

### O documento revogado

Pusemos no corpus, de propósito, a ficha *Salt reduction* de 2018. Ela diz que a meta global é reduzir o sal em 30% **até 2025**. A ficha vigente (2026) diz que esse prazo **foi estendido para 2030** por decisão da Assembleia Mundial da Saúde de 2019. As duas respondem à pergunta 5.

O que aconteceu ([E04](evidencias/E04-revogado.txt), `python -m scripts.experimentos revogado`):

| | recuperados (top 3) | fontes da resposta | resposta |
|---|---|---|---|
| **sem** desempate | `sodio-2026#08` (0,693), **`sal-2018#10` (0,655)**, `sodio-2026#00` | inclui **`oms-sal-2018#10`** | correta (2025 → 2030), porque o trecho vigente veio em 1º |
| **com** desempate | `sodio-2026#08`, `#00`, `#07` | só 2026 | correta; `sal-2018#10` e `#09` registrados como descartados |

**O achado:** o sistema, sozinho, **não tem como saber** que a ficha de 2018 não vale mais. O embedding não representa anterioridade, e o trecho revogado ficou a 0,04 do vigente. Desta vez a resposta saiu certa porque o trecho vigente ficou em 1º lugar. Mas o revogado **entrou nas fontes**: um auditor leria que a resposta se apoiou num documento revogado.

A solução não foi técnica de recuperação. Foi **curadoria**: cada documento declara `familia` e `data_publicacao` no cabeçalho, e o código mantém só a versão mais recente de cada família ([rag.py](../src/rag.py) `buscar_oms`). O descarte vai para o log.

## 4.3 As dez perguntas, e o corte

Este é o primeiro dataset de avaliação do RAG, executado pelo sistema inteiro em [E08](evidencias/E08-perguntas.txt) (`python -m scripts.experimentos perguntas`, logs `logs/*_E08_pergunta_*.jsonl`).

| # | Pergunta | Forma | O que a responde | Recuperou? | Resultado |
|---|---|---|---|---|---|
| 1 | Quanta proteína tem 100 g de ovo? | registro | TBCA `BRC0012J` | sim | ✓ 9,04 g |
| 2 | Quantas calorias tem 100 g de banana? | registro | TBCA `BRC0011C` | sim | ✓ 107 kcal |
| 3 | Qual é o limite de sódio por dia para um adulto? | assunto | `oms-sodio-2026#03` | sim | ✓ < 2000 mg (< 5 g de sal) |
| 4 | Para crianças, o limite de sal é o mesmo dos adultos? | assunto, **exceção** (2–15 anos: ajustar para baixo pela energia) | `oms-sodio-2026#03` | sim | ✓ cita o ajuste para crianças |
| 5 | Até quando é a meta global de reduzir o sal em 30%? | assunto, **exceção** (prazo estendido; há versão revogada) | `oms-sodio-2026#08` | sim | ✓ 2025 → estendida a 2030 |
| 6 | Quantos gramas de sal equivalem a 2000 mg de sódio? | **termo** | `oms-sodio-2026#06` (conversor) | **não** | ✗ recusa (falso negativo; ver abaixo) |
| 7 | Qual o limite de açúcar livre que a OMS recomenda? | assunto | `oms-alimentacao-saudavel-2026#04` | sim | ✓ < 10%, ~50 g, **mas** "12 colheres de **sopa**" (a fonte diz *teaspoons*) |
| 8 | Quanto de gordura trans a OMS recomenda no máximo? | assunto | `oms-alimentacao-saudavel-2026#06` | sim | ✗ recusa (falso negativo; ver abaixo) |
| 9 | me sugere alguma coisa com abobrinha | assunto (receitas) + registro (estoque) | receita `R01931` | sim | ✓ *Summer Squash and Basil Pasta* |
| 10 | O que a OMS recomenda sobre cafeína na gravidez? | **fora do corpus** | — | — | ✓ recusa |
| 11 | Quanta proteína tem 100 g de quinoa? | **fora do corpus** | — | — | ✓ recusa ("quinoa não está no recorte da TBCA") |

**Placar:**
- **recuperação:** 9 das 10 perguntas que têm resposta no corpus trouxeram o trecho certo;
- **resposta:** 7 certas, sendo 1 com erro de unidade;
- **falsos negativos:** 2, nas perguntas 6 e 8;
- **recusas corretas:** 2 de 2;
- **números inventados entregues:** 0.

**Duas falhas, e as duas são do lado seguro:**
- **6 (termo):** o consultor buscou "sódio e sal na dieta" em português e não trouxe o conversor. Então **fez a conta sozinho, errada**: "5,3 g", quando a fonte diz 5 g. O portão de números barrou a resposta, porque 0.4, 2.5 e 5.3 não estão nas fontes. É o caso que pede busca **textual**, e a correção proposta é uma consulta por termo ("2000 mg", "convert") antes da vetorial.
- **8:** a resposta estava **certa** ("menos de 1% da energia"). Mas o verificador citou uma frase que não existe literalmente: juntou duas orações da fonte. O código rejeitou a citação. É o custo do portão estrito, que prefere recusar a aceitar paráfrase.

**Corte e `k` (só a busca vetorial tem):**

| Corpus | Corte | Por que serve | `k` |
|---|---|---|---|
| receitas | **uma receita = um trecho** | receita partida perde sentido: o passo 3 sem os ingredientes não responde nada | o modelo vê até **5 viáveis**, escolhidas entre as **15** mais próximas; as inviáveis são filtradas em código antes |
| OMS | **por estrutura** (seção da ficha); seção acima de 200 palavras vira janelas por parágrafo, com o título herdado | a ficha tem seções temáticas ("Sugars", "Fats"). A 1ª versão do corte, só por `##`, deixou a seção do conversor com 434 palavras, e o parágrafo da meta de 2030 ficava fora do limite de caracteres que a ferramenta devolve. Linha solta curta sem marcação ("WHO response") também vira título, e as referências bibliográficas saem | **3** para o consultor (busca 6 e aplica o desempate, para o descarte não esvaziar o resultado); **1** para o avaliador |

O `k` = 3 da OMS vem da medição: nas perguntas de assunto, o trecho certo veio em 1º lugar em todas (E08 e logs). `k` maior só colocaria mais trechos de 200 palavras na janela, que já chega a 1.700 tokens no consultor.

## 4.4 Onde a recuperação entra no laço

**A escolha: ferramenta do agente.** O chef e o consultor decidem quando buscar, como decidem chamar qualquer outra ferramenta. A exceção declarada é o avaliador, que faz **uma busca fixa** na OMS a cada proposta, porque sempre precisa de um critério.

Medido nos logs da rodada final (`logs/`, recomendações e perguntas que chegaram ao agente):

| Rota | Buscas de receitas | Buscas na OMS | Consultas TBCA | Buscas vazias | Chamadas ao modelo |
|---|---|---|---|---|---|
| recomendação (14 execuções que chegaram ao chef) | **1,0** por execução, decidida pelo chef | 0,93, **fixa**, no avaliador (13 de 14; a 14ª não teve proposta para avaliar) | 0 | 1 de 14 (bruno: as 15 candidatas tinham ingrediente faltando ou amendoim) | 4,0 |
| pergunta (14 execuções que chegaram ao consultor) | 0 | 0,71, decidida pelo consultor | 0,36, decidida pelo consultor | 2 de 14 (tofu, quinoa) | 4,8 |

- **Etapa fixa no avaliador:** nas 13 buscas fixas, o trecho recuperado foi **sempre o mesmo** (`oms-alimentacao-saudavel-2026#01`, "Overview"), qualquer que fosse a receita. Nenhuma foi vazia, mas todas foram **pouco úteis**: a consulta fixa ("healthy diet recommendations: {objetivo}") depende só do objetivo, e os usuários de teste têm só dois objetivos. Fica como melhoria: incluir na consulta o que a receita tem de mais crítico (sódio, açúcar, gordura).
- **Ferramenta no consultor:** no caso 3 ("tofu e ovo"), o consultor **não** buscou na OMS, só na TBCA. No caso 5 (cafeína), buscou só na OMS. Essa é a economia que a etapa fixa não teria.

## O que a recuperação não garante, e os portões que existem por isso

| Defeito medido | Exemplo | Controle |
|---|---|---|
| número que não está na fonte | "200 mg de cafeína para grávidas"; "130 kcal" da quinoa; "5,3 g" de sal | **portão de números** ([citacao.py](../src/citacao.py) `nao_sustentados`) |
| afirmação sem número e sem fonte | "a cafeína deve ser limitada, pois pode ter efeitos negativos no feto" | **verificador**: o modelo cita um trecho e o código confere que ele existe literalmente (`verificar_resposta`) |
| interpretação errada de trecho certo | "colheres de sopa" para *teaspoons*; "clara do ovo" para "Ovo, galinha, branco" | **nenhum**. Limite conhecido, declarado no [case.md §2.11](case.md#211-o-maior-risco) |
