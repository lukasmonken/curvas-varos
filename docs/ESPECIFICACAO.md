# ESPECIFICAÇÃO: Plataforma de Curvas VAROS

> Escrita a partir dos valores calculados da planilha, sem acesso às fórmulas. As fórmulas descritas foram deduzidas e conferidas numericamente. Os casos de teste estão em E10. Confirme tudo na F0.

## E1. Propósito

A planilha é um **motor de premissas macroeconômicas** para modelos de valuation. Ela usa três curvas:

| Curva | Uso provável |
|---|---|
| DI futuro | Taxa livre de risco nominal e custo de dívida |
| Inflação implícita | Correção das projeções nominais |
| CDS Brasil (USD) | Prêmio de risco-país |

A essas curvas a planilha soma o realizado do ano (IPCA e Selic mensais). O resultado é uma taxa por ano civil de 2026 a 2036, mostrada na aba Dashboard. A data de atualização da versão analisada é 06/09/2026 (serial 46271).

## E2. Arquitetura

| Aba | Papel |
|---|---|
| Dashboard | Inputs (células em verde) e projeções anuais |
| Inflação | Curva de inflação implícita → inflação por ano |
| DI | Curva de DI → DI por ano |
| CDS | Vértices de CDS → spread por ano |

As três abas de cálculo são **independentes entre si**. Cada uma lê do Dashboard e devolve o resultado ao Dashboard, sempre no mesmo fluxo:

```
vértices → interpolação diária → acumulação dia a dia (+ realizado) → forward por ano → Dashboard
```

## E3. Dashboard

### E3.1 Parâmetros de controle

| Parâmetro | Valor |
|---|---|
| Trimestre Atual | 3º Tri |
| Mês do último IPCA | Agosto |
| Mês do último DI | Setembro |

Esses parâmetros **não controlam** as abas Inflação e DI, que têm campos próprios de mês e trimestre (ver E6.2).

### E3.2 Inputs

**Curva de inflação implícita.** Taxas anuais (%) por vértice, em dias úteis. Vai de 126 a 2646 dias, em passos de 126. Os vértices de 126 e 252 dias valem ambos 6,4827%.

| Dias úteis | 126 | 252 | 378 | 504 | 630 | 756 | 882 | 1008 | 1134 | 1260 |
|---|---|---|---|---|---|---|---|---|---|---|
| Taxa | 6,4827 | 6,4827 | 6,0499 | 5,9218 | 5,9117 | 5,9424 | 5,9828 | 6,0215 | 6,0549 | 6,0830 |

| Dias úteis | 1386 | 1512 | 1638 | 1764 | 1890 | 2016 | 2142 | 2268 | 2394 | 2520 / 2646 |
|---|---|---|---|---|---|---|---|---|---|---|
| Taxa | 6,1061 | 6,1254 | 6,1416 | 6,1555 | 6,1676 | 6,1784 | 6,1881 | 6,1971 | 6,2054 | 6,2131 |

**Curva de DI implícito.** Vai de 126 a 2394 dias úteis.

| Dias úteis | 126 | 252 | 378 | 504 | 630 | 756 | 882 | 1008 | 1134 | 1260 |
|---|---|---|---|---|---|---|---|---|---|---|
| Taxa | 13,3269 | 13,4448 | 13,7592 | 13,8898 | 13,9937 | 14,0727 | 14,1305 | 14,1708 | 14,1972 | 14,2124 |

| Dias úteis | 1386 | 1512 | 1638 | 1764 | 1890 | 2016 | 2142 | 2268 | 2394 |
|---|---|---|---|---|---|---|---|---|---|
| Taxa | 14,2189 | 14,2186 | 14,2131 | 14,2035 | 14,1910 | 14,1763 | 14,1600 | 14,1427 | 14,1248 |

**CDS Brasil (USD), em bps.** Valores copiados manualmente do Investing.com.

