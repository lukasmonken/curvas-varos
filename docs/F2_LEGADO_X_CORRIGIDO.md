# F2: LEGADO × CORRIGIDO com os inputs da planilha

Data-base (t0): 29/09/2026 (Q8). LEGADO = uso (a), a planilha exatamente como está (abas em Janeiro/1º Tri, YTG do CDS = 62). CORRIGIDO = E8 com as curvas da ANBIMA de 29/09/2026 como publicadas (Q15): inflação implícita de 252 a 2520 d.u.; DI = ETTJ PREF + Circular 3.361 abaixo de 252 (21, 42, 63 e 126 d.u.); CDS da planilha; calendário ANBIMA; realizado do BCB (CDI SGS 12, IPCA SGS 433) e datas de divulgação do IBGE.

- dU(2026) a partir de t0: 64 dias úteis; anos seguintes: 251, 248, 249, 252, 252, 252, 251, 248, 249, 253.
- CDI realizado em 2026 até t0 (exclusive): 10,3943%.
- IPCA realizado de 01/2026 a 08/2026 (último IPCA divulgado até t0: 08/2026, em 11/09/2026). De 01/09/2026 a 31/12/2026, coberto pela curva: 83 dias úteis contados do 1º dia útil após o último mês realizado (E8.6). IPCA realizado no ano: 3,1058%.
- Convenção de t0 (Q11, a confirmar): o dia t0 fica na curva (dU conta de t0 a 31/12, inclusive) e o CDI realizado vai até a véspera de t0; é a contagem de DU da B3.
- Alcance da regra do IPCA (Q12, a confirmar): o intervalo vale só para o ano corrente; os anos seguintes usam dU contado de t0 (E8.5).
- As curvas digitadas na planilha são a publicação da ANBIMA de 29/09/2026 (`docs/F3_RECONCILIACAO_ANBIMA.md`). A de DI tem um erro de colagem (o vértice 378 foi pulado e os seguintes subiram uma posição); o efeito dele aparece separado, na coluna **erro de colagem**.
- Sensibilidade, IPCA-15 no lugar do IPCA não divulgado (Forma A, Q13, desligada por padrão): Inflação 2026 = 5,4446% (+18,3 bps sobre o CORRIGIDO); Juro real 2026 = 8,0717% (-18,8 bps). IPCA realizado de 01/2026 a 08/2026 (último IPCA divulgado até t0: 08/2026, em 11/09/2026). IPCA-15 de 09/2026 (+0,70%, divulgado em 25/09/2026) no lugar do IPCA desse mês (Forma A, Q13). De 01/10/2026 a 31/12/2026, coberto pela curva: 62 dias úteis (E8.6).

## Tabela principal

Valores em % ao ano; diferenças (CORRIGIDO − LEGADO) em bps. Causas com |efeito| ≥ 0,5 bp, em bps, da maior para a menor.

### DI

| Ano | LEGADO | CORRIGIDO | Dif. (bps) | Causas (bps) |
|---|---:|---:|---:|---|
| 2026 | 13,4732% | 13,9558% | +48,3 | realizado +953,2; corte em 31/12 -904,7 |
| 2027 | 13,6770% | 13,5406% | -13,6 | corte em 31/12 -18,1; acumulação +17,8; erro de colagem -9,9; calendário -5,7; interpolação +2,2 |
| 2028 | 13,9722% | 13,9524% | -2,0 | acumulação +50,9; calendário -23,5; corte em 31/12 -18,2; erro de colagem -10,9 |
| 2029 | 14,1179% | 14,3106% | +19,3 | acumulação +55,9; calendário -18,2; corte em 31/12 -11,6; erro de colagem -6,2; interpolação -0,7 |
| 2030 | 14,1908% | 14,5299% | +33,9 | acumulação +43,9; corte em 31/12 -6,2; erro de colagem -2,9 |
| 2031 | 14,2166% | 14,4357% | +21,9 | acumulação +25,8; corte em 31/12 -2,6; erro de colagem -0,8 |
| 2032 | 14,2132% | 14,2942% | +8,1 | acumulação +8,2 |
| 2033 | 14,1926% | 14,0863% | -10,6 | acumulação -6,8; calendário -6,0; erro de colagem +1,2; corte em 31/12 +1,1 |
| 2034 | 14,1625% | 13,7726% | -39,0 | calendário -23,9; acumulação -18,4; corte em 31/12 +1,8; erro de colagem +1,6 |
| 2035 | 14,1308% | 13,7146% | -41,6 | acumulação -27,5; calendário -17,8; corte em 31/12 +1,9; erro de colagem +1,8 |
| 2036 | 14,1248% | 13,8580% | -26,7 | interpolação -24,6; acumulação -10,0; calendário +6,1; erro de colagem +1,8 |

