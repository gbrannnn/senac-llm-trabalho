from src import citacao


def test_numero_que_esta_na_fonte_passa():
    fonte = '{"codigo_tbca": "BRC0012J", "por_100g": {"proteina_g": 9.04, "energia_kcal": 126.0}}'
    assert citacao.nao_sustentados("O ovo tem 9,04 g de proteína e 126 kcal por 100 g.", [fonte]) == set()


def test_numero_inventado_e_acusado():
    fonte = "WHO recommends adults consume less than 2000 mg of sodium (5 g of salt) per day."
    assert citacao.nao_sustentados("Grávidas não devem passar de 200 mg de cafeína.", [fonte]) == {"200"}


def test_milhar_com_ponto_e_o_mesmo_numero():
    fonte = "less than 2000 mg/day sodium"
    assert citacao.nao_sustentados("menos de 2.000 mg de sódio por dia", [fonte]) == set()


def test_sem_fonte_todo_numero_e_acusado():
    assert citacao.nao_sustentados("tem 30 g", []) == {"30"}


def test_trecho_citado_existe_mesmo_com_json():
    fonte = '{"trechos": [{"texto": "Documento: Sodium\n\nWHO recommends a reduction to  <2 g/day sodium"}]}'
    assert citacao.trecho_existe("WHO recommends a reduction to <2 g/day sodium", [fonte])


def test_trecho_inventado_nao_existe():
    fonte = "WHO recommends a reduction to <2 g/day sodium"
    assert not citacao.trecho_existe("caffeine intake should be limited during pregnancy", [fonte])


def test_citacao_em_fragmentos_literais_passa():
    fonte = "TBCA BRC0012J - Ovo, galinha, branco, inteiro, cru, Brasil - por 100 g: energia 126 kcal; proteína 9.04 g; lipídio 8.74 g"
    citada = "TBCA BRC0012J - Ovo, galinha, branco, inteiro, cru, Brasil - por 100 g: proteína 9.04 g;"
    assert citacao.trecho_existe(citada, [fonte])


def test_fragmento_alterado_reprova():
    fonte = "por 100 g: energia 126 kcal; proteína 9.04 g"
    assert not citacao.trecho_existe("por 100 g: proteína 19.04 g", [fonte])
