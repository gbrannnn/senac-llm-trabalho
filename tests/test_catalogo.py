"""O catálogo é código determinístico: tudo aqui tem resposta exata."""
import pytest

from src import catalogo


@pytest.mark.parametrize("texto,item,esperado", [
    ("2 Tbsp. unsalted butter", "manteiga", 2 / 16 * 227),
    ("1 stick unsalted butter, softened", "manteiga", 113),
    ("3 large eggs", "ovo", 150),
    ("1 (5-ounce) bag baby arugula", "folhas", 5 * 28.35),
    ("4 slices thick-cut smoked bacon (4 ounces), chopped", "porco", 4 * 28.35),
    ("2 St. Louis-style pork ribs (3–4 pounds each)", "porco", 2 * 3 * 453.6),
    ("3 1/2–4 cups all-purpose flour, divided", "farinha_trigo", 3.5 * 125),
    ("½ cup whole milk", "leite_integral", 0.5 * 244),
    ("1 bunch fresh basil", "ervas", 0.0),
    ("Parmesan cheese shavings", "queijo_parmesao", None),
])
def test_gramas(texto, item, esperado):
    resultado = catalogo.gramas(texto, item)
    if esperado is None:
        assert resultado is None
    else:
        assert resultado == pytest.approx(esperado, rel=0.01)


@pytest.mark.parametrize("texto,alvo", [
    ("2 Tbsp. brown sugar", "acucar_mascavo"),   # o termo mais longo vence 'sugar'
    ("1 tsp. sugar", "_basico"),
    ("1 red bell pepper", "pimentao"),           # não é a pimenta-do-reino básica
    ("¼ cup peanut butter", "amendoim"),          # não é manteiga
    ("1 cup quinoa", None),
])
def test_casar_en(texto, alvo):
    assert catalogo.casar_en(texto) == alvo


def test_leite_e_ambiguo():
    casamento = catalogo.casar_pt("leite")
    assert casamento.status == "ambiguo"
    assert casamento.candidatos == ["leite_desnatado", "leite_integral"]


@pytest.mark.parametrize("nome,item", [("ovos", "ovo"), ("Frango", "frango"), ("espinafre", "espinafre"),
                                       ("leite integral", "leite_integral"), ("maçã", "maca")])
def test_casar_pt_reconhece(nome, item):
    assert catalogo.casar_pt(nome).candidatos == [item]


def test_casar_pt_nao_reconhece():
    assert catalogo.casar_pt("quinoa").status == "nao_reconhecido"


def test_alergenos_seguem_a_rdc_26():
    assert catalogo.alergenos_de("manteiga") == {"leite"}
    assert catalogo.alergenos_de("shoyu") == {"soja", "trigo"}
    assert catalogo.alergenos_de("gergelim") == set()  # não está na lista brasileira


@pytest.mark.parametrize("texto,alvo", [
    ("2 Tbsp. almond butter", "castanhas"),   # empatava com 'butter' e escondia o alérgeno
    ("¼ cup peanut butter", "amendoim"),
    ("1 cup almond milk", "castanhas"),
])
def test_pasta_de_oleaginosa_nao_vira_manteiga(texto, alvo):
    assert catalogo.casar_en(texto) == alvo


@pytest.mark.parametrize("ingredientes,deve_ter", [
    (["8 oz. egg noodles"], {"ovo", "trigo"}),          # casa só com macarrão; o ovo vem do texto
    (["1 cup coconut milk"], {"leite"}),                # conservador: bloqueia quem tem alergia a leite
    (["2 Tbsp. peanut butter"], {"amendoim", "leite"}),
    (["1 eggplant"], set()),                            # 'egg' com fronteira de palavra
    (["1 butternut squash"], set()),
])
def test_alergeno_por_texto(ingredientes, deve_ter):
    assert catalogo.alergenos_por_texto(ingredientes) == deve_ter


@pytest.mark.parametrize("plural,singular", [("camarões", "camarao"), ("pães", "pao"), ("amendoins", "amendoim"),
                                             ("nozes", "noz"), ("ovos", "ovo"), ("frutos do mar", "fruto do mar"),
                                             ("arroz", "arroz"), ("mês", "mes")])
def test_singular(plural, singular):
    assert catalogo.singular(plural) == singular


def test_casar_pt_no_plural():
    assert catalogo.casar_pt("camarões").candidatos == ["camarao"]
    assert catalogo.casar_pt("bananas").candidatos == ["banana"]