### Inflação

| Ano | LEGADO | CORRIGIDO | Dif. (bps) | Causas (bps) |
|---|---:|---:|---:|---|
| 2026 | 6,2763% | 5,2611% | -101,5 | corte em 31/12 -433,3; realizado +331,8 |
| 2027 | 6,1707% | 6,1315% | -3,9 | corte em 31/12 +28,4; acumulação -24,3; interpolação -5,4; calendário -2,6 |
| 2028 | 5,9213% | 5,4386% | -48,3 | acumulação -52,9; calendário -9,5; corte em 31/12 +8,9; interpolação +5,3 |
| 2029 | 5,9760% | 5,9903% | +1,4 | acumulação +12,7; calendário -7,4; corte em 31/12 -4,6; interpolação +0,6 |
| 2030 | 6,0485% | 6,2807% | +23,2 | acumulação +28,2; corte em 31/12 -4,6 |
| 2031 | 6,1016% | 6,3327% | +23,1 | acumulação +26,7; corte em 31/12 -3,3 |
| 2032 | 6,1385% | 6,3374% | +19,9 | acumulação +22,4; corte em 31/12 -2,3 |
| 2033 | 6,1654% | 6,3106% | +14,5 | acumulação +18,9; calendário -2,6; corte em 31/12 -1,7 |
| 2034 | 6,1864% | 6,2364% | +5,0 | acumulação +16,6; calendário -10,2; corte em 31/12 -1,3 |
| 2035 | 6,2026% | 6,2712% | +6,9 | acumulação +15,6; calendário -7,7; corte em 31/12 -1,0 |
| 2036 | 6,2054% | 6,3841% | +17,9 | interpolação +10,6; acumulação +4,8; calendário +2,5 |

### CDS

| Ano | LEGADO | CORRIGIDO | Dif. (bps) | Causas (bps) |
|---|---:|---:|---:|---|
| 2026 | 0,4567% | 0,4567% | 0,0 | — |
| 2027 | 0,5041% | 0,6311% | +12,7 | acumulação +10,3; interpolação +2,5 |
| 2028 | 0,6466% | 0,9060% | +25,9 | acumulação +26,1; calendário -1,2; interpolação +0,9 |
| 2029 | 0,8249% | 1,3611% | +53,6 | acumulação +54,6; calendário -1,5 |
| 2030 | 1,0410% | 1,8599% | +81,9 | acumulação +82,7; calendário -0,7 |
| 2031 | 1,2544% | 2,2799% | +102,6 | acumulação +98,6; interpolação +4,5; calendário -0,7 |
| 2032 | 1,4604% | 2,7494% | +128,9 | acumulação +117,9; interpolação +11,4; calendário -0,7 |
| 2033 | 1,6634% | 2,8163% | +115,3 | acumulação +127,6; interpolação -11,2; calendário -1,3 |
| 2034 | 1,8206% | 3,0573% | +123,7 | acumulação +105,5; interpolação +21,6; calendário -3,5 |
| 2035 | 1,9590% | 3,0698% | +111,1 | acumulação +119,5; interpolação -5,4; calendário -3,1 |
| 2036 | 2,0941% | 3,0563% | +96,2 | acumulação +114,5; interpolação -18,5 |

### Juro real

| Ano | LEGADO | CORRIGIDO | Dif. (bps) | Causas (bps) |
|---|---:|---:|---:|---|
| 2026 | 6,7718% | 8,2601% | +148,8 | realizado +582,7; corte em 31/12 -433,7 |
| 2027 | 7,0701% | 6,9811% | -8,9 | corte em 31/12 -45,5; acumulação +41,1; erro de colagem -9,3; interpolação +7,6; calendário -2,8 |
| 2028 | 7,6009% | 8,0746% | +47,4 | acumulação +102,0; corte em 31/12 -26,1; calendário -12,5; erro de colagem -10,2; interpolação -5,8 |
| 2029 | 7,6828% | 7,8500% | +16,7 | acumulação +39,9; calendário -9,7; corte em 31/12 -6,3; erro de colagem -5,8; interpolação -1,3 |
| 2030 | 7,6779% | 7,7617% | +8,4 | acumulação +12,7; erro de colagem -2,7; corte em 31/12 -1,1 |
| 2031 | 7,6483% | 7,6204% | -2,8 | acumulação -2,8; corte em 31/12 +0,9; erro de colagem -0,8 |
| 2032 | 7,6077% | 7,4826% | -12,5 | acumulação -15,0; corte em 31/12 +2,1 |
| 2033 | 7,5611% | 7,3142% | -24,7 | acumulação -25,5; calendário -3,0; corte em 31/12 +2,7; erro de colagem +1,1 |
| 2034 | 7,5114% | 7,0937% | -41,8 | acumulação -34,1; calendário -12,2; corte em 31/12 +3,1; erro de colagem +1,5 |
| 2035 | 7,4652% | 7,0042% | -46,1 | acumulação -41,6; calendário -9,0; corte em 31/12 +2,8; erro de colagem +1,7 |
| 2036 | 7,4567% | 7,0253% | -43,1 | interpolação -33,9; acumulação -14,3; calendário +3,2; erro de colagem +1,7 |

