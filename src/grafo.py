"""O grafo do Agente Nutricionista (LangGraph `StateGraph`).

Desenho e justificativa: docs/grafo.md. Convenções deste arquivo:
- nó com prefixo de verbo; comentário `# MODELO` nos nós que chamam o LLM;
- toda aresta condicional tem o mapa de destinos explícito;
- todo nó que pode estourar orçamento grava `termino`, e toda função de rota
  olha `termino` antes de qualquer outra coisa (o framework não dá motivo de
  término: o nó terminal só diz que acabou — §6.5).
"""
import functools
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime
from functools import cache

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import catalogo, citacao, config, db, esquemas, ferramentas, llm, memoria, nutricional, rag
from .estado import Estado, EstadoSemReducer
from .prompts import carregar

# --- utilidades ----------------------------------------------------------------


def no(fn):
    """Erro fatal (modelo fora do ar, JSON inválido duas vezes) vira término, não exceção."""
    @functools.wraps(fn)
    def envolvido(estado):
        try:
            return fn(estado)
        except llm.ErroFatal as erro:
            return {"termino": "erro_fatal", "erro": str(erro)}
    return envolvido


def estouro(estado: Estado) -> str | None:
    """Os tetos que o framework não cobre: tempo, tokens e janela (§6.5)."""
    uso = estado.get("uso") or {}
    if time.time() - estado["inicio_ts"] > config.TIMEOUT_EXECUCAO_S:
        return "teto_tempo"
    if uso.get("tokens", 0) > config.MAX_TOKENS_EXECUCAO:
        return "teto_tokens"
    if uso.get("maior_janela", 0) > config.MAX_TOKENS_JANELA:
        return "teto_tokens"
    return None


def sistema(*nomes: str, **campos) -> str:
    return "\n\n".join([carregar("sistema").texto] + [carregar(n).formatar(**campos) for n in nomes])


def ctx_de(estado: Estado) -> ferramentas.Ctx:
    """Derivado do estado a cada uso (não guardado): evita duas fontes de verdade."""
    perfil = estado.get("perfil") or {}
    marcadores, _ = memoria.marcadores_de_alergia(perfil.get("alergias", []))
    disponiveis = {i["item_id"] for i in estado.get("estoque", [])} | set(estado.get("disponiveis_extra", []))
    return ferramentas.Ctx(estado["usuario_id"], disponiveis, marcadores,
                           {r["receita_id"] for r in estado.get("recentes", [])}, set(estado.get("rejeitadas", [])))


# --- início e contexto (paralelo) -------------------------------------------------

@no
def inicio(estado: Estado) -> dict:
    # Campos `por_turno` recebem None: o reducer zera o que sobrou do turno anterior.
    return {"execucao_id": uuid.uuid4().hex[:10], "inicio_ts": time.time(), "fontes": None, "escolhas": None,
            "agente_msgs": None, "recuperacoes": None, "descartes_oms": None, "uso": None, "rejeitadas": None,
            "passos_agente": 0, "rodadas": 0, "proposta": None, "veredito": None, "nutricao": None,
            "resposta_consultor": None, "disponiveis_extra": [], "itens_ditos": [], "itens_propostos": [],
            "pendentes": [], "decisao_humana": None, "efeito": None, "termino": None, "erro": None,
            "saida": None, "triagem": None, "atualizacao_perfil": None, "expira_em": None}


@no
def carregar_perfil(estado: Estado) -> dict:
    perfil = db.perfil(estado["usuario_id"])
    fontes = [{"tipo": "perfil", "id": estado["usuario_id"], "detalhe": "tabela perfil"}] if perfil else []
    return {"perfil": perfil, "fontes": fontes}


@no
def carregar_estoque(estado: Estado) -> dict:
    estoque = db.estoque(estado["usuario_id"])
    fontes = [{"tipo": "estoque", "id": estado["usuario_id"], "detalhe": f"{len(estoque)} itens"}] if estoque else []
    return {"estoque": estoque, "fontes": fontes}


@no
def carregar_historico(estado: Estado) -> dict:
    recentes = memoria.lembrar(db.historico(estado["usuario_id"]), estado["entrada"])
    fontes = [{"tipo": "historico", "id": r["receita_id"], "detalhe": r["data"]} for r in recentes]
    return {"recentes": recentes, "fontes": fontes}


# --- triagem ---------------------------------------------------------------------

@no
def triagem(estado: Estado) -> dict:  # MODELO
    conversa = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in estado.get("conversa", [])) or "(vazia)"
    resultado, uso = llm.estruturada(carregar("sistema").texto,
                                     carregar("triagem").formatar(entrada=estado["entrada"], conversa=conversa),
                                     esquemas.Triagem)
    return {"triagem": resultado.model_dump(), "uso": uso}


def rota_triagem(estado: Estado) -> str:
    if estado.get("termino"):
        return "fim"
    t = estado["triagem"]
    # Regra em código: falar do futuro não dispara ação (nem escrita, nem recomendação registrada).
    # Decide pelo campo `acao_futura`, que o modelo acerta de forma estável; a ROTA desses
    # pedidos oscilou entre versões do prompt (E07: "vou comprar peixe amanhã" -> recomendar).
    if t["acao_futura"] and t["rota"] != "pergunta":
        return "nao_agir"
    return t["rota"]


@no
def recusar(estado: Estado) -> dict:
    return {"termino": "recusa_fora_escopo"}


@no
def nao_agir(estado: Estado) -> dict:
    return {"termino": "sem_acao"}


# --- recomendação ------------------------------------------------------------------