| Prazo | 6M | 1A | 2A | 3A | 4A | 5A | 7A | 10A | 20A |
|---|---|---|---|---|---|---|---|---|---|
| Dias úteis | 126 | 252 | 504 | 756 | 1008 | 1260 | 1764 | 2520 | 5040 |
| bps | 45,67 | 54,35 | 67,89 | 87,28 | 109,84 | 130,71 | 171,71 | 213,22 | 245,59 |

**Realizado mensal.** São 12 valores rotulados só pelo mês, sem o ano. Como o último IPCA informado é agosto, os meses de setembro a dezembro provavelmente são do ano anterior.

| Mês | Jan | Fev | Mar | Abr | Mai | Jun | Jul | Ago | Set | Out | Nov | Dez |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IPCA (%) | 0,33 | 0,70 | 0,88 | 0,43 | 0,58 | 0,16 | 0,07 | −0,32 | 0,48 | 0,09 | 0,18 | 0,33 |
| Selic (%) | 1,16 | 1,00 | 1,21 | 1,09 | 1,07 | 1,12 | 1,22 | 1,09 | 1,09 | 1,28 | 1,05 | 1,22 |

**Tabela ETTJ (ANBIMA).** Traz IPCA, Pré e Inflação Implícita, de 126 a 2520 dias. É coerente pela equação de Fisher; por exemplo, em 126 dias: 1,136275/1,084378 − 1 = 4,79%.

Essa tabela **não alimenta nenhum cálculo**. Os valores de inflação implícita que ela mostra são:

| Dias úteis | 126 | 252 | 378 | 504 | 630 | 756 |
|---|---|---|---|---|---|---|
| Inflação implícita | 4,7858 | 5,2187 | 5,3029 | 5,3677 | 5,4334 | 5,5008 |

### E3.3 Saídas atuais (modo legado)

| Ano | DI | Inflação | CDS |
|---|---|---|---|
| 2026 | 13,47% | 6,28% | 0,46% |
| 2027 | 13,68% | 6,17% | 0,50% |
| 2028 | 13,97% | 5,92% | 0,65% |
| 2029 | 14,12% | 5,98% | 0,82% |
| 2030 | 14,19% | 6,05% | 1,04% |
| 2031 | 14,22% | 6,10% | 1,25% |
| 2032 | 14,21% | 6,14% | 1,46% |
| 2033 | 14,19% | 6,17% | 1,66% |
| 2034 | 14,16% | 6,19% | 1,82% |
| 2035 | 14,13% | 6,20% | 1,96% |
| 2036 | 14,12% | 6,21% | 2,09% |
| YTG 2026 | 13,47% | 6,28% | 0,11% |

YTG significa *year to go*, a parte restante do ano corrente.

## E4. Motor da planilha (modo legado)

### E4.1 Interpolação linear nas taxas

Cada aba monta uma linha por dia útil. A taxa de cada dia é interpolada linearmente entre os vértices vizinhos:

```
taxa(d) = taxa(v1) + (taxa(v2) − taxa(v1)) × (d − v1)/(v2 − v1)
```

Antes do primeiro vértice e depois do último, a taxa fica constante (extrapolação flat).

### E4.2 Acumulação recursiva dia a dia

```
Acum(1) = (1 + realizado_YTD) × (1 + taxa(1))^(1/252) − 1
Acum(d) = (1 + Acum(d−1)) × (1 + taxa(d))^(1/252) − 1
```

- No CDS, `realizado_YTD` vale 0.
- A fórmula **não** é `(1+taxa(d))^(d/252)`. As duas só coincidem em trechos onde a curva é flat.

### E4.3 Realizado do ano

```
realizado_YTD = Π (1 + taxa_mensal_m) − 1, para os meses marcados "Usar"
```

Os meses marcados dependem do campo "Mês Atual" de cada aba. Os acumulados trimestrais são auxiliares:

| Trimestre | IPCA | Selic |
|---|---|---|
| 1T | 1,92% | 3,41% |
| 2T | 1,17% | 3,32% |
| 3T | 0,23% | 3,44% |
| 4T | 0,60% | 3,59% |

