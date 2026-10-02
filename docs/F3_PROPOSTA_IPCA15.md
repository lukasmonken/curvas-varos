# F3: proposta de uso do IPCA-15 no intervalo do IPCA não divulgado — Q13

E8.6 permite, "como alternativa parametrizável", cobrir com o IPCA-15 o intervalo entre o último IPCA divulgado e t0. Pesquisa de 01/10/2026, conferida por um verificador. Os números abaixo usam as curvas da planilha e t0 = 04/09/2026, só para ilustrar o mecanismo. A tabela oficial da F2 usa t0 = 29/09/2026 e traz a sensibilidade da Forma A nessa data.

## Fatos

- **Metodologia:** a mesma do IPCA, com 11 áreas em vez de 16.
- **Período de coleta:** cerca de 16 do mês anterior a 15 do mês de referência (em ago/2026, de 16/07 a 14/08).
- **Divulgação:** às 9h, entre os dias 23 e 28 do próprio mês de referência.
- **Ordem de divulgação:** sempre IPCA(M−1), depois IPCA-15(M), depois IPCA(M). Em qualquer t0 há, no máximo, um IPCA-15 útil: o do mês seguinte ao último IPCA divulgado.
- **Séries:**
  - BCB SGS **7478**, com dados desde mai/2000 (a data do SGS é o mês de referência);
  - SIDRA 7062 (v355, índice geral c315/7169);
  - agenda do IBGE (API de calendário, título "Índice Nacional de Preços ao Consumidor Amplo 15").
- **Valores de 2026:** IPCA-15 de julho 0,06%, de agosto −0,40% e de setembro 0,70%. O IPCA de agosto foi −0,32%.
- **Histórico (jan/2012 a ago/2026, n = 176):** IPCA-15(M) − IPCA(M) tem viés de 0,00 pp, erro médio absoluto de 0,14 pp e máximo de 0,81 pp. Repetir o IPCA do mês anterior erra 0,27 pp em média.

## As três formas (t0 = 04/09/2026; último IPCA: julho; IPCA-15 de agosto divulgado em 26/08)

| Forma | Regra | Inflação 2026 | vs. regra atual |
|---|---|---|---|
| Atual (curva) | IPCA jan–jul × F(104 d.u. desde 03/08) | 6,1532% | — |
| **A (recomendada)** | IPCA jan–jul × (1 + IPCA-15 de ago) × F(83 d.u. desde 01/09) | 5,1767% | −97,7 bps |
| B | IPCA jan–jul × (1 + IPCA-15 ago)^(10/22) × F(94 d.u. desde 17/08) | 5,6963% | −45,7 bps |
| C | IPCA jan–jul × (1 + IPCA-15 ago)^(1/2) × F(94 d.u. desde 17/08) | 5,6770% | −47,6 bps |

Na fórmula B, 10/22 são os dias úteis da janela de coleta (16/07–14/08) que caem em agosto.

Para comparação, com o IPCA de agosto efetivo (−0,32%) no lugar do IPCA-15, a estrutura da Forma A daria 5,2611%. A regra atual atribui à curva +0,60% nos 24 dias úteis de 03/08 a 03/09 (+0,52% só em agosto), um mês que teve deflação. Esse caso favorece a Forma A por construção, porque usa a mesma estrutura; o argumento mais forte para A é o histórico de 176 meses.

## Por que a Forma A

- O resultado anual é o produto dos IPCAs de cada mês. O IPCA-15(M) é a prévia oficial do mesmo mês, com a mesma metodologia e sem viés histórico.
- Usa um único número, sem depender das datas de coleta.
- As Formas B e C deixam metade do mês para a curva, que não tem sazonalidade, e tratam o eixo da curva como dias de coleta de preços. Isso não vale: na NTN-B, o IPCA(M) entra no VNA de 15/M a 15/(M+1) (Metodologia ANBIMA).

## Implementação proposta

- Parâmetro `inflation_gap_rule ∈ {curve, ipca15_same_month}`, com **padrão `curve`**, que é a regra atual de E8.6.
- Com `ipca15_same_month`, quando o IPCA-15 do mês M = L+1 já tiver sido divulgado até t0 (inclusive) e M estiver no ano corrente, o realizado passa a ser Π IPCA(jan..L) × (1 + IPCA-15(M)). A curva cobre do 1º dia útil de M+1 a 31/12.
- O output registra qual IPCA-15 foi usado, o valor e a data de divulgação.
- A validação `dias de curva ≥ dU(Y₀)` deixa de valer nesse modo: em 28/09/2026, por exemplo, são 62 dias de curva contra dU = 65.
- Coletor: SGS 7478 mais a agenda do IBGE, que já estão no projeto.
- Em 2026, o parâmetro faria diferença em 121 dos 249 dias úteis.

## Ressalva geral (vale também sem o IPCA-15)

O eixo da curva de inflação implícita da ANBIMA (NTN-B) fica deslocado cerca de meio mês em relação aos rótulos mensais do IPCA, porque o IPCA(M) entra no VNA de 15/M a 15/(M+1). Isso afeta a regra de E8.6 em geral. Fica registrado, sem bloquear nada.
