# F0: Auditoria da planilha `Query-Avila.xlsx`

Data da auditoria: 01/10/2026. Arquivo auditado: `docs/legado/Query-Avila.xlsx` (cópia de `Query - Ávila.xlsx`).

Scripts descartáveis em `scratch/`:

| Script | Função |
|---|---|
| `scratch/dump.py` | Fórmula + valor em cache + cor de preenchimento, célula a célula |
| `scratch/patterns.py` | Agrupa fórmulas repetidas em notação R1C1 (expande colunas longas) |
| `scratch/recalc_formulas.py` | Recalcula o workbook com o motor `formulas` (Python) → `scratch/recalc/QUERY-AVILA.XLSX` |
| `scratch/compare.py` | Cache original × recalculado, para as 22.452 células com fórmula |
| `scratch/indep.py` | Reimplementação independente das fórmulas reais + checagem de E10 + cenários |

> **Desvio de procedimento (3.3).** O LibreOffice não está instalado na máquina (nem o Homebrew). O recálculo de referência foi feito com o motor Python `formulas` 1.3.4, num venv isolado em `scratch/.venv`. Uma reimplementação independente (`scratch/indep.py`) bate com esse recálculo em até 4,4e-16 em todas as colunas diárias e anuais. Decisão de 01/10/2026 (Q7): sem LibreOffice; o motor `formulas` é a referência de recálculo. Ele foi validado também com inputs alterados (ver `OPEN_QUESTIONS.md`, Q7).

---

## 1. Mapa da planilha

Origem provável: exportação do Google Sheets (comentários com `ID#AAAA…`, sem `docProps/app.xml`, valores em cache com 10 dígitos significativos). Sem nomes definidos e sem links externos. Há 6 gráficos, que plotam as colunas W/X (curva interpolada) de Inflação, DI e CDS.

### Dashboard

| Bloco | Células | Tipo |
|---|---|---|
| Trimestre Atual | `C2` = "3º Tri" | Input (validação: lista `'Inflação'!Q3:Q6`). **Só é lido por `CDS!C2`, que não é usado por nada** |
| Mês último IPCA / DI | `C3` = Agosto, `C4` = Setembro | Input (lista `'Inflação'!E9:E20`). **Não referenciados por nenhuma fórmula** |
| Atualizado em | `C5` = 06/09/2026 (serial 46271, um domingo) | Input. Não referenciado |
| Anos | `F3` = 2026.0 (literal), `G3:P3` = anterior+1 | Fórmula |
| DI por ano | `F4` = `DI!E4`; `G4:P4` = `DI!F4:O4`; `Q4` = `DI!S26` | Link |
| CDS por ano | `F5` = `CDS!E4`; `G5:P5` = `CDS!F4:O4`; `Q5` = `CDS!J9` | Link |
| Inflação por ano | `F6` = `'Inflação'!H6`; `G6:P6` = `'Inflação'!F4:O4`; `Q6` = `'Inflação'!E4` | Link |
| Curva de inflação | `B11:C31` (vértices 126…2646; `B16:B29` = anterior+126) | Input (`C`) |
| Curva de DI | `E11:F29` (126…2394) | Input (`F`) |
| CDS (bps) | `H9:I17` + links Investing em `J9:J17` | Input (`I`) |
| Inflação passada | `H20:I31` (Jan…Dez, sem ano) | Input |
| Selic passado | `K20:L31` (Jan…Dez, sem ano) | Input |
| ETTJ ANBIMA | `C37:F57` (IPCA, Pré, Implícita; 126…2520) | Valores. **Não referenciada por nenhuma fórmula** |

### Inflação e DI (estrutura idêntica)

| Bloco | Células | Conteúdo |
|---|---|---|
| Mês Atual | `C2` = "Janeiro" | Input (lista `E9:E20`) |
| Trimestre Atual | `C3` = "1º Tri" | Input (lista `Q3:Q6`) |
| Rótulos de ano | Inflação `E3:O3` = "YTG2024", 2025…2034 (literais); DI `E3:O3` = `Dashboard!F3:P3` | Rótulo |
| Saída por ano | `E4:O4` | Ver fórmulas abaixo |
| "Acumulado 2024" | `H6` = `S27` | Saída do ano 1 (só a de Inflação é lida pelo Dashboard) |
| Vértices | `B7:C25` (126…2394); `C` = `Dashboard!{C\|F}{11..29}/100` | Link |
| Realizado mensal | `E9:G20` (mês, nº, valor) = `Dashboard!{I\|L}{20..31}` | Link |
| Acumulados trimestrais | `Q3:S6` | Auxiliar |
| Matriz "Usar" | `Q11:U22` (mês, trimestre, nº, **T** = Usar 1, **U** = Usar 2) | Fórmula |
| Cortes e forwards | `Q26:S37` | Fórmula |
| Grade diária | `W3:Y3000` (DI até dia 2998, Inflação até 3000) | W = dia, X = taxa, Y = acumulado |
| Células soltas (só Inflação) | `B4` "infla_anterior_calculada"; `F38:G38`, `F39`, `F40` | Não referenciadas |

