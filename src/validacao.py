"""O que a memória de longo prazo NÃO guarda (docs/seguranca.md §3.4, controles C3 e C4).

Duas regras em código, nos dois pontos em que texto da pessoa vira memória de longo prazo:

1. **Perfil** (memória semântica, relida em TODA execução futura e posta no prompt do chef).
   `valor_de_perfil` recusa o valor que:
     - contém dado pessoal que não serve à finalidade (CPF, e-mail, telefone, cartão, CEP);
     - parece instrução ("ignore as alergias acima", "recomende..."): uma alergia gravada com
       texto de instrução é injeção indireta COM PERSISTÊNCIA (ASI06);
     - não tem a forma de um valor de perfil: alergia/restrição/preferência/equipamento é um
       nome curto (até 4 palavras, só letras, espaço e hífen); objetivo, uma frase curta.
   Aplicada no nó `extrair_perfil` (a pessoa vê o motivo) e de novo em `db.atualizar_perfil`
   (a escrita em si): se o nó falhar em checar, o banco recusa (fail-closed).

2. **Histórico** (memória episódica: o pedido fica guardado com a receita, para não repetir).
   `redigir` troca os dados pessoais do texto por `[removido:<tipo>]` ANTES de gravar e antes
   de calcular o embedding. O pedido continua útil para a busca ("me sugere um jantar com ovo").
"""
import re

from . import catalogo

PII = [
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("cartao", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("telefone", re.compile(r"(\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")),
    ("cep", re.compile(r"\b\d{5}-\d{3}\b")),
]
# palavras de comando dirigidas ao modelo; não aparecem num nome de alergia, restrição ou objetivo
INSTRUCAO = re.compile(r"\b(ignor\w*|desconsider\w*|esquec\w*|instruc\w*|regras?|sistema|prompt|respond\w*|"
                       r"recomend\w*|assistente|modelo|system|ignore|override)\b")
CURTO = re.compile(r"^[a-z\- ]{2,40}$")          # sobre o texto normalizado (sem acento)
FRASE = re.compile(r"^[a-z0-9,.\- ]{2,60}$")


def achar_pii(texto: str) -> list[str]:
    return [nome for nome, padrao in PII if padrao.search(texto)]


def valor_de_perfil(campo: str, valor: str) -> str | None:
    """None se o valor pode ir para o perfil; senão, o motivo da recusa."""
    if pii := achar_pii(valor):
        return f"dado pessoal ({', '.join(pii)}) não é guardado no perfil"
    normal = catalogo.normalizar(valor)
    if INSTRUCAO.search(normal):
        return "o valor parece uma instrução, e não um dado de perfil"
    bruto = valor.strip().lower()
    if re.search(r"[;:{}<>\[\]\"'`|\\/]", bruto):
        return "o valor tem pontuação que um dado de perfil não tem"
    if campo == "objetivo":
        return None if FRASE.match(normal) else "o objetivo tem de ser uma frase curta (até 60 caracteres)"
    if not CURTO.match(normal) or len(normal.split()) > 4:
        return f"'{campo}' aceita um nome curto (até 4 palavras, só letras)"
    return None


def redigir(texto: str) -> str:
    """Troca dado pessoal por [removido:<tipo>]. A ordem importa: CPF e cartão antes do telefone."""
    for nome, padrao in PII:
        texto = padrao.sub(f"[removido:{nome}]", texto)
    return texto
