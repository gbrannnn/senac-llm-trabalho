"""Ação proibida aplicada em código: prescrever, dosar, diagnosticar (docs/seguranca.md §3.2, controle C6).

Até a v1.0.0 essa proibição estava só no prompt de sistema e nos exemplos da triagem: o
modelo decidia se "quantos mg de vitamina D eu devo tomar?" era pergunta de nutrição (e ia ao
consultor) ou fora do escopo. Prompt não é controle (o texto da pessoa chega pelo mesmo canal).

Agora o nó `triagem` confere a entrada ANTES de chamar o modelo: se casar um padrão abaixo, a
rota é `fora_escopo` e o modelo nem é chamado. O modelo continua podendo recusar mais coisa;
ele não pode mais aceitar o que estes padrões recusam.

Custo, declarado em docs/seguranca.md: falso positivo em pergunta legítima com essas palavras
("quantos mg de sódio tem o ovo?" passa; "posso tomar suco de laranja com remédio?" é recusada),
e falso negativo em paráfrase que nenhum padrão pega — essa continua dependendo do modelo.
"""
import re

from . import catalogo

UNIDADE_DOSE = r"(mg|mcg|ug|ui|gramas?|g|capsulas?|comprimidos?|gotas|doses?|scoops?|sache?s?)"
PADROES = [
    ("suplemento", re.compile(r"\b(suplement\w*|whey|creatina|capsulas?|comprimidos?|multivitamin\w*|polivitamin\w*|"
                              r"pre[- ]?treino|bcaa|termogenic\w*)\b")),
    ("medicamento", re.compile(r"\b(remedios?|medicament\w*|farmac\w*|antibiotic\w*|insulina|anticoncepcion\w*)\b")),
    ("diagnóstico", re.compile(r"\b(diagnostic\w*|diagnose)\b")),
    ("prescrição", re.compile(r"\b(prescrev\w*|prescric\w*|posologia|dosagem|dose)\b")),
    ("dose", re.compile(rf"\b(tomar|tomo|tome|ingerir)\b.{{0,40}}\b{UNIDADE_DOSE}\b|"
                        rf"\b{UNIDADE_DOSE}\b.{{0,40}}\b(tomar|tomo|tome|ingerir)\b")),
]


def proibido(texto: str) -> str | None:
    """O tipo de pedido proibido, ou None. Sobre o texto normalizado (minúsculas, sem acento)."""
    normal = catalogo.normalizar(texto)
    for nome, padrao in PADROES:
        if padrao.search(normal):
            return nome
    return None