@no
def checar_pedido(estado: Estado) -> dict:
    """Portão em código: o pedido tem o mínimo para recomendar? (§1.4)"""
    t, perfil, estoque = estado["triagem"], estado.get("perfil"), estado.get("estoque", [])
    if perfil is None:
        return {"termino": "pergunta_ao_usuario", "escolhas": [
            "perfil ausente: preciso do seu objetivo e de alergias antes de recomendar"]}
    if not estoque and not t["ingredientes_citados"]:
        return {"termino": "pergunta_ao_usuario", "escolhas": ["estoque vazio e nenhum ingrediente citado"]}
    escolhas, extras = [], []
    no_estoque = {i["item_id"] for i in estoque}
    for nome in t["ingredientes_citados"]:
        candidatos = catalogo.casar_pt(nome).candidatos
        if candidatos and not set(candidatos) & no_estoque:
            extras += candidatos[:1]
            escolhas.append(f"Você disse que tem {nome}, mas o seu estoque não registra. Considerei {nome} "
                            "disponível só nesta recomendação e não alterei o estoque.")
    if t.get("tempo_max_min"):
        escolhas.append(f"O acervo não informa tempo de preparo: não consigo garantir {t['tempo_max_min']} minutos.")
    if t.get("pessoas"):
        escolhas.append(f"O acervo não informa porções: não consigo garantir que serve {t['pessoas']} pessoas.")
    return {"disponiveis_extra": extras, "escolhas": escolhas}


def rota_checar(estado: Estado) -> str:
    return "fim" if estado.get("termino") else "chef"