### CDS no ano corrente (E8.7)

| Campo | LEGADO | CORRIGIDO | Dif. (bps) | Causa |
|---|---:|---:|---:|---|
| annualized_rate (coluna 2026) | 0,4567% | 0,4567% | 0,0 | corte em 31/12 (YTG digitado do CDS: 62 → 64); antes do 1º vértice a taxa é a mesma |
| remaining_period_accumulated (coluna YTG) | 0,1122% | 0,1158% | +0,4 | corte em 31/12 (YTG digitado do CDS: 62 → 64); mesmo conceito, acumulado sem anualizar (E6.7) |

## Decomposição por causa (bps)

Cascata em ordem fixa; cada coluna é o efeito de trocar só aquela causa, mantidas as trocas anteriores. A soma das colunas é a diferença total.

Como ler:

- **erro de colagem** (E6.12, Q14): troca a curva de DI digitada pela mesma curva da ANBIMA alinhada, ainda no método da planilha. Mexe só no DI e no juro real.
- **corte em 31/12** e **realizado** são as duas metades do mesmo erro de data-base (E6.2): a planilha soma o realizado de janeiro a 231 dias de curva; o CORRIGIDO soma o realizado do ano aos dias de curva até 31/12. No ano corrente, os dois efeitos são grandes e de sinais opostos; o que importa é a soma.
- No DI, **realizado** = CDI até a véspera de t0 + 64 dias de curva. Na inflação, = IPCA até o último mês divulgado + 83 dias de curva desde o 1º dia útil seguinte (E8.6); desses, 19 dias são curva no lugar do IPCA ainda não divulgado, e respondem por cerca de +49,7 bps do efeito.
- **anualização** é zero aqui porque as abas estão no 1º Tri (expoente 4/(5−1) = 1). Com a planilha em outro trimestre, ela deixa de ser zero (ver F0, D2).
- **acumulação** é o E6.1: a planilha trata a taxa spot de cada dia como forward.
- **interpolação** inclui a extrapolação depois do último vértice (E8.3: forward do último segmento, contra taxa flat na planilha) e a troca de vértices: o CORRIGIDO usa só os publicados pela ANBIMA (sem os remendos 126 e 2646 da inflação; com os vértices curtos 21 a 126 e o 2520 do DI).
- A ordem da cascata importa só na divisão entre causas que interagem, sobretudo **acumulação** e **interpolação**: a soma das duas não depende da ordem, mas a divisão entre elas sim (aqui, a interação fica com a interpolação, que vem depois).

### DI

| Ano | erro de colagem | anualização | corte em 31/12 | realizado | calendário | acumulação | interpolação | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 0,0 | 0,0 | -904,7 | +953,2 | 0,0 | 0,0 | -0,2 | +48,3 |
| 2027 | -9,9 | 0,0 | -18,1 | 0,0 | -5,7 | +17,8 | +2,2 | -13,6 |
| 2028 | -10,9 | 0,0 | -18,2 | 0,0 | -23,5 | +50,9 | -0,4 | -2,0 |
| 2029 | -6,2 | 0,0 | -11,6 | 0,0 | -18,2 | +55,9 | -0,7 | +19,3 |
| 2030 | -2,9 | 0,0 | -6,2 | 0,0 | -0,4 | +43,9 | -0,5 | +33,9 |
| 2031 | -0,8 | 0,0 | -2,6 | 0,0 | -0,2 | +25,8 | -0,3 | +21,9 |
| 2032 | +0,4 | 0,0 | -0,3 | 0,0 | 0,0 | +8,2 | -0,2 | +8,1 |
| 2033 | +1,2 | 0,0 | +1,1 | 0,0 | -6,0 | -6,8 | -0,1 | -10,6 |
| 2034 | +1,6 | 0,0 | +1,8 | 0,0 | -23,9 | -18,4 | -0,1 | -39,0 |
| 2035 | +1,8 | 0,0 | +1,9 | 0,0 | -17,8 | -27,5 | 0,0 | -41,6 |
| 2036 | +1,8 | 0,0 | +0,1 | 0,0 | +6,1 | -10,0 | -24,6 | -26,7 |

### Inflação

