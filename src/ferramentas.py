"""Ferramentas que os agentes (chef e consultor) podem chamar.

Todas são de LEITURA. As escritas (estoque, perfil, histórico) não são
ferramentas: são nós de código do grafo, depois de validação ou de aprovação
humana. O modelo não tem como escrever no banco (docs/arquitetura.md §3.2).

O contexto (`Ctx`) é montado pelo código a partir da sessão: o modelo não
escolhe de quem são os dados.

Erro de ferramenta (receita inexistente, alimento fora da TBCA) volta para o
modelo como resultado, com a dica do que fazer: é erro RECUPERÁVEL.
"""
import json
from dataclasses import dataclass, field

from . import catalogo, config, nutricional, rag


@dataclass
class Ctx:
    usuario_id: str
    disponiveis: set[str]           # itens do estoque + os que a pessoa declarou ter neste pedido
    alergenos_bloqueados: set[str]
    recentes: set[str]
    rejeitadas: set[str] = field(default_factory=set)       # reprovadas neste turno: saem das buscas
    recuperacoes: list[dict] = field(default_factory=list)  # registro de cada busca, para o log
    descartes_oms: list[dict] = field(default_factory=list)
    fontes: list[dict] = field(default_factory=list)


def _f(nome: str, descricao: str, props: dict, obrigatorios: list[str]) -> dict:
    return {"type": "function", "function": {"name": nome, "description": descricao, "parameters": {
        "type": "object", "properties": props, "required": obrigatorios}}}


_TXT = {"type": "string"}

FERRAMENTAS_CHEF = [
    _f("buscar_receitas", "Busca receitas no acervo (em inglês) por similaridade. Devolve até 5, com o que falta no estoque.",
       {"consulta": {**_TXT, "description": "consulta em inglês, ex.: 'chicken lemon garlic'"}}, ["consulta"]),
    _f("detalhar_receita", "Ingredientes e modo de preparo de uma receita pelo id.", {"receita_id": _TXT}, ["receita_id"]),
    _f("propor_receita", "Propõe a receita escolhida. Encerra a busca.",
       {"receita_id": _TXT, "justificativa": {**_TXT, "description": "português, 1-2 frases, motivo verificável"}},
       ["receita_id", "justificativa"]),
    _f("declarar_sem_opcao", "Declara que nenhuma receita do acervo serve.", {"motivo": _TXT}, ["motivo"]),
]

FERRAMENTAS_CONSULTOR = [
    _f("buscar_diretrizes", "Busca trechos das fichas da OMS sobre alimentação (em inglês).", {"consulta": _TXT}, ["consulta"]),
    _f("consultar_alimento", "Composição por 100 g de um alimento na TBCA.",
       {"nome": {**_TXT, "description": "nome em português, ex.: 'ovo'"}}, ["nome"]),
    _f("responder", "Entrega a resposta final.",
       {"resposta": _TXT, "suficiente": {"type": "boolean"}, "fontes": {"type": "array", "items": _TXT}},
       ["resposta", "suficiente", "fontes"]),
]

TERMINAIS = {"propor_receita", "declarar_sem_opcao", "responder"}


def resumo_receita(r: dict, ctx: Ctx) -> dict:
    faltando = sorted(set(r["itens"]) - ctx.disponiveis)
    conflito = sorted(set(r["alergenos"]) & ctx.alergenos_bloqueados)
    return {"receita_id": r["id"], "nome": r["nome"], "itens": r["itens"], "faltando": faltando,
            "conflito_alergia": conflito, "recomendada_recentemente": r["id"] in ctx.recentes,
            "viavel": not faltando and not conflito}


def expandir_consulta(consulta: str) -> str:
    """Ponte de vocabulário: palavra em português que o catálogo conhece ganha os termos
    em inglês do acervo ('abobrinha' -> 'zucchini summer squash'). Determinístico."""
    extras = []
    palavras = catalogo.normalizar(consulta).split()
    for n in (2, 1):
        for i in range(len(palavras) - n + 1):
            casamento = catalogo.casar_pt(" ".join(palavras[i:i + n]))
            if casamento.status == "reconhecido":
                termos = catalogo.itens()[casamento.candidatos[0]]["en"][:2]
                extras += [t.replace("s?", "").replace("?", "") for t in termos]
    return consulta if not extras else f"{consulta} ({' '.join(dict.fromkeys(extras))})"


