# F3: reconciliação da planilha com a ETTJ da ANBIMA

Fonte: download CSV da página [curvas de juros fechamento](https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm) (`est-termo/CZ-down.asp`). Respostas gravadas em `tests/fixtures/f3/anbima/` (23/09 a 30/09/2026). Prova automatizada em `tests/test_reconciliacao_anbima.py`.

## O que a ANBIMA publica

- **Histórico público de 5 dias úteis.** Não dá para baixar 04/09/2026 hoje, e não contornamos o limite. Consequência para o pipeline: o bruto precisa ser gravado todo dia útil; dia perdido há mais de uma semana não se recupera pela página pública.
- **Dia não útil ou ainda não publicado:** HTTP 200 com corpo vazio. Às 18h05 de 01/10/2026, o dia ainda não estava publicado.
- **Seções do arquivo:** parâmetros de Svensson (PREFIXADOS e IPCA); a ETTJ com "ETTJ IPCA", "ETTJ PREF" e "Inflação Implícita" a partir do vértice 252 (PREF e implícita só até 2520); a curva prefixada da Circular 3.361 (21, 42, 63, 126, 252, 504, 756, 1008, 1260, 2520); e o erro título a título.

## De onde vêm as curvas da planilha

| Curva | Origem exata | Diferença |
|---|---|---|
| Inflação (`Dashboard!C11:C31`) | "Inflação Implícita" de **29/09/2026**; vértice 126 = valor do 252; vértice 2646 = valor do 2520 | 0 nos 21 valores |
| DI (`Dashboard!F11:F29`) | 126 = Circular 3.361; 252 = ETTJ PREF; **de 378 a 2394 = ETTJ PREF do vértice seguinte** (504 a 2520), de **29/09/2026** | 0 nos 19 valores |
| Tabela ETTJ colada (`Dashboard!C37:F57`) | Outra data, mais antiga (ainda tinha o vértice 126) | Não é usada por fórmula |

Nenhum dos outros 5 dias disponíveis bate.

## Consequências

1. **Data das curvas = 29/09/2026**, não 04/09/2026 (Q8). Isso é coerente com o realizado da planilha, que já tinha o IPCA de agosto (divulgado em 11/09) e a Selic de setembro. A tabela da F2 foi refeita com t0 = 29/09 (`docs/F2_LEGADO_X_CORRIGIDO.md`).
2. **Erro de colagem na curva de DI (E6.12, operacional).** O vértice 378 (13,6052%) ficou de fora e todos os seguintes subiram uma posição. Efeito no LEGADO (método da planilha, curva certa − curva digitada), que é a coluna **erro de colagem** da tabela da F2: DI 2027 −9,9 bps; 2028 −10,9; 2029 −6,2; 2030 −2,9; 2031 −0,8; de 2032 a 2036, de +0,4 a +1,8.
3. **Remendos manuais da inflação:** a ANBIMA não publica a implícita no 126 nem no 2646. O operador copia o 252 e o 2520. O LEGADO (uso b) precisa repetir isso para manter o método; o CORRIGIDO não precisa (antes do 1º vértice, spot constante; depois do último, forward do último segmento).