### E4.4 Forwards por ano

Os cortes de cada ano ficam em:

```
d₁ = YTG
dₙ = YTG + 252·(n−1)
```

E as taxas anuais saem da razão entre fatores acumulados:

```
Ano 1 = Acum(d₁)                          (já inclui o realizado)
Ano n = (1 + Acum(dₙ)) / (1 + Acum(dₙ₋₁)) − 1
```

O YTG vale 231 dias nas abas Inflação e DI, e 62 dias no CDS (digitado manualmente, campo "<- Mudar").

### E4.5 CDS

- A conversão é bps ÷ 10.000.
- No Dashboard, a coluna "2026" do CDS mostra a taxa do primeiro vértice (0,4567%).
- A coluna "YTG" do CDS mostra o acumulado **não anualizado** de 62 dias (0,112%).
- O vértice de 20 anos só serve para interpolar entre 10 e 20 anos.

### E4.6 Itens a confirmar

- Há quatro números soltos, sem rótulo, na aba Inflação (1,000170; 1,010760; 1,011468; 1,008231).
- Existe uma possível "anualização do DI" pela fórmula `(1+YTG)^(4/trimestres)−1` (suspeita: `DI!E4`). Ela não pode ser observada pelos valores, porque com a aba em 1º trimestre o expoente é 1.

## E5. Leitura econômica (com os vieses de E6)

- **DI:** estável entre 13,5% e 14,2%. A curva não precifica um ciclo relevante de cortes.
- **Inflação implícita:** entre 5,9% e 6,3% em todo o horizonte.
- **Juro real implícito:** cerca de 7,1% em 2027 e 7,5% no longo prazo.
- **CDS forward:** sobe de 0,46% para 2,09% ao ano.

## E6. Diagnóstico

### E6.1 Spot tratado como forward diária (crítico, metodológico)

As taxas dos vértices são spot. Ao acumular dia a dia usando a taxa interpolada de cada dia, a planilha trata cada uma delas como se fosse a forward daquele dia. Com isso, a curva acumulada não reprecifica os vértices de entrada.

Exemplo no prazo de 504 dias (sem o realizado de janeiro):

| Prazo 504 dias | Planilha | Correto (spot) |
|---|---|---|
| Inflação acumulada | 13,00% | 1,059218² − 1 = 12,19% |
| DI acumulado | 28,90% | 1,138898² − 1 = 29,71% |

O efeito depende da inclinação da curva:

- quando a curva cai (inflação), o resultado é superestimado;
- quando a curva sobe (DI), o resultado é subestimado.

Todos os forwards anuais herdam esse viés.

### E6.2 Datas-base diferentes entre abas (crítico, operacional)

- O Dashboard indica 3º trimestre.
- As abas Inflação e DI estão em "Janeiro" / "1º Tri": só janeiro entra no realizado e o YTG é de 231 dias.
- O CDS usa YTG de 62 dias.

Uma ilustração com os próprios dados da planilha:

| Indicador | Planilha | Com o realizado até o mês de referência |
|---|---|---|
| IPCA 2026 | 6,28% | ≈ 5,0% (jan–ago 2,86% + ~83 dias úteis) |
| DI 2026 | 13,47% | ≈ 14,0% (jan–set 10,51% + 62 dias úteis) |

Os anos seguintes também se deslocam, porque os cortes são ancorados no YTG.

### E6.3 Ano fixo de 252 dias úteis (médio)

Um ano civil tem entre cerca de 248 e 254 dias úteis. Com o corte fixo em 252, os limites dos anos vão se afastando de 31/12 ao longo do horizonte.

### E6.4 Curva de inflação diverge da ETTJ (alto)

O input mostra 6,4827% em 126 e em 252 dias (valor repetido). A ETTJ da própria planilha indica 4,79% e 5,22% nesses prazos. Esse trecho domina os resultados de 2026 e 2027.

### E6.5 Realizado sem identificação de ano (médio)

Ao atualizar o mês da aba, valores do ano anterior podem entrar no acumulado sem nenhum aviso.