def buscar_receitas(ctx: Ctx, consulta: str) -> dict:
    """Devolve SÓ receitas viáveis: o modelo não escolhe o que não vê.

    A conferência em código (grafo.conferir_proposta) continua existindo como
    segunda linha, para o caso de o modelo inventar um id."""
    expandida = expandir_consulta(consulta)
    resultados = rag.buscar_receitas(expandida, k=config.K_RECEITAS * 3)
    resumos = [resumo_receita(r, ctx) for r, _ in resultados if r["id"] not in ctx.rejeitadas]
    viaveis = [x for x in resumos if x["viavel"]][:config.K_RECEITAS]
    motivos = {"falta ingrediente": sum(bool(x["faltando"]) for x in resumos),
               "alérgeno do perfil": sum(bool(x["conflito_alergia"]) for x in resumos)}
    ctx.recuperacoes.append({"indice": "receitas", "consulta": consulta, "consulta_expandida": expandida,
                             "ids": [x["receita_id"] for x in viaveis], "candidatas": len(resumos),
                             "descartadas_por_codigo": motivos})
    return {"receitas": viaveis, "viaveis": len(viaveis), "descartadas_por_codigo": motivos}


def detalhar_receita(ctx: Ctx, receita_id: str) -> dict:
    r = rag.receitas_por_id().get(receita_id)
    if r is None:
        return {"erro": f"receita '{receita_id}' não existe no acervo. Use um id devolvido por buscar_receitas."}
    return {**resumo_receita(r, ctx), "ingredientes": [i["texto"] for i in r["ingredientes"]],
            "modo_preparo": r["modo_preparo"][:800]}


def buscar_diretrizes(ctx: Ctx, consulta: str) -> dict:
    resultado = rag.buscar_oms(consulta)
    ctx.recuperacoes.append({"indice": "oms", "consulta": consulta, "ids": [t["id"] for t, _ in resultado.trechos],
                             "descartados": resultado.descartados})
    ctx.descartes_oms += resultado.descartados
    return {"trechos": [{"id": t["id"], "documento": t["documento"], "data_publicacao": t["data_publicacao"],
                         "texto": t["texto"][:1200]} for t, _ in resultado.trechos]}


def consultar_alimento(ctx: Ctx, nome: str) -> dict:
    casamento = catalogo.casar_pt(nome)
    com_dado = [c for c in casamento.candidatos if catalogo.itens()[c]["tbca"]]
    ctx.recuperacoes.append({"indice": "tbca", "consulta": nome, "ids": [catalogo.itens()[c]["tbca"] for c in com_dado]})
    if not com_dado:
        return {"erro": f"'{nome}' não está no recorte da TBCA usado por este sistema.",
                "alimentos_disponiveis_exemplo": sorted(i["nome"] for i in catalogo.itens().values() if i["tbca"])[:20]}
    saida = []
    rotulos = {"energia_kcal": ("energia", "kcal"), "proteina_g": ("proteína", "g"), "carboidrato_g": ("carboidrato", "g"),
               "lipidio_g": ("lipídio", "g"), "fibra_g": ("fibra", "g"), "sodio_mg": ("sódio", "mg")}
    for c in com_dado:
        t = nutricional.por_100g(catalogo.itens()[c]["tbca"])
        # texto corrido, e não JSON: o verificador precisa COPIAR um trecho, e copiar JSON é frágil
        valores = "; ".join(f"{rotulos[k][0]} {v:g} {rotulos[k][1]}" for k, v in t["por_100g"].items() if v is not None)
        saida.append(f"TBCA {t['codigo']} - {t['nome']} - por 100 g: {valores}")
    return {"resultados": saida}


EXECUTORES = {"buscar_receitas": buscar_receitas, "detalhar_receita": detalhar_receita,
              "buscar_diretrizes": buscar_diretrizes, "consultar_alimento": consultar_alimento}


def executar(ctx: Ctx, nome: str, args: dict) -> str:
    executor = EXECUTORES.get(nome)
    if executor is None:
        return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}, ensure_ascii=False)
    try:
        return json.dumps(executor(ctx, **args), ensure_ascii=False)
    except TypeError as erro:  # argumento errado vindo do modelo: recuperável
        return json.dumps({"erro": f"argumentos inválidos para {nome}: {erro}"}, ensure_ascii=False)
