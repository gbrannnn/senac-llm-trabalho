"""Experimentos que sustentam os documentos. Cada um grava docs/evidencias/E0N-*.txt.

    python -m scripts.experimentos janela      # E02: truncamento silencioso do Ollama
    python -m scripts.experimentos reducer     # E03: o grafo sem reducer em `fontes`
    python -m scripts.experimentos revogado    # E04: documento revogado com e sem desempate
    python -m scripts.experimentos remocao     # E05: remoção do titular + varredura
    python -m scripts.experimentos frase       # E06: a regra da frase no prompt do chef
    python -m scripts.experimentos etapas      # E07: triagem e extração contra casos rotulados
    python -m scripts.experimentos todos
"""
import contextlib
import io
import json
import sys
import time
from datetime import datetime

from src import config, db, llm, prompts, rag
from src.registro import commit

EVID = config.RAIZ / "docs" / "evidencias"


@contextlib.contextmanager
def evidencia(codigo: str, titulo: str, comando: str):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield
    texto = (f"# {codigo} — {titulo}\n# commit: {commit()} · data: {datetime.now().isoformat(timespec='seconds')}\n"
             f"# modelo: {json.dumps(llm.identidade_modelo())}\n$ {comando}\n\n{buf.getvalue()}")
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / f"{codigo}-{titulo.split(':')[0].lower().replace(' ', '-')}.txt").write_text(texto, encoding="utf-8")
    sys.__stdout__.write(texto + "\n")


def janela():
    """O mesmo prompt de ~4.500 tokens (abaixo do orçamento de 6.000) em dois modelos:
    o padrão do Ollama (janela 4096) e o do Modelfile (num_ctx 8192)."""
    prompt = ("Guarde este código: CODIGO-SECRETO-4471.\n" + " ".join(["banana maçã"] * 1500)
              + "\nQual é o código? Responda só o código.")
    with evidencia("E02", "janela: truncamento silencioso do contexto", "python -m scripts.experimentos janela"):
        contagens = {}
        for modelo in ("qwen2.5:7b-instruct", config.LLM_MODELO):
            r = llm.cliente().chat.completions.create(model=modelo, temperature=0, max_tokens=15,
                                                      messages=[{"role": "user", "content": prompt}])
            contagens[modelo] = r.usage.prompt_tokens
            print(f"modelo={modelo:22s} prompt_tokens_processados={r.usage.prompt_tokens:5d} "
                  f"erro_ou_aviso=nenhum resposta={r.choices[0].message.content!r}")
        perdidos = contagens[config.LLM_MODELO] - contagens["qwen2.5:7b-instruct"]
        print(f"\nLeitura: o mesmo prompt foi processado inteiro ({contagens[config.LLM_MODELO]} tokens) só com num_ctx=8192."
              f" Com a janela padrão, {perdidos} tokens do INÍCIO foram descartados sem erro e sem aviso — e o início é"
              " onde fica o system prompt. Quando estoura, o Ollama corta para cerca de metade da janela (2050 de 4096).")


def reducer():
    from langgraph.checkpoint.memory import MemorySaver

    from src.grafo import construir
    with evidencia("E03", "reducer: o mesmo grafo com e sem reducer em fontes", "python -m scripts.experimentos reducer"):
        for com in (True, False):
            g = construir(reducer_fontes=com).compile(checkpointer=MemorySaver())
            cfg = {"configurable": {"thread_id": f"ana:reducer-{com}"}, "recursion_limit": config.RECURSION_LIMIT}
            print(f"--- reducer em `fontes`: {'SIM (por_turno)' if com else 'NÃO (último valor)'}")
            try:
                for passo in g.stream({"entrada": "o que eu faço pra jantar?", "usuario_id": "ana", "thread_id": "ana:r"},
                                      cfg, stream_mode="updates"):
                    for no, v in passo.items():
                        if no.startswith("carregar_"):
                            print(f"  {no:20s} escreveu fontes={[f['tipo'] for f in (v or {}).get('fontes', [])]}")
                    if "triagem" in passo:
                        break
                print(f"  estado depois da junção: fontes={[f['tipo'] for f in g.get_state(cfg).values.get('fontes', [])]}")
            except Exception as erro:  # noqa: BLE001 — o ponto da demonstração é a exceção
                print(f"  EXCEÇÃO {type(erro).__name__}: {str(erro).splitlines()[0]}")


