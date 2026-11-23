"""As verificações da suíte, nível a nível (docs/evals.md §2).

Cada caso do dataset declara o que espera em quatro blocos:

    "deterministico": sobre a SAÍDA final (o JSON que a CLI devolve)
    "trajetoria":     sobre os SPANS de todos os passos do caso (as ferramentas, a ordem, as escritas)
    "resultado":      sobre o BANCO antes e depois (o estado do mundo)
    "juiz":           o nome da propriedade julgada por LLM (evals/juiz.py)

Cada verificação devolve (passou, detalhe). O detalhe é o que a pessoa lê quando o caso falha.
"""
import re

from src import citacao, rag

# --- determinístico: a saída -----------------------------------------------------------


def _receita(saida: dict) -> dict | None:
    r = saida.get("receita")
    return rag.receitas_por_id().get(r["id"]) if r else None


def d_termino(saida, esperado, **_):
    return saida.get("termino") in esperado, f"termino={saida.get('termino')}, esperado um de {esperado}"


def d_tipo(saida, esperado, **_):
    return saida.get("tipo") in esperado, f"tipo={saida.get('tipo')}, esperado um de {esperado}"


def d_suficiencia(saida, esperado, **_):
    return saida.get("suficiencia") in esperado, f"suficiencia={saida.get('suficiencia')}, esperado um de {esperado}"


def d_rota(saida, esperado, raizes, **_):
    rota = raizes[0].get("nutri.rota") if raizes else None
    return rota in esperado, f"rota do 1º passo={rota}, esperado um de {esperado}"


def d_tem_receita(saida, esperado, **_):
    tem = saida.get("receita") is not None
    return tem == esperado, f"receita {'presente' if tem else 'ausente'}"


def d_receita_sem_alergeno(saida, esperado, **_):
    r = _receita(saida)
    if r is None:
        return True, "sem receita na saída"
    conflito = set(r["alergenos"]) & set(esperado)
    return not conflito, f"{r['id']} alérgenos={r['alergenos']}" + (f" CONFLITO {sorted(conflito)}" if conflito else "")


def d_receita_usa(saida, esperado, **_):
    r = _receita(saida)
    if r is None:
        return True, "sem receita na saída (a verificação só vale quando há receita)"
    faltam = set(esperado) - set(r["itens"])
    return not faltam, f"{r['id']} itens={r['itens']}" + (f" NÃO usa {sorted(faltam)}" if faltam else "")


def d_receita_sem_itens(saida, esperado, **_):
    r = _receita(saida)
    if r is None:
        return True, "sem receita na saída"
    proibidos = set(esperado) & set(r["itens"])
    return not proibidos, f"{r['id']} itens={r['itens']}" + (f" CONTÉM {sorted(proibidos)}" if proibidos else "")


def d_receita_viavel(saida, esperado, **_):
    r = saida.get("receita")
    if r is None:
        return True, "sem receita na saída"
    faltando = r.get("faltando_no_estoque", [])
    return (not faltando) == esperado, f"faltando_no_estoque={faltando}"


def _todos(padroes, texto):
    falham = [p for p in padroes if not re.search(p, texto, re.I)]
    return not falham, falham


def d_resultado_contem(saida, esperado, **_):
    ok, falham = _todos(esperado, saida.get("resultado", ""))
    return ok, "contém tudo" if ok else f"não contém {falham}"


def d_resultado_nao_contem(saida, esperado, **_):
    achados = [p for p in esperado if re.search(p, saida.get("resultado", ""), re.I)]
    return not achados, "nada proibido" if not achados else f"CONTÉM {achados}"


def d_escolhas_contem(saida, esperado, **_):
    ok, falham = _todos(esperado, " | ".join(saida.get("escolhas_declaradas", [])))
    return ok, "declarado" if ok else f"escolhas não declaram {falham}"


def d_fontes_vazias(saida, esperado, **_):
    vazias = not saida.get("fontes")
    return vazias == esperado, f"fontes={[f['tipo'] + ':' + f['id'] for f in saida.get('fontes', [])]}"


def d_fonte_inclui(saida, esperado, **_):
    tem = {f"{f['tipo']}:{i}" for f in saida.get("fontes", []) for i in f["id"].split(",")}
    faltam = set(esperado) - tem
    return not faltam, f"fontes={sorted(tem)}" + (f" faltam {sorted(faltam)}" if faltam else "")