### E6.6 Defasagem do IPCA (médio)

O IPCA de um mês só sai no mês seguinte. O intervalo entre o último IPCA divulgado e a data-base não é tratado.

### E6.7 Unidades misturadas na linha YTG (médio)

DI e inflação mostram taxa de ano cheio; o CDS mostra um acumulado parcial. Além disso, o "2026" do CDS é apenas o primeiro vértice.

### E6.8 Extrapolação (baixo)

As abas terminam em 2394 dias. Os vértices de inflação em 2520 e 2646 dias são ignorados, e os anos 10 e 11 saem por extrapolação flat.

### E6.9 Selic como realizado do DI (baixo)

A curva é de DI/CDI, mas o realizado usado é a Selic.

### E6.10 CDS capitalizado como taxa (baixo, conceitual)

É uma aproximação aceitável para prêmio de risco, mas não é precificação de CDS.

### E6.11 Rótulos desatualizados (baixo)

Aparecem "YTG2024", "2025…2034", "Inflação Acumulada 2024", "DI Acumulado 2024", "DI Futuro" na aba CDS e "2026.0".

## E7. Resumo

A planilha entrega uma matriz ano × {DI, inflação, CDS}. Ela tem dois defeitos sérios:

1. um erro de método (E6.1);
2. um erro de operação (E6.2).

## E8. Metodologia corrigida

### E8.1 Data-base

Uma única data-base t0, igual ao último dia útil com curvas disponíveis. Dias úteis contados pelo calendário ANBIMA.

### E8.2 Fatores

Para cada vértice `v`, com taxa spot `s(v)` em base 252:

```
F(v) = (1 + s(v))^(v/252)
```

### E8.3 Interpolação flat-forward

```
F(d) = F(v1) × (F(v2)/F(v1))^((d − v1)/(v2 − v1))
```

- **Antes do primeiro vértice:** spot constante, `F(d) = (1+s(v₁))^(d/252)`.
- **Depois do último vértice:** a forward do último segmento é mantida.
- **Uso:** vale para as três curvas. A interpolação linear nas taxas fica disponível apenas como parâmetro de comparação.

### E8.4 Cortes por ano civil

```
dU(Y) = dias úteis de t0 até 31/12/Y
```

### E8.5 Taxa por ano

```
Ano corrente:  Taxa(Y₀) = (1 + realizado_YTD) × F(dU(Y₀)) − 1
Anos seguintes: Taxa(Y) = F(dU(Y)) / F(dU(Y−1)) − 1
```

### E8.6 Realizado

**DI.** CDI realizado no ano até t0, pela série diária do SGS. Não há defasagem.

**Inflação.**
- Usa o IPCA até o último mês divulgado.
- O intervalo entre o fim desse mês e t0 é coberto pela curva, contando os dias a partir do primeiro dia útil depois do último mês realizado.
- A regra aplicada fica registrada no output.
- Como alternativa parametrizável, o IPCA-15 pode cobrir esse intervalo.

### E8.7 CDS

Interpolação flat-forward sobre bps ÷ 10.000. No ano corrente, o CDS publica dois campos rotulados:

- `annualized_rate`;
- `remaining_period_accumulated`.

### E8.8 Saídas derivadas

```
Juro real(Y) = (1 + DI(Y)) / (1 + Inflação(Y)) − 1
```

A taxa de desconto (DI + CDS) depende de uma convenção a ser definida (seção 4 da Parte 1).

## E9. Fontes de dados (verificar todas na implementação)