def revogado():
    from src.main import executar
    pergunta = "Até quando é a meta global de reduzir o consumo de sal em 30%?"
    with evidencia("E04", "revogado: a ficha de 2018 no corpus, com e sem desempate", "python -m scripts.experimentos revogado"):
        for desempate in (False, True):
            config.DESEMPATE_OMS = desempate
            r = rag.buscar_oms(pergunta)
            print(f"--- desempate por data_publicacao: {'LIGADO' if desempate else 'DESLIGADO'}")
            print("  recuperados:", [(t["id"], t["data_publicacao"], round(n, 3)) for t, n in r.trechos])
            print("  descartados:", [d["id"] for d in r.descartados])
            s = executar("ana", f"revogado-{desempate}", pergunta, nome_log=f"E04_revogado_desempate_{desempate}")["saida"]
            print(f"  saída ({s['suficiencia']}): {s['resultado']}")
            print(f"  fontes: {[f['id'] for f in s['fontes']]}\n")
        config.DESEMPATE_OMS = True


def remocao():
    from src import remover
    from src.main import executar
    alvo = "titular_teste_7f3a"
    with evidencia("E05", "remocao: gravar, ver o efeito, remover, ver voltar, varrer", "python -m scripts.experimentos remocao"):
        db.atualizar_perfil(alvo, "objetivo", "definir", "emagrecimento")
        db.atualizar_perfil(alvo, "alergias", "adicionar", "camarão")
        db.somar_estoque(alvo, [{"item_id": i, "quantidade": 1, "unidade": "un"} for i in ("frango", "arroz", "batata", "manteiga", "alho", "cebola", "ervas", "limao")])
        s = executar(alvo, "s1", "o que eu como hoje?", nome_log=f"E05_{alvo}_antes")["saida"]
        print("1. com dados  :", s["tipo"], "|", s["resultado"][:160])
        print("   varredura  :", json.dumps(remover.varrer(alvo)))
        print("2. remoção    :", json.dumps(remover.remover(alvo)))
        print("3. varredura  :", json.dumps(remover.varrer(alvo)))
        s = executar(alvo, "s2", "o que eu como hoje?", nome_log=f"E05_{alvo}_depois")["saida"]
        print("4. sem dados  :", s["tipo"], "|", s["resultado"][:160])
        print("   (o log desta última execução é novo: a pessoa voltou a falar com o sistema)")


def frase():
    """Regra da frase (§2.3): tira a regra 2 do chef e mede passos e término em 5 pedidos."""
    from src import grafo
    from src.main import executar
    frase_alvo = ('2. Se "viaveis" for maior que 0, PARE de buscar e chame `propor_receita` com a receita que melhor atende '
                  'o pedido. Só busque de novo, com outros ingredientes, se "viaveis" for 0. No máximo 3 buscas; depois '
                  'disso, declare que não há opção.\n')
    original = grafo.carregar
    pedidos = ["o que eu faço pra jantar?", "quero algo com frango", "me sugere um almoço com batata",
               "tenho ovo e espinafre, o que faço?", "uma massa pra hoje"]
    with evidencia("E06", "frase: a regra de parada do chef, com e sem", "python -m scripts.experimentos frase"):
        assert frase_alvo in original("chef").texto
        for com in (True, False):
            def carregar(nome, _com=com):
                p = original(nome)
                if nome == "chef" and not _com:
                    return prompts.Prompt(p.id, p.versao + "-sem-regra2", p.texto.replace(frase_alvo, ""), "experimento")
                return p
            grafo.carregar = carregar
            print(f"--- chef {'COM' if com else 'SEM'} a frase da regra 2")
            for i, pedido in enumerate(pedidos):
                inicio = time.perf_counter()
                s = executar("ana", f"frase-{com}-{i}", pedido, nome_log=f"E06_frase_{'com' if com else 'sem'}_{i}")["saida"]
                print(f"  {pedido:38s} -> {s['termino']:15s} chamadas={s['uso']['chamadas']:2d} "
                      f"tokens={s['uso']['tokens']:6d} {time.perf_counter() - inicio:5.1f}s")
        grafo.carregar = original


