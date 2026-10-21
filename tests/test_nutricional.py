"""Cálculo nutricional: determinístico, e honesto sobre o que fica de fora."""
import pytest

from src import nutricional


def receita(*ingredientes):
    return {"id": "T1", "nome": "teste", "ingredientes": [
        {"texto": t, "item": item, "gramas": g, "opcional": False} for t, item, g in ingredientes]}


def test_ovo_bate_com_a_tbca():
    n = nutricional.calcular(receita(("2 eggs", "ovo", 100.0)))
    por_100g = nutricional.por_100g("BRC0012J")["por_100g"]
    assert n.energia_kcal == pytest.approx(por_100g["energia_kcal"], abs=0.1)
    assert n.completa


def test_quantidade_desconhecida_fica_fora_e_marca_incompleta():
    n = nutricional.calcular(receita(("2 eggs", "ovo", 100.0), ("Parmesan shavings", "queijo_parmesao", None)))
    assert not n.completa
    assert n.fora_do_calculo == ["Parmesan shavings"]


def test_item_sem_tbca_fica_fora():
    n = nutricional.calcular(receita(("½ cup sour cream", "creme_azedo", 115.0)))
    assert not n.completa and n.energia_kcal == 0


def test_sal_de_salmoura_nao_entra_no_sodio():
    n = nutricional.calcular(receita(("2 eggs", "ovo", 100.0), ("1 cup kosher salt", "_basico", None)))
    assert n.sodio_mg < 1000
    assert "salmoura" in n.fora_do_calculo[0]


def test_sal_de_tempero_entra():
    n = nutricional.calcular(receita(("1 tsp. salt", "_basico", None)))
    assert n.sodio_mg > 1500  # ~6 g de sal = ~2300 mg de sódio
    assert n.completa


def test_oleo_de_fritura_nao_entra():
    n = nutricional.calcular(receita(("Vegetable oil (for frying)", "_basico", None), ("1 1/2 cups grapeseed oil", "_basico", None)))
    assert n.energia_kcal == 0
    assert len(n.fora_do_calculo) == 2