### CDS

| Bloco | Células | Conteúdo |
|---|---|---|
| Trimestre | `C2` = `Dashboard!C2` | **Não usado** |
| Rótulos | `E2` = "DI Futuro" (errado); `E3:O3` = `DI!E3:O3` | Rótulo |
| Saída por ano | `E4:O4` | Fórmula |
| Vértices | `B8:F16`: prazo, dias (`=126`, `=252`, `=252*k`), link, bps (`=Dashboard!I9..I17`), taxa (`=E/10000`) | Link/fórmula |
| YTG | `I9` = 62 (`K9` "<- Mudar") | **Input manual** |
| Cortes e forwards | `H8:J19` | Fórmula |
| Grade diária | `L8:N5047` (dias 1…5040) | L = dia, M = taxa, N = acumulado |
| Validação órfã | `C3:C4` → lista `$Q$5:$Q$7` (vazia) | Resíduo |

### Dependências

```
Dashboard (inputs) ──► Inflação ──► Dashboard!F6:Q6
                   ──► DI       ──► Dashboard!F4:Q4
                   ──► CDS      ──► Dashboard!F5:Q5
```
As três abas são independentes entre si (CDS só lê `DI!E3:O3`, que são rótulos).

---

## 2. Inventário de fórmulas (Inflação e DI; R1C1 relativo expandido)

`m` = nº do mês em `C2`; `q` = nº do trimestre em `C3`; `trim(i)` = trimestre do mês i; `r_i` = realizado do mês i.

| Célula | Fórmula original | Matemática | Finalidade | Parte 2 |
|---|---|---|---|---|
| `R26` | `=(12-VLOOKUP($C$2,$E$9:$F$20,2,FALSE))*(252/12)` | `YTG = (12−m)·21` | Dias até o fim do ano | E4.4 ✓ (231 com Janeiro) |
| `T11:T22` | `=IF(AND(R>q−1, S<=m), G, 0)` | `T_i = r_i` se `trim(i) ≥ q` e `i ≤ m` | Realizado do trimestre corrente até o mês m | E4.3 ✗ (ver §3) |
| `U11:U22` | `=IF(R<q, G, 0)` | `U_i = r_i` se `trim(i) < q` (independe de m) | Realizado dos trimestres anteriores | E4.3 ✗ |
| `X3:X127` | `=$X$128` | `x(d) = s(126)` para d < 126 | Extrapolação flat à esquerda | E4.1 ✓ |
| `X128, X254, …, X2396` | `=C7`, `=C8`, …, `=C25` | `x(v_k) = s(v_k)` | Âncora no vértice | E4.1 ✓ |
| `X129:X253` (e blocos análogos) | `=X128+($C$8-$C$7)/126` | `x(d) = x(d−1) + (s_{k+1}−s_k)/126` | Interpolação linear **por soma incremental**, passo fixo 126 | E4.1 ✓ (forma diferente) |
| `X2397:X3000` | `=X2396` | `x(d) = s(2394)` | Extrapolação flat à direita | E4.1 / E6.8 ✓ |
| `Y3` | `{=(PRODUCT(1+T11:T22)*(1+X3)^(1/252))-1}` | `A(1) = Π(1+T_i)·(1+x(1))^(1/252) − 1` | Dia 1 com realizado do trimestre corrente | E4.2 ✗ (só T) |
| `Y4:Y3000` | `=(1+Y3)*(1+X4)^(1/252) - 1` | `A(d) = (1+A(d−1))·(1+x(d))^(1/252) − 1` | Acumulação recursiva | E4.2 ✓ |
| `S26` | `=VLOOKUP(R26,$W$3:$Y$3000,3,FALSE)` | `A(YTG)` | Acumulado do início do trimestre q até 31/12 | "YTG" |
| `S27` | `{=(1+S26)*PRODUCT(1+U11:U22)-1}` | `(1+A(YTG))·Π(1+U_i) − 1` | Ano civil completo ("Ano 1") | E4.4 ✗ (ordem) |
| `R28` | `=R26+252`; `R29:R37` = anterior+252 | `d_n = YTG + 252·(n−1)` | Cortes | E4.4 ✓ |
| `S28:S37` | `=(1+VLOOKUP(Rn))/(1+VLOOKUP(Rn−1))-1` | `(1+A(d_n))/(1+A(d_{n−1})) − 1` | Forwards anos 2…11 | E4.4 ✓ |
| `S3:S6` | `{=IF(G11<>0,PRODUCT(1+G9:G11)-1,"-")}` | `Π(1+r_i) − 1` no trimestre | Auxiliar (não usado) | E4.3 ✓ |
| **DI `E4`** | `=(1+S26)^(4/(5-VLOOKUP(C3,Q3:R6,2,FALSE)))-1` | `(1+A(YTG))^(4/(5−q)) − 1` | **Anualização** do período "início do trimestre q → 31/12" | E4.6: confirmada |
| Inflação `E4` | `=S26` | `A(YTG)` | Sem anualização | — |
| `F4:O4` | `=S28` … `=S37` | Forwards anos 2…11 | Saída | ✓ |
| `H6` | `=S27` | Ano civil | Saída ano 1 | — |

