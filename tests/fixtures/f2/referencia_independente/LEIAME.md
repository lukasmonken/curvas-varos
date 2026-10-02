# Referência independente do CORRIGIDO

`blind.py` foi escrito por um agente revisor **sem ler** `src/curvas`, `tools/` nem os
testes, só com `docs/ESPECIFICACAO.md` (E8), as decisões de `OPEN_QUESTIONS.md` e os
dados brutos desta pasta. `blind_B_ii.json` é a saída dele com:

- convenção B de t0 (Q11): t0 na curva, CDI realizado até t0 exclusive, dU = [t0, 31/12];
- regra ii do IPCA não divulgado (Q12): intervalo só no ano corrente.

`tests/test_attribution.py::test_corrigido_bate_com_referencia_independente` compara
o motor com este arquivo. Não regenerar a partir do código do projeto.