TRIAGEM = [  # (texto, rota esperada, acao_futura esperada)
    ("o que eu como hoje?", "recomendar", False), ("me dá uma ideia de almoço com o que tenho", "recomendar", False),
    ("tenho frango e batata, faz o que com isso?", "recomendar", False), ("quero uma janta leve", "recomendar", False),
    ("comprei 1kg de arroz e 2 de feijão", "estoque", False), ("chegou a feira: tomate, cebola, alho", "estoque", False),
    ("NF-e: OVOS BRANCOS 12UN; LEITE INT 1L 2UN", "estoque", False), ("acabei de comprar banana", "estoque", False),
    ("sou alérgica a camarão", "perfil", False), ("virei vegetariano", "perfil", False),
    ("meu objetivo agora é ganhar massa", "perfil", False), ("comprei uma air fryer", "perfil", False),
    ("quanto sal posso comer por dia?", "pergunta", False), ("ovo tem quanta proteína?", "pergunta", False),
    ("o que a OMS diz sobre açúcar?", "pergunta", False), ("qual remédio tomo pra azia?", "fora_escopo", False),
    ("quantas cápsulas de ômega 3 devo tomar?", "fora_escopo", False), ("me ajuda a fazer meu imposto de renda", "fora_escopo", False),
    ("vou comprar peixe amanhã", "fora_escopo", True), ("semana que vem vou ao mercado comprar ovos", "fora_escopo", True),
]
EXTRACAO = [  # (texto, {nome: quantidade}) — None = quantidade não dita
    ("comprei 2kg de frango e uma dúzia de ovos", {"frango": 2, "ovo": 12}),
    ("chegou leite e queijo cottage", {"leite": None, "queijo cottage": None}),
    ("NF: ARROZ TIPO1 5KG 1UN; DETERGENTE 500ML 1UN", {"arroz": 5}),
    ("trouxe 6 bananas e 3 maçãs da feira", {"banana": 6, "maçã": 3}),
    ("comprei 500 g de carne moída e um pacote de macarrão", {"carne moída": 500, "macarrão": 1}),
    ("chegou tomate", {"tomate": None}),
]


def etapas():
    from src import catalogo, esquemas
    from src.prompts import carregar
    with evidencia("E07", "etapas: triagem e extração contra casos rotulados", "python -m scripts.experimentos etapas"):
        acertos, erros = 0, []
        for texto, rota, futura in TRIAGEM:
            t, _ = llm.estruturada(carregar("sistema").texto, carregar("triagem").formatar(entrada=texto, conversa="(vazia)"),
                                   esquemas.Triagem)
            # mesma regra de rota_triagem: futuro vira "não agir", que aqui conta como fora_escopo
            efetiva = "fora_escopo" if t.acao_futura and t.rota != "pergunta" else t.rota
            ok = efetiva == rota and (t.acao_futura == futura or not futura)
            acertos += ok
            if not ok:
                erros.append(f"{texto!r}: esperado {rota}/futura={futura}, veio {t.rota}/futura={t.acao_futura}")
        print(f"TRIAGEM {carregar('triagem').versao}@{carregar('triagem').sha}: {acertos}/{len(TRIAGEM)} (critério: >= 18)")
        for e in erros:
            print("  erro:", e)
        acertos, erros = 0, []
        for texto, esperado in EXTRACAO:
            r, _ = llm.estruturada(carregar("sistema").texto, carregar("extrair_itens").formatar(entrada=texto),
                                   esquemas.ItensExtraidos)
            veio = {catalogo.normalizar(i.nome): i.quantidade for i in r.itens}
            alvo = {catalogo.normalizar(k): v for k, v in esperado.items()}
            ok = set(veio) == set(alvo) and all((veio[k] is None) == (v is None) and (v is None or float(veio[k]) == v)
                                                for k, v in alvo.items())
            acertos += ok
            if not ok:
                erros.append(f"{texto!r}: esperado {alvo}, veio {veio}")
        print(f"\nEXTRAÇÃO {carregar('extrair_itens').versao}@{carregar('extrair_itens').sha}: {acertos}/{len(EXTRACAO)} (critério: >= 5)")
        for e in erros:
            print("  erro:", e)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    alvo = sys.argv[1] if len(sys.argv) > 1 else "todos"
    for nome in (["janela", "reducer", "revogado", "remocao", "frase", "etapas"] if alvo == "todos" else [alvo]):
        globals()[nome]()