def _passo_agente(estado: Estado, prompt_inicial: str, lista_ferramentas: list[dict],
                  fechamento: type, para_chamada) -> dict:
    """Uma volta do laço do agente: chama o modelo, que pode pedir ferramentas.

    Se o modelo responder em TEXTO (o qwen 7B às vezes escreve `responder(...)` em
    vez de chamar a ferramenta), o texto é tratado como "decidi parar" e uma
    segunda chamada, com saída estruturada, converte a decisão na ferramenta final.
    O modelo continua decidindo QUANDO parar; o schema garante a FORMA do fim."""
    if t := estouro(estado):
        return {"termino": t}
    if estado.get("passos_agente", 0) >= config.MAX_PASSOS_AGENTE:
        return {"termino": "teto_passos"}
    novas = []
    msgs = estado.get("agente_msgs") or []
    if not msgs:
        novas = [{"role": "system", "content": prompt_inicial}, {"role": "user", "content": "Comece."}]
    enviadas = [{k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_call_id")}
                for m in msgs + novas]
    resposta, uso = llm.com_ferramentas(enviadas, lista_ferramentas)
    if not resposta.get("tool_calls"):
        transcricao = "\n".join(f"[{m['role']}] {m.get('content', '')[:1500]}" for m in (msgs + novas)[1:] + [resposta])
        decisao, uso2 = llm.estruturada(prompt_inicial, f"Histórico da sua busca:\n{transcricao}\n\n"
                                        "Converta a sua decisão final no formato pedido. Use só ids que aparecem acima.",
                                        fechamento)
        uso = {k: uso.get(k, 0) + uso2.get(k, 0) for k in ("tokens", "chamadas", "segundos")} | {
            "maior_janela": max(uso.get("maior_janela", 0), uso2.get("maior_janela", 0))}
        nome, args = para_chamada(decisao)
        resposta["tool_calls"] = [{"id": f"fechamento-{estado.get('passos_agente', 0)}", "type": "function",
                                   "function": {"name": nome, "arguments": json.dumps(args, ensure_ascii=False)}}]
        resposta["fechamento_estruturado"] = True
    novas.append(resposta)
    return {"agente_msgs": novas, "passos_agente": estado.get("passos_agente", 0) + 1, "uso": uso}


def _fechar_chef(d: esquemas.FechamentoChef) -> tuple[str, dict]:
    if d.receita_id:
        return "propor_receita", {"receita_id": d.receita_id, "justificativa": d.justificativa}
    return "declarar_sem_opcao", {"motivo": d.justificativa}


def _fechar_consultor(d: esquemas.FechamentoConsultor) -> tuple[str, dict]:
    return "responder", d.model_dump()


def _ultimas_chamadas(estado: Estado) -> list[dict]:
    ultima = (estado.get("agente_msgs") or [{}])[-1]
    return ultima.get("tool_calls", []) if ultima.get("role") == "assistant" else []


def _laco(estado: Estado) -> bool:
    """Detector de laço: a mesma chamada (nome+argumentos) repetida no turno.

    `recursion_limit` só limita o dano; ele não detecta. Um agente preso repetindo
    a mesma busca gastaria o teto inteiro e terminaria como 'teto de passos'."""
    vistas = []
    for m in estado.get("agente_msgs") or []:
        for c in m.get("tool_calls", []):
            vistas.append((c["function"]["name"], json.dumps(llm.argumentos(c), sort_keys=True)))
    return len(vistas) != len(set(vistas))


def rota_agente(estado: Estado) -> str:
    # com o fechamento estruturado, toda volta termina em chamada de ferramenta
    return "fim" if estado.get("termino") else "ferramentas"


@no
def chef(estado: Estado) -> dict:  # MODELO
    t, perfil = estado["triagem"], estado["perfil"]
    regras = carregar("regras_procedurais").texto
    reprovacao = ""
    if estado.get("veredito") and not estado["veredito"]["aprovado"]:
        reprovacao = f"A proposta anterior foi REPROVADA: {estado['veredito']['motivo']} Escolha outra receita."
    prompt = sistema("chef", regras=regras, entrada=estado["entrada"],
                     perfil=json.dumps({k: perfil.get(k) for k in ("objetivo", "alergias", "restricoes")}, ensure_ascii=False),
                     estoque=", ".join(sorted(ctx_de(estado).disponiveis)),
                     recentes=", ".join(f"{r['receita_nome']} ({r['data']})" for r in estado.get("recentes", [])) or "nenhuma",
                     ingredientes=t["ingredientes_citados"] or "nenhum", pessoas=t.get("pessoas") or "-",
                     tempo=t.get("tempo_max_min") or "-", reprovacao=reprovacao)
    return _passo_agente(estado, prompt, ferramentas.FERRAMENTAS_CHEF, esquemas.FechamentoChef, _fechar_chef)


@no
def ferramentas_chef(estado: Estado) -> dict:
    if _laco(estado):
        return {"termino": "laco_detectado"}
    ctx, novas, saida = ctx_de(estado), [], {}
    for c in _ultimas_chamadas(estado):
        nome, args = c["function"]["name"], llm.argumentos(c)
        if nome == "propor_receita":
            receita = rag.receitas_por_id().get(args.get("receita_id", ""))
            if receita is None:
                resultado = json.dumps({"erro": f"receita '{args.get('receita_id')}' não existe. Use um id de buscar_receitas."})
            else:
                saida["proposta"] = {"receita_id": receita["id"], "justificativa": args.get("justificativa", "")}
                resultado = json.dumps({"ok": "proposta recebida para avaliação"})
        elif nome == "declarar_sem_opcao":
            saida["termino"] = "recusa_sem_base"
            saida["escolhas"] = [f"o chef não encontrou receita adequada: {args.get('motivo', '')}"]
            resultado = json.dumps({"ok": True})
        else:
            resultado = ferramentas.executar(ctx, nome, args)
        novas.append({"role": "tool", "tool_call_id": c["id"], "content": resultado})
    return {**saida, "agente_msgs": novas, "recuperacoes": ctx.recuperacoes}


def rota_ferramentas_chef(estado: Estado) -> str:
    if estado.get("termino"):
        return "fim"
    return "conferir" if estado.get("proposta") else "chef"


@no
def conferir_proposta(estado: Estado) -> dict:
    """Portão determinístico: alergia, restrição e ingrediente faltando. O modelo não decide isto."""
    receita = rag.receitas_por_id()[estado["proposta"]["receita_id"]]
    perfil, ctx = estado["perfil"], ctx_de(estado)
    marcadores, desconhecidas = memoria.marcadores_de_alergia(perfil.get("alergias", []))
    motivos = []
    if conflito := set(receita["alergenos"]) & marcadores:
        motivos.append(f"contém alérgeno do perfil ({', '.join(sorted(conflito))})")
    textos = " ".join(catalogo.normalizar(i["texto"]) for i in receita["ingredientes"])
    for a in desconhecidas:  # alergia que o catálogo não mapeia: procura o nome, por precaução
        if catalogo.normalizar(a) in textos:
            motivos.append(f"menciona '{a}', alergia do perfil")
    for r in perfil.get("restricoes", []):
        if proibidos := set(receita["itens"]) & memoria.RESTRICAO_PARA_ITENS.get(catalogo.normalizar(r), set()):
            motivos.append(f"viola a restrição '{r}' ({', '.join(sorted(proibidos))})")
    if faltando := set(receita["itens"]) - ctx.disponiveis:
        motivos.append(f"faltam no estoque: {', '.join(sorted(faltando))}")
    if not motivos:
        return {"veredito": None}
    return _reprovar(estado, "; ".join(motivos), "codigo")


def _reprovar(estado: Estado, motivo: str, por: str) -> dict:
    rodadas = estado.get("rodadas", 0) + 1
    saida = {"veredito": {"aprovado": False, "motivo": motivo, "por": por}, "rodadas": rodadas,
             "proposta": None, "passos_agente": 0, "rejeitadas": [estado["proposta"]["receita_id"]],
             # a reprovação precisa chegar ao chef como mensagem: o prompt de sistema só é montado na 1ª volta
             "agente_msgs": [{"role": "user", "content": f"Proposta {estado['proposta']['receita_id']} REPROVADA: {motivo}. "
                              "Proponha outra receita com viavel=true, ou declare que não há opção."}],
             "escolhas": [f"proposta {estado['proposta']['receita_id']} reprovada ({por}): {motivo}"]}
    if rodadas >= config.MAX_RODADAS_AVALIACAO:
        saida["termino"] = "teto_rodadas"
    return saida


def rota_conferir(estado: Estado) -> str:
    if estado.get("termino"):
        return "fim"
    return "chef" if estado.get("veredito") else "avaliador"


@no
def avaliador(estado: Estado) -> dict:  # MODELO (+ cálculo e recuperação fixos em código)
    if t := estouro(estado):
        return {"termino": t}
    receita = rag.receitas_por_id()[estado["proposta"]["receita_id"]]
    nutricao = nutricional.calcular(receita)
    objetivo = estado["perfil"].get("objetivo") or "alimentação saudável"
    oms = rag.buscar_oms(f"healthy diet recommendations: {objetivo}", k=1)
    trecho = oms.trechos[0][0] if oms.trechos else None
    veredito, uso = llm.estruturada(carregar("sistema").texto, carregar("avaliador").formatar(
        objetivo=objetivo, receita=f"{receita['nome']} — itens: {', '.join(receita['itens'])}",
        nutricao=nutricao.model_dump_json(), oms=trecho["texto"][:1500] if trecho else "(nenhum trecho)"),
        esquemas.Veredito)
    saida = {"nutricao": nutricao.model_dump(), "uso": uso,
             "recuperacoes": [{"indice": "oms", "consulta": f"healthy diet recommendations: {objetivo}",
                               "ids": [t["id"] for t, _ in oms.trechos], "descartados": oms.descartados}],
             "descartes_oms": oms.descartados}
    if trecho:
        saida["fontes"] = [{"tipo": "oms", "id": trecho["id"], "detalhe": f"critério do avaliador ({trecho['data_publicacao']})"}]
    if not nutricao.completa:
        saida["escolhas"] = [f"cálculo nutricional parcial: fora do cálculo {', '.join(nutricao.fora_do_calculo)}"]
    if veredito.aprovado:
        return {**saida, "veredito": {"aprovado": True, "motivo": veredito.motivo, "por": "modelo"}}
    reprovado = _reprovar(estado, veredito.motivo, "modelo")
    return {**saida, **reprovado, "escolhas": saida.get("escolhas", []) + reprovado["escolhas"]}


def rota_avaliador(estado: Estado) -> str:
    if estado.get("termino"):
        return "fim"
    return "registrar" if estado["veredito"]["aprovado"] else "chef"


@no
def registrar(estado: Estado) -> dict:
    receita = rag.receitas_por_id()[estado["proposta"]["receita_id"]]
    vetor = memoria.embedding_episodio(estado["entrada"], receita["nome"])
    efeito = db.registrar_recomendacao(estado["usuario_id"], receita, estado["entrada"],
                                       (estado.get("nutricao") or {}).get("energia_kcal"), vetor)
    codigos = sorted({catalogo.itens()[i]["tbca"] for i in receita["itens"] if catalogo.itens()[i]["tbca"]})
    return {"efeito": efeito, "termino": "concluido",
            "fontes": [{"tipo": "receita", "id": receita["id"], "detalhe": receita["fonte"]},
                       {"tipo": "tbca", "id": ",".join(codigos), "detalhe": "composição por 100 g"}]}


# --- pergunta (consultor) ------------------------------------------------------------

@no
def consultor(estado: Estado) -> dict:  # MODELO
    return _passo_agente(estado, sistema("consultor", entrada=estado["entrada"]), ferramentas.FERRAMENTAS_CONSULTOR,
                         esquemas.FechamentoConsultor, _fechar_consultor)


@no
def ferramentas_consultor(estado: Estado) -> dict:
    if _laco(estado):
        return {"termino": "laco_detectado"}
    ctx, novas, saida = ctx_de(estado), [], {}
    for c in _ultimas_chamadas(estado):
        nome, args = c["function"]["name"], llm.argumentos(c)
        if nome == "responder":
            # portão de citação: todo número da resposta tem de estar no que as ferramentas devolveram
            textos = [m["content"] for m in estado.get("agente_msgs", []) + novas if m.get("role") == "tool"]
            textos.append(estado["entrada"])  # número que a própria pessoa disse ("30%") não é invenção
            sem_fonte = citacao.nao_sustentados(args.get("resposta", ""), textos)
            achou = any(r["ids"] for r in ctx.recuperacoes + estado.get("recuperacoes", []))
            if sem_fonte:
                saida["termino"] = "recusa_sem_base"
                saida["escolhas"] = [f"resposta do modelo descartada: número(s) {', '.join(sorted(sem_fonte))} "
                                     "não aparece(m) em nenhuma fonte consultada"]
                saida["resposta_consultor"] = {**args, "descartada": True}
            else:
                # parcial: o modelo diz que faltou algo, mas alguma busca trouxe dado
                saida["resposta_consultor"] = {**args, "parcial": not args.get("suficiente") and achou}
                saida["termino"] = "concluido" if args.get("suficiente") or achou else "recusa_sem_base"
            resultado = json.dumps({"ok": True})
        else:
            resultado = ferramentas.executar(ctx, nome, args)
        novas.append({"role": "tool", "tool_call_id": c["id"], "content": resultado})
    fontes = []
    for r in ctx.recuperacoes:
        tipo = "tbca" if r["indice"] == "tbca" else "oms"
        fontes += [{"tipo": tipo, "id": i, "detalhe": f"consulta: {r['consulta']}"} for i in r["ids"]]
    return {**saida, "agente_msgs": novas, "recuperacoes": ctx.recuperacoes, "descartes_oms": ctx.descartes_oms,
            "fontes": fontes}


def rota_ferramentas_consultor(estado: Estado) -> str:
    r = estado.get("resposta_consultor")
    if r and not r.get("descartada") and estado.get("termino") == "concluido":
        return "verificar"
    return "fim" if estado.get("termino") else "consultor"


@no
def verificar_resposta(estado: Estado) -> dict:  # MODELO + código
    """Segunda linha contra resposta sem fonte (a primeira é o portão de números).

    O modelo julga se as fontes tratam do assunto e COPIA o trecho; o código confere
    que o trecho existe. Julgamento sem trecho conferível não vale."""
    if t := estouro(estado):
        return {"termino": t}
    r = estado["resposta_consultor"]
    textos = [m["content"] for m in estado.get("agente_msgs", []) if m.get("role") == "tool"]
    # O código sabe quais buscas voltaram vazias: as frases sobre esses termos ("não encontrei
    # tofu") não são afirmação, e o verificador 7B as contava contra a resposta.
    falhas = [catalogo.normalizar(x["consulta"]) for x in estado.get("recuperacoes", []) if not x["ids"]]
    frases = [f for f in re.split(r"(?<=[.!?])\s+", r["resposta"])
              if not any(termo and termo in catalogo.normalizar(f) for termo in falhas)]
    afirmado = " ".join(frases).strip()
    if not afirmado:
        return {"termino": "recusa_sem_base", "resposta_consultor": {**r, "descartada": True},
                "escolhas": ["a resposta só dizia o que não foi encontrado"]}
    suporte, uso = llm.estruturada(carregar("sistema").texto, carregar("verificador").formatar(
        resposta=afirmado, fontes="\n---\n".join(t[:2500] for t in textos)),
        esquemas.Suporte)
    existe = citacao.trecho_existe(suporte.trecho_citado, textos)
    registro = {"sustentada": suporte.sustentada, "trecho_citado": suporte.trecho_citado,
                "trecho_existe_na_fonte": existe, "assunto_sem_fonte": suporte.assunto_sem_fonte}
    if suporte.sustentada and existe:
        return {"uso": uso, "resposta_consultor": {**r, "verificacao": registro}}
    motivo = ("o verificador não achou nas fontes o assunto da pergunta" if not suporte.sustentada
              else "o trecho citado como prova não existe nas fontes")
    return {"uso": uso, "termino": "recusa_sem_base", "resposta_consultor": {**r, "descartada": True, "verificacao": registro},
            "escolhas": [f"resposta do modelo descartada: {motivo}"
                         + (f" ({suporte.assunto_sem_fonte})" if suporte.assunto_sem_fonte else "")]}


# --- estoque, com pausa para aprovação --------------------------------------------------

@no
def extrair_itens(estado: Estado) -> dict:  # MODELO
    itens, uso = llm.estruturada(carregar("sistema").texto, carregar("extrair_itens").formatar(entrada=estado["entrada"]),
                                 esquemas.ItensExtraidos)
    return {"itens_ditos": [i.model_dump() for i in itens.itens], "uso": uso}


@no
def casar_catalogo(estado: Estado) -> dict:
    propostos, pendentes = [], []
    for dito in estado.get("itens_ditos", []):
        casamento = catalogo.casar_pt(dito["nome"])
        if casamento.status == "reconhecido":
            item = catalogo.itens()[casamento.candidatos[0]]
            propostos.append({"item_id": item["id"], "nome": item["nome"],
                              "quantidade": dito["quantidade"] or 1, "unidade": dito["unidade"] or "un",
                              "quantidade_informada": dito["quantidade"] is not None})
        else:
            pendentes.append({"nome": dito["nome"], "motivo": casamento.status,
                              "candidatos": casamento.candidatos})
    if not propostos and not pendentes:
        return {"termino": "sem_acao", "escolhas": ["não encontrei nenhum item de comida na mensagem"]}
    # o prazo é gravado AQUI, antes da pausa: a retomada roda `confirmar_estoque` de novo do começo
    return {"itens_propostos": propostos, "pendentes": pendentes, "expira_em": time.time() + config.PRAZO_APROVACAO_S}


def rota_casar(estado: Estado) -> str:
    return "fim" if estado.get("termino") else "confirmar"


def pausa_estoque(estado: Estado) -> dict:
    linhas = [f"  - {i['nome']}: {i['quantidade']:g} {i['unidade']}" + ("" if i["quantidade_informada"] else
              "  (quantidade não informada: supus 1)") for i in estado["itens_propostos"]] or ["  (nenhum)"]
    pend = [f"  ? {p['nome']}: " + (f"ambíguo entre {', '.join(p['candidatos'])}" if p["candidatos"] else
            "não está no catálogo") + " — NÃO será gravado, a menos que você edite" for p in estado["pendentes"]]
    expira = datetime.fromtimestamp(estado["expira_em"]).isoformat(timespec="seconds")
    texto = carregar("pausa_estoque").formatar(usuario=estado["usuario_id"], itens="\n".join(linhas),
                                               pendentes="Pendentes:\n" + "\n".join(pend) if pend else "",
                                               expira_em=expira)
    return {"acao": "estoque.somar", "usuario_id": estado["usuario_id"], "itens": estado["itens_propostos"],
            "pendentes": estado["pendentes"], "expira_em": expira, "texto": texto,
            "respostas_aceitas": ["aprovar", "rejeitar", "editar"]}


@no
def confirmar_estoque(estado: Estado) -> dict:
    # Nada com efeito colateral antes do interrupt: este nó roda de novo na retomada.
    resposta = interrupt(pausa_estoque(estado))
    acao = (resposta or {}).get("acao")
    if time.time() > estado["expira_em"] or acao == "expirar":
        return {"decisao_humana": {"acao": "expirada"}, "termino": "aprovacao_expirada"}
    if acao == "aprovar":
        return {"decisao_humana": {"acao": "aprovar", "itens": estado["itens_propostos"]}}
    if acao == "editar":
        itens, invalidos = [], []
        for i in resposta.get("itens", []):
            if i.get("item_id") in catalogo.itens() and float(i.get("quantidade") or 0) > 0:
                itens.append({"item_id": i["item_id"], "nome": catalogo.itens()[i["item_id"]]["nome"],
                              "quantidade": float(i["quantidade"]), "unidade": i.get("unidade") or "un"})
            else:
                invalidos.append(i)
        if invalidos or not itens:
            return {"decisao_humana": {"acao": "edicao_invalida", "invalidos": invalidos},
                    "termino": "rejeitado_pelo_humano"}
        return {"decisao_humana": {"acao": "editar", "itens": itens}}
    return {"decisao_humana": {"acao": "rejeitar"}, "termino": "rejeitado_pelo_humano"}


def rota_confirmar(estado: Estado) -> str:
    return "fim" if estado.get("termino") else "gravar"


@no
def gravar_estoque(estado: Estado) -> dict:
    efeito = db.somar_estoque(estado["usuario_id"], estado["decisao_humana"]["itens"])
    return {"efeito": efeito, "termino": "concluido",
            "fontes": [{"tipo": "usuario", "id": estado["execucao_id"], "detalhe": "aprovação humana da lista"}]}


# --- perfil ----------------------------------------------------------------------------

@no
def extrair_perfil(estado: Estado) -> dict:  # MODELO
    atualizacao, uso = llm.estruturada(carregar("sistema").texto,
                                       carregar("extrair_perfil").formatar(entrada=estado["entrada"]),
                                       esquemas.AtualizacaoPerfil)
    return {"atualizacao_perfil": atualizacao.model_dump(), "uso": uso,
            "expira_em": time.time() + config.PRAZO_APROVACAO_S}


def rota_perfil(estado: Estado) -> str:
    if estado.get("termino"):
        return "fim"
    a = estado["atualizacao_perfil"]
    # tirar uma alergia volta a liberar receitas com o alérgeno: é a escrita mais perigosa do sistema
    return "confirmar" if (a["campo"], a["operacao"]) == ("alergias", "remover") else "gravar"


@no
def confirmar_perfil(estado: Estado) -> dict:
    a = estado["atualizacao_perfil"]
    resposta = interrupt({"acao": "perfil.remover_alergia", "usuario_id": estado["usuario_id"], "valor": a["valor"],
                          "expira_em": datetime.fromtimestamp(estado["expira_em"]).isoformat(timespec="seconds"),
                          "texto": f"Vou REMOVER '{a['valor']}' das suas alergias. Consequência: receitas com "
                                   f"{a['valor']} voltam a ser sugeridas. Responda aprovar ou rejeitar.",
                          "respostas_aceitas": ["aprovar", "rejeitar"]})
    acao = (resposta or {}).get("acao")
    if time.time() > estado["expira_em"] or acao == "expirar":
        return {"decisao_humana": {"acao": "expirada"}, "termino": "aprovacao_expirada"}
    if acao != "aprovar":
        return {"decisao_humana": {"acao": "rejeitar"}, "termino": "rejeitado_pelo_humano"}
    return {"decisao_humana": {"acao": "aprovar"}}


@no
def gravar_perfil(estado: Estado) -> dict:
    a = estado["atualizacao_perfil"]
    efeito = db.atualizar_perfil(estado["usuario_id"], a["campo"], a["operacao"], a["valor"])
    return {"efeito": efeito, "termino": "concluido",
            "fontes": [{"tipo": "usuario", "id": estado["execucao_id"], "detalhe": "mensagem da pessoa"}]}


# --- saída --------------------------------------------------------------------------

ESCOPO = ("Eu recomendo refeições com o que você tem em casa, registro compras no seu estoque, "
          "atualizo seu perfil (objetivo, alergias, restrições) e respondo dúvidas de nutrição com base na OMS e na TBCA.")


@no
def finalizar(estado: Estado) -> dict:
    saida = montar_saida(estado)
    return {"saida": saida.model_dump(),
            "conversa": [{"role": "user", "content": estado["entrada"]}, {"role": "assistant", "content": saida.resultado}]}


def montar_saida(estado: Estado) -> esquemas.Saida:
    termino = estado.get("termino") or "concluido"
    rota = (estado.get("triagem") or {}).get("rota")
    base = {"execucao_id": estado["execucao_id"], "thread_id": estado["thread_id"], "termino": termino,
            "fontes": _fontes_da_rota(estado, _sem_repetir(estado.get("fontes", []))),
            "escolhas_declaradas": estado.get("escolhas", [])}
    efeito = estado.get("efeito") or {}

    if termino == "erro_fatal":
        return esquemas.Saida(**base, tipo="erro", resultado="Não consegui processar agora (falha interna). Tente de novo.",
                              suficiencia="insuficiente", motivo_suficiencia=estado.get("erro"))
    if termino == "recusa_fora_escopo":
        return esquemas.Saida(**base, tipo="recusa", suficiencia="fora_de_escopo",
                              resultado=f"Isso está fora do que eu faço. {ESCOPO}",
                              motivo_suficiencia=estado["triagem"]["justificativa"])
    if termino == "sem_acao":
        texto = ("Não registrei nada: você falou do que ainda vai fazer, e eu só registro o que já aconteceu. "
                 "Também não envio lembretes. Quando comprar, me diga o que chegou."
                 if rota != "estoque" else "Não encontrei itens de comida para registrar.")
        return esquemas.Saida(**base, tipo="resposta", suficiencia="suficiente", resultado=texto)
    if termino == "pergunta_ao_usuario":
        if estado.get("perfil") is None:
            texto = ("Ainda não conheço você. Antes de recomendar, me diga: qual é o seu objetivo (ex.: emagrecer, "
                     "manter o peso, ganhar massa) e se você tem alguma alergia ou restrição alimentar.")
        else:
            texto = "Seu estoque está vazio. O que você tem em casa agora? Posso registrar e sugerir a partir disso."
        return esquemas.Saida(**base, tipo="pergunta", suficiencia="incompleta", resultado=texto,
                              motivo_suficiencia="; ".join(estado.get("escolhas", [])))
    if rota in ("estoque", "perfil"):
        return _saida_escrita(estado, base, efeito, termino)
    if rota == "pergunta":
        r = estado.get("resposta_consultor") or {}
        if termino == "concluido":
            vazias = [f"{x['indice']}:'{x['consulta']}'" for x in estado.get("recuperacoes", []) if not x["ids"]]
            if r.get("parcial"):
                return esquemas.Saida(**base, tipo="resposta", resultado=r["resposta"], suficiencia="parcial",
                                      motivo_suficiencia="parte da pergunta sem base; buscas sem resultado: " + "; ".join(vazias))
            return esquemas.Saida(**base, tipo="resposta", resultado=r["resposta"], suficiencia="suficiente")
        # Na recusa, o texto é montado por CÓDIGO a partir do que as buscas não acharam:
        # o texto do modelo, quando ele não tem base, tende a completar com conhecimento próprio.
        return esquemas.Saida(**base, tipo="recusa", suficiencia="insuficiente", resultado=_recusa_consulta(estado),
                              motivo_suficiencia=f"término: {termino}; buscas sem resultado: "
                              + "; ".join(f"{x['indice']}:'{x['consulta']}'" for x in estado.get("recuperacoes", []) if not x["ids"]))
    # recomendação
    if termino == "concluido":
        receita = rag.receitas_por_id()[estado["proposta"]["receita_id"]]
        ctx = ctx_de(estado)
        nut = esquemas.Nutricao(**estado["nutricao"]) if estado.get("nutricao") else None
        rs = esquemas.ReceitaSaida(id=receita["id"], nome=receita["nome"],
                                   ingredientes=[i["texto"] for i in receita["ingredientes"]],
                                   faltando_no_estoque=sorted(set(receita["itens"]) - ctx.disponiveis), nutricao=nut)
        kcal = f" A receita inteira tem cerca de {nut.energia_kcal:.0f} kcal e {nut.proteina_g:.0f} g de proteína (TBCA)." if nut else ""
        repetida = " (Essa recomendação já estava registrada hoje.)" if efeito.get("ja_existia") else ""
        return esquemas.Saida(**base, tipo="recomendacao", receita=rs, suficiencia="suficiente",
                              resultado=f"Sugestão: {receita['nome']}. {estado['proposta']['justificativa']}{kcal}{repetida}")
    motivos = {"teto_rodadas": "nenhuma das propostas passou na avaliação",
               "recusa_sem_base": "não encontrei receita no acervo que sirva",
               "teto_passos": "atingi o limite de passos da busca", "laco_detectado": "a busca entrou em repetição",
               "teto_tempo": "atingi o limite de tempo", "teto_tokens": "atingi o limite de tokens"}
    return esquemas.Saida(**base, tipo="recusa", suficiencia="insuficiente",
                          resultado=f"Não tenho uma recomendação segura agora: {motivos.get(termino, termino)}. "
                                    "Me diga outro ingrediente que você tenha, ou registre suas compras.",
                          motivo_suficiencia=motivos.get(termino, termino))


def _recusa_consulta(estado: Estado) -> str:
    vazias = [x for x in estado.get("recuperacoes", []) if not x["ids"]]
    nao_achei = ", ".join(f"'{x['consulta']}'" for x in vazias if x["indice"] == "tbca")
    exemplos = ", ".join(sorted(i["nome"] for i in catalogo.itens().values() if i["tbca"])[:12])
    texto = (f"Não encontrei {nao_achei} na tabela de composição que eu uso (um recorte da TBCA). "
             if nao_achei else "Não encontrei nas minhas fontes (TBCA e fichas da OMS) a informação para responder isso. ")
    return texto + (f"Consigo informar a composição de alimentos como {exemplos}, e as recomendações da OMS "
                    "sobre alimentação saudável e sódio. Para outros alimentos, consulte um nutricionista.")


def _fontes_da_rota(estado: Estado, fontes: list[dict]) -> list[dict]:
    """Fonte é o que SUSTENTA o resultado, e não tudo o que foi carregado."""
    rota, termino = (estado.get("triagem") or {}).get("rota"), estado.get("termino")
    if termino in ("recusa_fora_escopo", "sem_acao", "erro_fatal"):
        return []
    permitidos = {"pergunta": {"oms", "tbca"}, "estoque": {"usuario", "estoque"}, "perfil": {"usuario", "perfil"}}.get(rota)
    return [f for f in fontes if permitidos is None or f["tipo"] in permitidos]


def _saida_escrita(estado, base, efeito, termino) -> esquemas.Saida:
    tipo = "estoque" if estado["triagem"]["rota"] == "estoque" else "perfil"
    if termino == "aprovacao_expirada":
        texto = "O prazo para aprovar acabou. Nada foi gravado."
    elif termino == "rejeitado_pelo_humano":
        texto = "Você não aprovou. Nada foi gravado."
    elif efeito.get("ja_existia"):
        texto = "Isso já estava registrado (mesma lista, mesmo dia). Nada foi gravado de novo."
    elif tipo == "estoque":
        itens = ", ".join(f"{i['nome']} ({i['quantidade']:g} {i['unidade']})" for i in estado["decisao_humana"]["itens"])
        texto = f"Estoque atualizado: {itens}."
    else:
        a = estado["atualizacao_perfil"]
        texto = f"Perfil atualizado: {a['campo']} — {a['operacao']} '{a['valor']}'."
    pend = {"efeito": efeito} if efeito else None
    return esquemas.Saida(**base, tipo=tipo, resultado=texto, suficiencia="suficiente", pendencia=pend)


def _sem_repetir(fontes: list[dict]) -> list[dict]:
    vistas, saida = set(), []
    for f in fontes:
        chave_f = (f["tipo"], f["id"])
        if chave_f not in vistas:
            vistas.add(chave_f)
            saida.append(f)
    return saida


def saida_da_pausa(estado: Estado, pausa: dict) -> esquemas.Saida:
    """A execução parou num `interrupt`: a saída diz o que espera e até quando."""
    return esquemas.Saida(execucao_id=estado["execucao_id"], thread_id=estado["thread_id"], tipo="aguardando_aprovacao",
                          resultado=pausa["texto"], suficiencia="suficiente", pendencia=pausa,
                          fontes=_sem_repetir(estado.get("fontes", [])), escolhas_declaradas=estado.get("escolhas", []),
                          termino="aguardando_humano")


# --- montagem -------------------------------------------------------------------------

def construir(reducer_fontes: bool = True) -> StateGraph:
    g = StateGraph(Estado if reducer_fontes else EstadoSemReducer)

    def t(fn):
        # o LangGraph lê o schema da anotação de nós e rotas; na variante sem reducer, nada pode impor `Estado`
        return fn if reducer_fontes else (lambda e, _f=fn: _f(e))

    for nome, fn in [("inicio", inicio), ("carregar_perfil", carregar_perfil), ("carregar_estoque", carregar_estoque),
                     ("carregar_historico", carregar_historico), ("triagem", triagem), ("recusar", recusar),
                     ("nao_agir", nao_agir), ("checar_pedido", checar_pedido), ("chef", chef),
                     ("ferramentas_chef", ferramentas_chef), ("conferir_proposta", conferir_proposta),
                     ("avaliador", avaliador), ("registrar", registrar), ("consultor", consultor),
                     ("ferramentas_consultor", ferramentas_consultor), ("verificar_resposta", verificar_resposta),
                     ("extrair_itens", extrair_itens),
                     ("casar_catalogo", casar_catalogo), ("confirmar_estoque", confirmar_estoque),
                     ("gravar_estoque", gravar_estoque), ("extrair_perfil", extrair_perfil),
                     ("confirmar_perfil", confirmar_perfil), ("gravar_perfil", gravar_perfil), ("finalizar", finalizar)]:
        g.add_node(nome, t(fn))

    g.add_edge(START, "inicio")
    for carregador in ("carregar_perfil", "carregar_estoque", "carregar_historico"):
        g.add_edge("inicio", carregador)                      # paralelo: três ramos
    g.add_edge(["carregar_perfil", "carregar_estoque", "carregar_historico"], "triagem")  # junção
    g.add_conditional_edges("triagem", t(rota_triagem), {
        "recomendar": "checar_pedido", "estoque": "extrair_itens", "perfil": "extrair_perfil",
        "pergunta": "consultor", "fora_escopo": "recusar", "nao_agir": "nao_agir", "fim": "finalizar"})
    g.add_edge("recusar", "finalizar")
    g.add_edge("nao_agir", "finalizar")
    g.add_conditional_edges("checar_pedido", t(rota_checar), {"chef": "chef", "fim": "finalizar"})
    g.add_conditional_edges("chef", t(rota_agente), {"ferramentas": "ferramentas_chef", "fim": "finalizar"})
    g.add_conditional_edges("ferramentas_chef", t(rota_ferramentas_chef),
                            {"conferir": "conferir_proposta", "chef": "chef", "fim": "finalizar"})
    g.add_conditional_edges("conferir_proposta", t(rota_conferir), {"avaliador": "avaliador", "chef": "chef", "fim": "finalizar"})
    g.add_conditional_edges("avaliador", t(rota_avaliador), {"registrar": "registrar", "chef": "chef", "fim": "finalizar"})
    g.add_edge("registrar", "finalizar")
    g.add_conditional_edges("consultor", t(rota_agente), {"ferramentas": "ferramentas_consultor", "fim": "finalizar"})
    g.add_conditional_edges("ferramentas_consultor", t(rota_ferramentas_consultor),
                            {"verificar": "verificar_resposta", "consultor": "consultor", "fim": "finalizar"})
    g.add_edge("verificar_resposta", "finalizar")
    g.add_edge("extrair_itens", "casar_catalogo")
    g.add_conditional_edges("casar_catalogo", t(rota_casar), {"confirmar": "confirmar_estoque", "fim": "finalizar"})
    g.add_conditional_edges("confirmar_estoque", t(rota_confirmar), {"gravar": "gravar_estoque", "fim": "finalizar"})
    g.add_edge("gravar_estoque", "finalizar")
    g.add_conditional_edges("extrair_perfil", t(rota_perfil),
                            {"confirmar": "confirmar_perfil", "gravar": "gravar_perfil", "fim": "finalizar"})
    g.add_conditional_edges("confirmar_perfil", t(rota_confirmar), {"gravar": "gravar_perfil", "fim": "finalizar"})
    g.add_edge("gravar_perfil", "finalizar")
    g.add_edge("finalizar", END)
    return g


@cache
def checkpointer() -> SqliteSaver:
    config.DB_CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(config.DB_CHECKPOINTS, check_same_thread=False))


@cache
def obter_grafo():
    """O grafo compilado UMA vez por processo; é este objeto que src.main executa e conferir_grafo.py importa."""
    db.iniciar()
    return construir().compile(checkpointer=checkpointer())
