"""Prepara tudo do zero: dados, índice e banco com usuários FICTÍCIOS.

    python -m scripts.preparar            # tudo
    python -m scripts.preparar --banco    # só recria o banco (zera estoque/perfil/histórico)

Os usuários são simulados (regra da disciplina: dado pessoal não entra no
repositório nem no contexto do modelo):
- ana:   perfil completo, sem alergias, estoque doméstico típico — o caminho feliz;
- bruno: alergia a amendoim, e amendoim no estoque — exercita o filtro de alérgeno;
- carla: usuária nova, sem perfil e sem estoque — exercita a entrada incompleta.
"""
import json
import sys

from scripts import baixar_dados
from src import config, db, rag

USUARIOS = {
    "ana": {"perfil": {"nome": "Ana (fictícia)", "objetivo": "manutenção do peso", "alergias": [],
                       "restricoes": [], "preferencias": ["refeições rápidas"], "equipamentos": ["fogão", "forno"]},
            "estoque": [("ovo", 6, "un"), ("manteiga", 200, "g"), ("alho", 1, "cabeça"), ("cebola", 3, "un"),
                        ("tomate", 4, "un"), ("limao", 3, "un"), ("macarrao", 500, "g"), ("queijo_parmesao", 100, "g"),
                        ("frango", 600, "g"), ("folhas", 1, "maço"), ("pao", 1, "pacote"), ("batata", 1, "kg"),
                        ("espinafre", 200, "g"), ("leite_integral", 1, "l"), ("farinha_trigo", 1, "kg"),
                        ("ervas", 1, "maço"), ("arroz", 1, "kg"), ("banana", 6, "un")]},
    "bruno": {"perfil": {"nome": "Bruno (fictício)", "objetivo": "ganho de massa muscular", "alergias": ["amendoim"],
                         "restricoes": [], "preferencias": [], "equipamentos": ["fogão"]},
              "estoque": [("banana", 6, "un"), ("pao", 1, "pacote"), ("manteiga", 200, "g"), ("amendoim", 300, "g"),
                          ("ovo", 12, "un"), ("frango", 1000, "g"), ("arroz", 2, "kg"), ("alho", 1, "cabeça"),
                          ("limao", 4, "un")]},
    "carla": {"perfil": None, "estoque": []},
}


def semear() -> None:
    config.DB_DOMINIO.unlink(missing_ok=True)
    db.iniciar()
    with db.conexao() as con:
        for usuario_id, u in USUARIOS.items():
            if u["perfil"]:
                p = u["perfil"]
                con.execute("INSERT INTO perfil VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (usuario_id, p["nome"], p["objetivo"], *(json.dumps(p[c], ensure_ascii=False)
                             for c in db.CAMPOS_LISTA), db.agora()))
            for item_id, qtd, unidade in u["estoque"]:
                con.execute("INSERT INTO estoque VALUES (?, ?, ?, ?, ?)", (usuario_id, item_id, qtd, unidade, db.agora()))
    print(f"banco: {len(USUARIOS)} usuários fictícios -> {config.DB_DOMINIO}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--banco" not in sys.argv:
        baixar_dados.baixar_receitas()
        baixar_dados.baixar_tbca()
        baixar_dados.baixar_oms()
        print("índice:", json.dumps(rag.indexar(), ensure_ascii=False))
    config.DB_CHECKPOINTS.unlink(missing_ok=True)
    semear()
