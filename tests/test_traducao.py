from src import traducao


def test_traducao_fiel_passa():
    assert traducao.conferir_linha("1 1/2 teaspoons sugar", "1 1/2 colheres de chá de açúcar") is None
    assert traducao.conferir_linha("3/4 cup chopped fresh parsley", "3/4 xícara de salsinha fresca picada") is None
    assert traducao.conferir_linha("2 large eggs", "2 ovos grandes") is None


def test_colher_de_cha_virando_colher_de_sopa_e_barrado():
    # o erro observado no E08 #7: teaspoons lido como colheres de sopa
    assert traducao.conferir_linha("12 teaspoons sugar", "12 colheres de sopa de açúcar") == "unidade diferente do original"


def test_unidade_inventada_e_barrada():
    assert traducao.conferir_linha("2 large eggs", "2 xícaras de ovos") == "unidade diferente do original"


def test_numero_mudado_e_barrado():
    assert traducao.conferir_linha("4 ounces finely grated Parmesan", "40 onças de parmesão ralado") == "número diferente do original"
    # converter para gramas também muda o número: o prompt pede para não converter
    assert traducao.conferir_linha("1 pound potatoes", "454 g de batatas") == "número diferente do original"


def test_linha_reprovada_volta_ao_original_e_e_contada():
    r = traducao.aplicar("Potato Latkes", ["1 pound potatoes", "1 large egg"], "Latkes de batata",
                         ["1 libra de batatas", "1 xícara de ovo"])
    assert r["nome_pt"] == "Latkes de batata"
    assert r["ingredientes_pt"] == ["1 libra de batatas", "1 large egg"]
    assert r["mantidas"] == 1


def test_numero_de_linhas_diferente_mantem_tudo_em_ingles():
    r = traducao.aplicar("Crepes", ["1 cup flour", "2 eggs"], "Crepes", ["1 xícara de farinha"])
    assert r["ingredientes_pt"] == ["1 cup flour", "2 eggs"]
    assert r["mantidas"] == 2


def test_ingrediente_trocado_ou_inventado_e_barrado():
    # observado: "Roasted broccoli..." virou "Brocolírico assado"
    assert traducao.conferir_linha("1 head broccoli, roasted", "1 cabeça de brocolírico assado") is not None
    assert traducao.conferir_linha("1/2 cup finely chopped onion", "1/2 xícara de alho picado") is not None


def test_plural_e_substantivo_principal_valem():
    assert traducao.conferir_linha("1 pound potatoes", "1 libra de batatas") is None
    assert traducao.conferir_linha("1 cup all-purpose flour", "1 xícara de farinha") is None


def test_basico_trocado_e_barrado():
    # observados no teste com o 7B
    assert traducao.conferir_linha("Pinch of salt", "Pimenta-do-reino a gosto") is not None
    assert traducao.conferir_linha("3 large egg yolks, at room temperature", "3 ovos grandes claros") is not None


def test_basico_fiel_passa():
    assert traducao.conferir_linha("8 tablespoons (120 g) unsalted butter", "8 colheres de sopa (120 g) de manteiga sem sal") is None
    assert traducao.conferir_linha("Kosher salt, freshly ground pepper", "sal kosher, pimenta-do-reino moída na hora") is None
    assert traducao.conferir_linha("3 large egg yolks", "3 gemas grandes") is None


def test_stick_virando_colher_e_barrado():
    assert traducao.conferir_linha("1/2 cup (1 stick) unsalted butter", "1/2 xícara (1 colher de manteiga) de manteiga sem sal") is not None
    assert traducao.conferir_linha("1/2 cup (1 stick) unsalted butter", "1/2 xícara (1 tablete) de manteiga sem sal") is None


def test_white_pepper_nao_e_clara():
    assert traducao.conferir_linha("1/4 teaspoon white pepper", "1/4 colher de chá de pimenta-branca") is None