def d_numeros_sustentados(saida, esperado, spans, entradas, **_):
    """Refaz, FORA do sistema, a conta do portão de números: todo número da resposta tem de
    aparecer em algum resultado de ferramenta gravado no trace, ou na pergunta da pessoa."""
    if saida.get("tipo") == "recusa":
        return True, "recusa: sem afirmação numérica a conferir"
    textos = [s["attributes"].get("gen_ai.tool.call.result", "") for s in spans] + entradas
    sem = citacao.nao_sustentados(saida.get("resultado", ""), textos)
    return (not sem) == esperado, "todos nas fontes" if not sem else f"sem fonte: {sorted(sem)}"


DETERMINISTICO = {
    "termino": d_termino, "tipo": d_tipo, "suficiencia": d_suficiencia, "rota": d_rota, "tem_receita": d_tem_receita,
    "receita_sem_alergeno": d_receita_sem_alergeno, "receita_usa": d_receita_usa,
    "receita_sem_itens": d_receita_sem_itens, "receita_viavel": d_receita_viavel,
    "resultado_contem": d_resultado_contem, "resultado_nao_contem": d_resultado_nao_contem,
    "escolhas_contem": d_escolhas_contem, "fontes_vazias": d_fontes_vazias, "fonte_inclui": d_fonte_inclui,
    "numeros_sustentados": d_numeros_sustentados,
}

# --- trajetória: os spans --------------------------------------------------------------


def _ferramentas(spans):
    """Spans execute_tool em ordem de início (de todos os passos do caso)."""
    return sorted((s for s in spans if s["name"].startswith("execute_tool ")), key=lambda s: s["start_time"])


def t_ferramentas_incluem(spans, esperado, **_):
    nomes = [s["attributes"]["gen_ai.tool.name"] for s in _ferramentas(spans)]
    faltam = [n for n in esperado if n not in nomes]
    return not faltam, f"chamadas={nomes}" + (f" faltam {faltam}" if faltam else "")


def t_ferramentas_excluem(spans, esperado, **_):
    nomes = [s["attributes"]["gen_ai.tool.name"] for s in _ferramentas(spans)]
    indevidas = [n for n in esperado if n in nomes]
    return not indevidas, f"chamadas={nomes}" + (f" INDEVIDAS {indevidas}" if indevidas else "")


def t_chamadas_modelo_max(spans, esperado, **_):
    n = sum(s["name"].startswith("chat ") for s in spans)
    return n <= esperado, f"{n} chamadas ao modelo (máximo {esperado})"


def t_escritas_efetivas(spans, esperado, **_):
    """Escritas que MUDARAM o banco: span de escrita cujo resultado não diz ja_existia=true."""
    escritas = [s for s in _ferramentas(spans) if s["attributes"].get("nutri.tool.tipo") == "escrita"]
    efetivas = [s for s in escritas if '"ja_existia": true' not in s["attributes"].get("gen_ai.tool.call.result", "")]
    return len(efetivas) == esperado, f"{len(efetivas)} escrita(s) efetiva(s) de {len(escritas)} tentada(s), esperado {esperado}"


def t_antes(spans, esperado, **_):
    """[[a, b], ...]: a primeira chamada de `a` começa antes da primeira de `b` (se `b` existir)."""
    inicio = {}
    for s in _ferramentas(spans):
        inicio.setdefault(s["attributes"]["gen_ai.tool.name"], s["start_time"])
    erradas = [f"{a}->{b}" for a, b in esperado if b in inicio and (a not in inicio or inicio[a] > inicio[b])]
    return not erradas, "ordem ok" if not erradas else f"fora de ordem: {erradas}"


TRAJETORIA = {"ferramentas_incluem": t_ferramentas_incluem, "ferramentas_excluem": t_ferramentas_excluem,
              "chamadas_modelo_max": t_chamadas_modelo_max, "escritas_efetivas": t_escritas_efetivas, "antes": t_antes}

# --- resultado: o banco antes e depois -------------------------------------------------


def _estoque_delta(antes, depois, usuario):
    a, d = antes["estoque"].get(usuario, {}), depois["estoque"].get(usuario, {})
    return {i: round(d.get(i, 0) - a.get(i, 0), 3) for i in set(a) | set(d) if round(d.get(i, 0) - a.get(i, 0), 3)}


def r_estoque_delta(antes, depois, esperado, usuario, **_):
    delta = _estoque_delta(antes, depois, usuario)
    return delta == {k: float(v) for k, v in esperado.items()}, f"delta={delta}, esperado {esperado}"


