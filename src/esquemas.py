"""Contratos: a saída do sistema (§1.2) e a saída de cada etapa que chama o modelo.

O schema garante que a resposta do modelo tenha a forma certa. Ele NÃO garante
que a rota escolhida seja a certa — isso é medido em docs/prompts.md.
"""
from typing import Literal

from pydantic import BaseModel, Field

# --- saídas do modelo, etapa a etapa -------------------------------------------

Rota = Literal["recomendar", "estoque", "perfil", "pergunta", "fora_escopo"]


class Triagem(BaseModel):
    rota: Rota
    acao_futura: bool = Field(description="true se a pessoa fala do que AINDA vai fazer (vou comprar, amanhã)")
    ingredientes_citados: list[str] = Field(default_factory=list,
                                            description="ingredientes que a pessoa diz ter ou querer usar, em português")
    pessoas: int | None = None
    tempo_max_min: int | None = None
    justificativa: str


class ItemDito(BaseModel):
    nome: str
    quantidade: float | None = None
    unidade: str | None = None


class ItensExtraidos(BaseModel):
    itens: list[ItemDito]


class AtualizacaoPerfil(BaseModel):
    campo: Literal["objetivo", "alergias", "restricoes", "preferencias", "equipamentos"]
    operacao: Literal["definir", "adicionar", "remover"]
    valor: str


class FechamentoChef(BaseModel):
    """Usado quando o chef responde em texto em vez de chamar a ferramenta final."""
    receita_id: str | None = Field(description="id de uma receita com viavel=true, ou null se nenhuma serve")
    justificativa: str = Field(description="português, 1-2 frases; se receita_id for null, o motivo")


class FechamentoConsultor(BaseModel):
    resposta: str
    suficiente: bool
    fontes: list[str] = Field(default_factory=list)


class Suporte(BaseModel):
    sustentada: bool
    trecho_citado: str = Field(description="5 a 30 palavras copiadas literalmente de uma fonte")
    assunto_sem_fonte: str = ""


class Veredito(BaseModel):
    aprovado: bool
    motivo: str = Field(description="uma frase; se reprovado, o que o chef deve mudar")


# --- a saída do sistema ----------------------------------------------------------

TipoFonte = Literal["receita", "tbca", "oms", "perfil", "estoque", "historico", "usuario", "regra"]


class Fonte(BaseModel):
    tipo: TipoFonte
    id: str
    detalhe: str = ""


class Nutricao(BaseModel):
    energia_kcal: float
    proteina_g: float
    carboidrato_g: float
    lipidio_g: float
    sodio_mg: float
    completa: bool = Field(description="false se algum ingrediente ficou fora do cálculo")
    fora_do_calculo: list[str] = Field(default_factory=list)
    base: str = "receita inteira (o dataset não informa porções)"


class ReceitaSaida(BaseModel):
    id: str
    nome: str
    ingredientes: list[str]
    faltando_no_estoque: list[str] = Field(default_factory=list)
    nutricao: Nutricao | None = None


Termino = Literal[
    "concluido", "pergunta_ao_usuario", "recusa_fora_escopo", "recusa_sem_base", "sem_acao",
    "aguardando_humano", "rejeitado_pelo_humano", "aprovacao_expirada",
    "teto_passos", "teto_rodadas", "teto_tokens", "teto_tempo", "laco_detectado", "erro_fatal"]


class Saida(BaseModel):
    execucao_id: str
    thread_id: str
    tipo: Literal["recomendacao", "estoque", "perfil", "resposta", "pergunta", "recusa", "aguardando_aprovacao", "erro"]
    resultado: str = Field(description="o texto que a pessoa lê")
    receita: ReceitaSaida | None = None
    fontes: list[Fonte] = Field(default_factory=list)
    suficiencia: Literal["suficiente", "parcial", "insuficiente", "incompleta", "fora_de_escopo"]
    motivo_suficiencia: str | None = None
    escolhas_declaradas: list[str] = Field(default_factory=list)
    pendencia: dict | None = None
    termino: Termino
