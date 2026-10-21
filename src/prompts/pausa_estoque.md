---
id: pausa_estoque
versao: 1.0.0
tecnica: modelo de texto (sem LLM) mostrado à pessoa na pausa de aprovação
---
Vou SOMAR estes itens ao seu estoque ({{usuario}}):
{{itens}}
{{pendentes}}
Consequência: as quantidades acima passam a contar nas próximas recomendações. Nada foi gravado ainda.
Responda até {{expira_em}}:
  aprovar               -> grava exatamente a lista acima
  editar <json>         -> grava a lista que você mandar, por exemplo [{"item_id":"leite_integral","quantidade":1,"unidade":"l"}]
  rejeitar              -> não grava nada
Sem resposta até o prazo, nada é gravado.