| Ano | erro de colagem | anualização | corte em 31/12 | realizado | calendário | acumulação | interpolação | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 0,0 | 0,0 | -433,3 | +331,8 | 0,0 | 0,0 | 0,0 | -101,5 |
| 2027 | 0,0 | 0,0 | +28,4 | 0,0 | -2,6 | -24,3 | -5,4 | -3,9 |
| 2028 | 0,0 | 0,0 | +8,9 | 0,0 | -9,5 | -52,9 | +5,3 | -48,3 |
| 2029 | 0,0 | 0,0 | -4,6 | 0,0 | -7,4 | +12,7 | +0,6 | +1,4 |
| 2030 | 0,0 | 0,0 | -4,6 | 0,0 | -0,2 | +28,2 | -0,1 | +23,2 |
| 2031 | 0,0 | 0,0 | -3,3 | 0,0 | -0,2 | +26,7 | -0,1 | +23,1 |
| 2032 | 0,0 | 0,0 | -2,3 | 0,0 | -0,1 | +22,4 | -0,1 | +19,9 |
| 2033 | 0,0 | 0,0 | -1,7 | 0,0 | -2,6 | +18,9 | -0,1 | +14,5 |
| 2034 | 0,0 | 0,0 | -1,3 | 0,0 | -10,2 | +16,6 | 0,0 | +5,0 |
| 2035 | 0,0 | 0,0 | -1,0 | 0,0 | -7,7 | +15,6 | 0,0 | +6,9 |
| 2036 | 0,0 | 0,0 | 0,0 | 0,0 | +2,5 | +4,8 | +10,6 | +17,9 |

### CDS

| Ano | erro de colagem | anualização | corte em 31/12 | realizado | calendário | acumulação | interpolação | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 0,0 | 0,0 | 0,0 | 0,0 | 0,0 | 0,0 | 0,0 | 0,0 |
| 2027 | 0,0 | 0,0 | +0,1 | 0,0 | -0,2 | +10,3 | +2,5 | +12,7 |
| 2028 | 0,0 | 0,0 | +0,1 | 0,0 | -1,2 | +26,1 | +0,9 | +25,9 |
| 2029 | 0,0 | 0,0 | +0,2 | 0,0 | -1,5 | +54,6 | +0,4 | +53,6 |
| 2030 | 0,0 | 0,0 | +0,2 | 0,0 | -0,7 | +82,7 | -0,3 | +81,9 |
| 2031 | 0,0 | 0,0 | +0,2 | 0,0 | -0,7 | +98,6 | +4,5 | +102,6 |
| 2032 | 0,0 | 0,0 | +0,2 | 0,0 | -0,7 | +117,9 | +11,4 | +128,9 |
| 2033 | 0,0 | 0,0 | +0,1 | 0,0 | -1,3 | +127,6 | -11,2 | +115,3 |
| 2034 | 0,0 | 0,0 | +0,1 | 0,0 | -3,5 | +105,5 | +21,6 | +123,7 |
| 2035 | 0,0 | 0,0 | +0,1 | 0,0 | -3,1 | +119,5 | -5,4 | +111,1 |
| 2036 | 0,0 | 0,0 | +0,1 | 0,0 | +0,1 | +114,5 | -18,5 | +96,2 |

### Juro real

| Ano | erro de colagem | anualização | corte em 31/12 | realizado | calendário | acumulação | interpolação | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 0,0 | 0,0 | -433,7 | +582,7 | 0,0 | 0,0 | -0,2 | +148,8 |
| 2027 | -9,3 | 0,0 | -45,5 | 0,0 | -2,8 | +41,1 | +7,6 | -8,9 |
| 2028 | -10,2 | 0,0 | -26,1 | 0,0 | -12,5 | +102,0 | -5,8 | +47,4 |
| 2029 | -5,8 | 0,0 | -6,3 | 0,0 | -9,7 | +39,9 | -1,3 | +16,7 |
| 2030 | -2,7 | 0,0 | -1,1 | 0,0 | -0,1 | +12,7 | -0,4 | +8,4 |
| 2031 | -0,8 | 0,0 | +0,9 | 0,0 | 0,0 | -2,8 | -0,2 | -2,8 |
| 2032 | +0,4 | 0,0 | +2,1 | 0,0 | +0,1 | -15,0 | -0,1 | -12,5 |
| 2033 | +1,1 | 0,0 | +2,7 | 0,0 | -3,0 | -25,5 | -0,1 | -24,7 |
| 2034 | +1,5 | 0,0 | +3,1 | 0,0 | -12,2 | -34,1 | 0,0 | -41,8 |
| 2035 | +1,7 | 0,0 | +2,8 | 0,0 | -9,0 | -41,6 | 0,0 | -46,1 |
| 2036 | +1,7 | 0,0 | +0,1 | 0,0 | +3,2 | -14,3 | -33,9 | -43,1 |