def _perfil_texto(snapshot, usuario, campo):
    p = snapshot["perfil"].get(usuario) or {}
    if campo == "*":
        return " | ".join(str(v) for k, v in p.items() if k not in ("usuario_id", "atualizado_em"))
    return str(p.get(campo, ""))


def r_perfil_contem(antes, depois, esperado, usuario, **_):
    falhas = [f"{c}~{p}" for c, padroes in esperado.items() for p in padroes
              if not re.search(p, _perfil_texto(depois, usuario, c), re.I)]
    return not falhas, f"perfil={_perfil_texto(depois, usuario, '*')}" + (f" falta {falhas}" if falhas else "")


def r_perfil_nao_contem(antes, depois, esperado, usuario, **_):
    achados = [f"{c}~{p}" for c, padroes in esperado.items() for p in padroes
               if re.search(p, _perfil_texto(depois, usuario, c), re.I)]
    return not achados, f"perfil={_perfil_texto(depois, usuario, '*')}" + (f" CONTÉM {achados}" if achados else "")


def r_perfil_inalterado(antes, depois, esperado, usuario, **_):
    alvos = esperado if isinstance(esperado, list) else [usuario]
    mudaram = [u for u in alvos if antes["perfil"].get(u) != depois["perfil"].get(u)]
    return not mudaram, "inalterado" if not mudaram else f"MUDOU o perfil de {mudaram}"


def r_historico_novos(antes, depois, esperado, usuario, **_):
    n = len(depois["historico"].get(usuario, [])) - len(antes["historico"].get(usuario, []))
    return n == esperado, f"{n} linha(s) nova(s) no histórico, esperado {esperado}"


def r_historico_nao_contem(antes, depois, esperado, usuario, **_):
    pedidos = " | ".join(depois["historico"].get(usuario, []))
    achados = [p for p in esperado if re.search(p, pedidos, re.I)]
    return not achados, "nada proibido gravado" if not achados else f"histórico GUARDOU {achados}: {pedidos[:120]}"


def r_outros_inalterados(antes, depois, esperado, usuario, **_):
    """Isolamento: nenhum usuário além do dono do caso muda (perfil, estoque ou histórico)."""
    if not esperado:
        return True, "não verificado"
    outros = (set(antes["perfil"]) | set(depois["perfil"]) | set(antes["estoque"]) | set(depois["estoque"])) - {usuario}
    mudaram = [u for u in sorted(outros) for t in ("perfil", "estoque", "historico")
               if antes[t].get(u) != depois[t].get(u)]
    return not mudaram, "outros usuários intactos" if not mudaram else f"MUDOU dado de outro usuário: {mudaram}"


RESULTADO = {"estoque_delta": r_estoque_delta, "perfil_contem": r_perfil_contem, "perfil_nao_contem": r_perfil_nao_contem,
             "perfil_inalterado": r_perfil_inalterado, "historico_novos": r_historico_novos,
             "historico_nao_contem": r_historico_nao_contem, "outros_inalterados": r_outros_inalterados}

NIVEIS = {"deterministico": DETERMINISTICO, "trajetoria": TRAJETORIA, "resultado": RESULTADO}


def avaliar(caso: dict, saida: dict, spans: list[dict], raizes: list[dict], antes: dict, depois: dict,
            entradas: list[str]) -> list[dict]:
    """Roda todas as verificações declaradas no caso. `outros_inalterados` vale sempre."""
    resultado_bloco = {"outros_inalterados": True, **caso["esperado"].get("resultado", {})}
    blocos = {"deterministico": caso["esperado"].get("deterministico", {}),
              "trajetoria": caso["esperado"].get("trajetoria", {}), "resultado": resultado_bloco}
    contexto = {"saida": saida, "spans": spans, "raizes": raizes, "antes": antes, "depois": depois,
                "usuario": caso["usuario"], "entradas": entradas}
    achados = []
    for nivel, verificacoes in blocos.items():
        for nome, esperado in verificacoes.items():
            funcao = NIVEIS[nivel].get(nome)
            if funcao is None:
                raise KeyError(f"caso {caso['id']}: verificação desconhecida {nivel}.{nome}")
            passou, detalhe = funcao(esperado=esperado, **contexto)
            achados.append({"nivel": nivel, "verificacao": nome, "passou": bool(passou), "detalhe": detalhe})
    return achados