### CDS

| Célula | Fórmula | Matemática | Parte 2 |
|---|---|---|---|
| `F8:F16` | `=E/10000` | bps → taxa | E4.5 ✓ |
| `M8:M132` | `=$M$133` | flat à esquerda | ✓ |
| `M133, M259, M511, …, M5047` | `=F8`, `=F9`, … | âncoras nos vértices | ✓ |
| `M134:M258` etc. | `=M133+($F$9-$F$8)/($C$9-$C$8)` | soma incremental, passo = (v₂−v₁) real | ✓ (≠ DI/Inflação, que usam 126 fixo; equivalente porque lá os vértices são equiespaçados) |
| `N8` | `=(1+$M$8)^(1/252) - 1` | `A(1)` sem realizado | E4.2 ✓ |
| `N9:N5047` | `=(1+N8)*((1+M9)^(1/252)) - 1` | recursiva | ✓ |
| `J9` | `=VLOOKUP(I9,L8:N5047,3,FALSE)` | `A(62)` | E4.5 ✓ |
| `I10:I19` | `=I9+252` … | cortes | ✓ |
| `J10` | `=(1+VLOOKUP(I10))/(1+J9) - 1` | forward ano 2 | ✓ |
| `J11:J19` | razão de VLOOKUPs | forwards 3…11 | ✓ |
| **`E4`** | `=(1+J9)^(252/I9) - 1` | **anualização de A(62)** com 252/YTG | E4.5 ✗ (não é "1º vértice") |

### Células soltas (Inflação)

| Célula | Fórmula | Valor |
|---|---|---|
| `F38` | `=(1+4.374%)^(1/252)` | 1,000169897 |
| `G38` | `=F38^63` | 1,010760082 |
| `F39` | `=G38*(1+G15)` (× julho) | 1,011467614 |
| `F40` | `=F39*(1+G16)` (× agosto) | 1,008230918 |

Parecem uma conta manual de 63 d.u. a 4,374% a.a. composta com o IPCA de julho e agosto (rótulo `B4` "infla_anterior_calculada"). Nada referencia essas células.

---

## 3. Recálculo e comparação

| Comparação | Resultado |
|---|---|
| Cache × recálculo (`formulas`) | 22.452 células; diferença máxima 5,0e-10 (`Inflação!Y2991`). Causa: cache gravado com 10 dígitos significativos. Nenhuma divergência > 1e-8 → nenhum `FORMULA_RECALC_REQUIRED` |
| Recálculo × reimplementação independente | Colunas Y/N diárias: ≤ 4,4e-16. Saídas anuais: ≤ 5,6e-17 |
| E10 × recálculo | 13 pontos e 30 valores anuais dentro de 1e-8 (máx. 4,5e-11, arredondamento da própria E10) |

---

## 4. Cenários auxiliares (reimplementação, não são fixture)

Com as abas configuradas como o Dashboard sugere:

| Cenário | YTG | DI `S26` | DI `E4` (Dashboard) | DI `S27` (ano civil) | Inflação `S27` (Dashboard) | DI 2027 | Infl. 2027 |
|---|---|---|---|---|---|---|---|
| Janeiro / 1º Tri (atual) | 231 | 13,4732% | 13,4732% | 13,4732% | 6,2763% | 13,6770% | 6,1707% |
| Agosto / 3º Tri | 84 | 6,6806% | 13,8075% | 13,9742% | 5,0364% | 13,4312% | 6,4340% |
| Setembro / 3º Tri | 63 | 6,7250% | 13,9022% | 14,0216% | 4,9896% | 13,4060% | 6,4552% |

### Comportamento de erro (confirmado na F1)

O `#N/A` dos `VLOOKUP` exatos é local. Com Dezembro (YTG = 0), só ficam com erro S26, S27, H6, S28, E4 e F4 de cada aba e, no Dashboard, F4:G4, F6:G6, Q4 e Q6; os anos 2028–2036 e o CDS inteiro seguem válidos. Com `CDS!I9` = 0 ou acima de 2520, o erro fica só nos cortes do CDS que caem fora da grade. O motor reproduz isso com `None`.

E6.1 reproduzido: acumulado a 504 d.u. sem realizado = 13,00% (inflação) e 28,90% (DI), contra 12,19% e 29,71% pela spot.