| Dado | Fonte sugerida | Observação |
|---|---|---|
| Curva DI | B3: ajustes DI1 ou "Taxas Referenciais DI x Pré" | Avaliar bibliotecas como `pyield` |
| Inflação implícita / ETTJ | ANBIMA: Estrutura a Termo (publicação diária) | Mesmo formato da tabela ETTJ da planilha |
| IPCA mensal | BCB SGS série 433 (ou IBGE/SIDRA) | API pública em JSON |
| CDI | BCB SGS 12 (diário) e 4391 (acumulado no mês) | Realizado do modo CORRIGIDO |
| Selic | BCB SGS 11 (diária) e 4390 (acumulada no mês) | Só para o modo LEGADO |
| CDS Brasil (USD) | Investing.com hoje, ou alternativa | Scraping frágil e sujeito a termos de uso; fallback em `data/manual/cds.csv` |
| Calendário | Feriados nacionais ANBIMA | `bizdays`, `pyield` ou arquivo oficial |

## E10. Casos de teste do modo legado

Configuração usada para gerar estes valores:

- Inflação e DI com "Mês Atual" = janeiro;
- realizado: IPCA 0,33% e Selic 1,16%;
- YTG de 231 dias (Inflação e DI) e 62 dias (CDS);
- curvas conforme E3.2.

Tolerância: 1e-8, sujeita à regra de desempate (3.3).

| Teste | Esperado |
|---|---|
| DI: taxa interpolada, dia 127 | 0,1332783571 |
| DI: Acum(1) | 0,01210233742 |
| DI: Acum(127) | 0,07743467076 |
| DI: Acum(231) | 0,1347318473 |
| DI: Acum(504) | 0,3039766 |
| Inflação: taxa interpolada, dia 253 | 0,06479265079 |
| Inflação: Acum(1) | 0,003550109048 |
| Inflação: Acum(231) | 0,06276345587 |
| Inflação: Acum(253) | 0,06860711517 |
| Inflação: Acum(504) | 0,1337749986 |
| CDS: taxa interpolada, dia 127 | 0,004573888889 |
| CDS: Acum(62) | 0,0011216976 |
| CDS: Acum(127) | 0,00229904919 |

Linhas anuais esperadas no Dashboard:

| Ano | DI | Inflação | CDS |
|---|---|---|---|
| 2026 | 0,1347318473 | 0,06276345587 | 0,004567 (1º vértice) |
| 2027 | 0,1367704582 | 0,06170699177 | 0,005040834358 |
| 2028 | 0,1397224171 | 0,05921274213 | 0,006465717867 |
| 2029 | 0,1411788478 | 0,05975990725 | 0,008248988388 |
| 2030 | 0,1419084912 | 0,06048500357 | 0,0104101213 |
| 2031 | 0,1421659309 | 0,06101641848 | 0,01254379297 |
| 2032 | 0,1421324179 | 0,06138540302 | 0,01460425996 |
| 2033 | 0,1419262871 | 0,06165391388 | 0,01663378424 |
| 2034 | 0,1416246573 | 0,06186391725 | 0,01820592628 |
| 2035 | 0,1413084536 | 0,0620259023 | 0,01958959306 |
| 2036 | 0,141248 | 0,062054 | 0,0209406778 |

Acumulados trimestrais esperados:

| Trimestre | IPCA | Selic |
|---|---|---|
| 1T | 0,01921394328 | 0,0340787636 |
| 2T | 0,0117411399 | 0,03315985626 |
| 3T | 0,002285749248 | 0,03438621948 |
| 4T | 0,006010535346 | 0,03592029968 |

Testes mínimos do modo CORRIGIDO:

1. Reprecificação: `F(v) = (1+s(v))^(v/252)` com erro menor que 1e-12.
2. Com curva flat, LEGADO e CORRIGIDO coincidem.
3. Os dias úteis entre os cortes batem com o calendário ANBIMA.

## E11. Rotina operacional (a ser automatizada)

- Uma data-base única, propagada para tudo. YTG sempre calculado, nunca digitado.
- Curvas de DI, inflação e CDS da mesma data-base. Vértices curtos conferidos contra a ETTJ.
- Realizado com mês **e** ano explícitos (Jan/2026). Regra do IPCA não divulgado aplicada e registrada.
- Rótulos de ano corretos e unidade do YTG do CDS explícita.
- Alerta para dado defasado e para variação diária acima do limite.
- Ano corrente conferido contra o realizado acumulado e contra o Focus.
