"""Linha de comando do agente.

    python -m src.main --usuario ana "o que eu faço pra janta?"
    python -m src.main --usuario ana --sessao s2 "comprei leite e 6 ovos"   # pode pausar
    python -m src.main --usuario ana --sessao s2 --aprovar
    python -m src.main --usuario ana --sessao s2 --editar '[{"item_id":"leite_integral","quantidade":1,"unidade":"l"}]'
    python -m src.main --usuario ana --sessao s2 --rejeitar
    python -m src.main --pendentes [--expirar]

O `thread_id` é `usuario:sessao`. Mesma sessão = mesma conversa (o checkpoint
guarda o histórico); sessão nova = conversa nova, mas a memória de longo prazo
(perfil, estoque, histórico) é a mesma.
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime

from langgraph.types import Command

from . import acesso, config, esquemas, integridade, telemetria, validacao
from .grafo import montar_saida, obter_grafo, saida_da_pausa
from .registro import Registro


def executar(usuario: str, sessao: str, entrada=None, retomada: dict | None = None, nome_log: str | None = None,
             checkpoint_id: str | None = None) -> dict:
    """`checkpoint_id` retoma a partir de um ponto do passado: é como se a mesma
    aprovação chegasse de novo no momento da pausa (prova de docs/humano.md §8.5)."""
    thread_id = f"{usuario}:{sessao}"
    registro = Registro(nome_log or f"{usuario}-{sessao}", thread_id, usuario,
                        validacao.redigir(entrada) if isinstance(entrada, str) else retomada)
    with telemetria.execucao(registro.caminho.stem, {
            "gen_ai.conversation.id": thread_id, "nutri.usuario_id": usuario, "nutri.commit": registro.commit,
            # o trace guarda a entrada SEM dado pessoal que não serve à decisão (CPF, e-mail, telefone)
            "nutri.entrada": validacao.redigir(entrada) if entrada else None, "nutri.retomada": retomada,
            "gen_ai.request.model": config.LLM_MODELO,
            "nutri.modelo": registro.modelo, "nutri.prompts": [f"{k}={v}" for k, v in registro.prompts.items()],
            "nutri.indices": [f"{k}={v}" for k, v in registro.indices.items()], "nutri.log_detalhe": str(registro.caminho),
            "nutri.parametros": {"temperature": config.TEMPERATURA, "top_p": config.TOP_P}}) as raiz:
        registro.nota("trace", trace_id=telemetria.id_do_trace(raiz), arquivo=telemetria.caminho_trace())
        negado = _portao_de_entrada(usuario, thread_id, raiz, retomada)
        if negado is not None:
            saida, valores = negado, {}
            registro.saida(saida)
        else:
            saida, valores = _executar(usuario, thread_id, entrada, retomada, checkpoint_id, registro)
        _registrar_decisao(raiz, usuario, saida, valores, retomada)
    return {"saida": saida, "log": str(registro.caminho), "trace": telemetria.caminho_trace(),
            "trace_id": telemetria.id_do_trace(raiz)}


def _negar(thread_id: str, termino: str, resultado: str, motivo: str) -> dict:
    return esquemas.Saida(execucao_id=uuid.uuid4().hex[:10], thread_id=thread_id, tipo="erro", resultado=resultado,
                          suficiencia="insuficiente", motivo_suficiencia=motivo, termino=termino).model_dump()


def _identidade_ok(usuario: str, retomada: dict | None) -> bool:
    token = os.getenv("NUTRI_TOKEN")
    if acesso.autenticar(usuario, token):
        return True
    # o operador pode EXPIRAR a pausa de qualquer um (--pendentes --expirar); expirar nunca grava nada
    return (retomada or {}).get("acao") == "expirar" and acesso.autenticar(acesso.OPERADOR, token, papel=acesso.OPERADOR)


def _portao_de_entrada(usuario: str, thread_id: str, raiz, retomada: dict | None = None) -> dict | None:
    """Os três controles que rodam ANTES de qualquer nó do grafo, na ordem: integridade dos
    dados (C2), suspensão pelo operador (C5) e identidade (C1). Todos fail-closed: na dúvida,
    a execução não acontece. Devolve a saída da negação, ou None para seguir."""
    try:
        integridade.exigir()
    except integridade.IntegridadeViolada as erro:
        telemetria.definir(raiz, {"nutri.controle": "C2_integridade", "nutri.controle.motivo": str(erro)[:1000]})
        return _negar(thread_id, "integridade_violada", "O sistema está bloqueado: os dados de receitas ou nutrição "
                      "não conferem com o manifesto. Nada foi executado. Avise o responsável.", str(erro))
    if (s := acesso.suspensao()) is not None:
        telemetria.definir(raiz, {"nutri.controle": "C5_suspensao", "nutri.controle.motivo": s.get("motivo")})
        return _negar(thread_id, "suspenso", "O agente está suspenso pelo operador. Nada foi executado.",
                      f"suspenso por {s.get('por')} em {s.get('em')}: {s.get('motivo')}")
    if not _identidade_ok(usuario, retomada):
        telemetria.definir(raiz, {"nutri.controle": "C1_identidade",
                                  "nutri.controle.motivo": "NUTRI_TOKEN ausente ou não prova o --usuario"})
        return _negar(thread_id, "acesso_negado", f"Acesso negado: o token informado não é de '{usuario}'. "
                      "Defina NUTRI_TOKEN com o seu token.", "NUTRI_TOKEN ausente ou de outro usuário")
    return None


def _executar(usuario, thread_id, entrada, retomada, checkpoint_id, registro) -> tuple[dict, dict]:
    grafo = obter_grafo()
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": config.RECURSION_LIMIT}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id

    if retomada is not None:
        if not grafo.get_state(cfg).next:
            registro.nota("nada pendente nesta conversa: a retomada não executou nenhum nó")
            saida = {"thread_id": thread_id, "tipo": "resposta", "resultado": "Não há nada aguardando aprovação nesta conversa.",
                     "termino": "sem_acao", "suficiencia": "suficiente"}
            registro.saida(saida)
            return saida, {}
        entrada_grafo = Command(resume=retomada)
    else:
        entrada_grafo = {"entrada": entrada, "usuario_id": usuario, "thread_id": thread_id}

    for atualizacao in grafo.stream(entrada_grafo, cfg, stream_mode="updates"):
        for no, valor in atualizacao.items():
            registro.evento(no, valor)

    estado = grafo.get_state({"configurable": {"thread_id": thread_id}})
    pausas = [i.value for t in estado.tasks for i in t.interrupts]
    if pausas:
        saida = saida_da_pausa(estado.values, pausas[0]).model_dump()
    else:
        saida = estado.values.get("saida") or montar_saida(estado.values).model_dump()
    saida["uso"] = estado.values.get("uso")
    registro.saida(saida)
    return saida, estado.values


def _sinais_de_responsabilidade(saida: dict, valores: dict) -> dict:
    """Os dois modos de falha que não aparecem como erro (docs/observabilidade.md §3), calculados
    em código na hora: devem ser SEMPRE false. Não levam dado pessoal: só o booleano."""
    from . import memoria, rag
    sinais = {}
    receita = (saida.get("receita") or {}).get("id")
    if receita and valores.get("perfil") is not None:
        marcadores, _ = memoria.marcadores_de_alergia(valores["perfil"].get("alergias", []))
        sinais["nutri.alergeno_na_saida"] = bool(set(rag.receitas_por_id()[receita]["alergenos"]) & marcadores)
    if (valores.get("efeito") or {}).get("gravados") and (valores.get("triagem") or {}).get("rota") == "estoque":
        sinais["nutri.escrita_sem_aprovacao"] = (valores.get("decisao_humana") or {}).get("acao") not in ("aprovar", "editar")
    return sinais


def _registrar_decisao(raiz, usuario: str, saida: dict, valores: dict, retomada: dict | None) -> None:
    """Os atributos da raiz que respondem, só pelo trace: o que o agente decidiu, com base
    em quê e sob qual versão (docs/model-card.md §11). A entrada e as versões já foram postas
    na abertura; aqui entram o contexto recuperado, a saída, o término e a aprovação."""
    receita = saida.get("receita") or {}
    telemetria.definir(raiz, {
        "nutri.execucao_id": saida.get("execucao_id") or valores.get("execucao_id"),
        "nutri.rota": (valores.get("triagem") or {}).get("rota"),
        "nutri.triagem": valores.get("triagem"),
        "nutri.termino": saida.get("termino"), "nutri.tipo": saida.get("tipo"),
        "nutri.suficiencia": saida.get("suficiencia"),
        "nutri.saida.resultado": (saida.get("resultado") or "")[:2000],
        "nutri.saida.receita_id": receita.get("id"),
        "nutri.fontes": [f"{f['tipo']}:{f['id']}" for f in saida.get("fontes", [])],
        "nutri.contexto.recuperado": [f"{r['indice']}:{i}" for r in valores.get("recuperacoes") or [] for i in r["ids"]],
        "nutri.contexto.descartado": [d["id"] for d in valores.get("descartes_oms") or []],
        "nutri.escolhas": saida.get("escolhas_declaradas", []),
        "nutri.veredito": valores.get("veredito"), "nutri.rodadas": valores.get("rodadas"),
        "nutri.efeito": valores.get("efeito"),
        "nutri.uso.tokens": (saida.get("uso") or {}).get("tokens"),
        "nutri.uso.chamadas": (saida.get("uso") or {}).get("chamadas"),
        "nutri.uso.segundos_modelo": (saida.get("uso") or {}).get("segundos"),
        **_sinais_de_responsabilidade(saida, valores),
    })
    if saida.get("termino") == "aguardando_humano":
        pend = saida.get("pendencia") or {}
        telemetria.definir(raiz, {"nutri.pausa.acao": pend.get("acao"), "nutri.pausa.expira_em": pend.get("expira_em"),
                                  "nutri.pausa.itens": pend.get("itens") or pend.get("valor")})
    if retomada is not None:
        # quem aprovou é a identidade da sessão que retomou (a CLI), e não o modelo
        decisao = valores.get("decisao_humana") or {}
        quem = acesso.OPERADOR if retomada.get("acao") == "expirar" else usuario   # autenticado em _portao_de_entrada
        telemetria.definir(raiz, {"nutri.aprovacao.acao": retomada.get("acao"), "nutri.aprovacao.quem": quem,
                                  "nutri.aprovacao.quando": datetime.now().isoformat(timespec="seconds"),
                                  "nutri.aprovacao.o_que": decisao.get("itens") or (valores.get("atualizacao_perfil")
                                                                                   if decisao else None),
                                  "nutri.aprovacao.resultado": decisao.get("acao")})


def pendentes(expirar: bool) -> list[dict]:
    """Lista as conversas paradas em `interrupt`; com --expirar, encerra as vencidas sem gravar nada."""
    grafo = obter_grafo()
    threads = {c.config["configurable"]["thread_id"] for c in grafo.checkpointer.list(None)}
    achados = []
    for thread_id in sorted(threads):
        cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": config.RECURSION_LIMIT}
        for t in grafo.get_state(cfg).tasks:
            for i in t.interrupts:
                vencida = datetime.fromisoformat(i.value["expira_em"]) < datetime.now()
                achados.append({"thread_id": thread_id, "acao": i.value["acao"], "expira_em": i.value["expira_em"],
                                "vencida": vencida})
                if expirar and vencida:
                    usuario, sessao = thread_id.split(":", 1)
                    achados[-1]["resultado"] = executar(usuario, sessao, retomada={"acao": "expirar"},
                                                        nome_log=f"{usuario}-{sessao}-expirar")["saida"]["resultado"]
    return achados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Agente Nutricionista Pessoal")
    p.add_argument("texto", nargs="?", help="o que a pessoa digita")
    p.add_argument("--usuario", default="ana")
    p.add_argument("--sessao", default="s1")
    p.add_argument("--aprovar", action="store_true")
    p.add_argument("--rejeitar", action="store_true")
    p.add_argument("--editar", metavar="JSON")
    p.add_argument("--pendentes", action="store_true")
    p.add_argument("--expirar", action="store_true")
    p.add_argument("--log", help="nome do arquivo de log (sem extensão)")
    p.add_argument("--json", action="store_true", help="imprime só o JSON {saida, log, trace} (usado pela suíte, evals/rodar.py)")
    a = p.parse_args()

    if a.pendentes:
        # lista as pausas de TODOS os usuários: função do operador, e não de quem roda a CLI (C1)
        if not acesso.autenticar(acesso.OPERADOR, os.getenv("NUTRI_TOKEN"), papel=acesso.OPERADOR):
            sys.exit("acesso negado: --pendentes exige o NUTRI_TOKEN do operador")
        print(json.dumps(pendentes(a.expirar), ensure_ascii=False, indent=2))
        return
    retomada = ({"acao": "aprovar"} if a.aprovar else {"acao": "rejeitar"} if a.rejeitar else
                {"acao": "editar", "itens": json.loads(a.editar)} if a.editar else None)
    if retomada is None and not a.texto:
        p.error("informe o texto, ou --aprovar/--rejeitar/--editar")
    r = executar(a.usuario, a.sessao, a.texto, retomada, a.log)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return
    print(r["saida"]["resultado"])
    print("\n--- saída completa ---")
    print(json.dumps(r["saida"], ensure_ascii=False, indent=2))
    print(f"\nlog: {r['log']}\ntrace: {r['trace']} (python -m src.traces {r['trace_id'][:8]})")


if __name__ == "__main__":
    main()
