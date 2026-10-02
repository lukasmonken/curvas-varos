# Questões em aberto

Status: `ABERTA` até resposta explícita. Coluna "Bloqueia" indica a primeira fase que não pode avançar sem resposta.

| # | Questão | Bloqueia | Status |
|---|---|---|---|
| Q1 | Curva de inflação: fonte e data-base | F3 | RESOLVIDA: ANBIMA (curvas de juros fechamento), publicação de 29/09/2026 (ver Q8 e a reconciliação) |
| Q2 | Fonte do CDS (diagnóstico antes de qualquer scraper) | F3 | RESOLVIDA: manual (`data/manual/cds.csv`) + cotação à Cbonds; sem coletor do Investing |
| Q3 | Repositório público ou privado | F4 | RESOLVIDA: repositório e site públicos (GitHub Free) |
| Q4 | Convenção da taxa de desconto (DI + CDS) | F4 | RESOLVIDA: composição (1 + DI)(1 + CDS) − 1 |
| Q5 | Identidade visual: fontes, logo, paleta completa | F5 | RESOLVIDA: Instrument Sans; logo = "VAROS" em texto; tema escuro da paleta |
| Q6 | LEGADO (b): como derivar mês e trimestre de t0 | F4 | RESOLVIDA: m = último IPCA divulgado até t0; trimestre de m |
| Q7 | Recálculo de referência: aceitar o motor `formulas` no lugar do LibreOffice | F1 | RESOLVIDA (01/10/2026) |
| Q8 | Data-base (t0) dos inputs da planilha para o CORRIGIDO | F2 | RESOLVIDA: t0 = 29/09/2026 (refazer a F2 com o efeito do erro do DI à parte) |
| Q9 | Realizado do CORRIGIDO na tabela da F2 | F2 | RESOLVIDA: leitura pontual do BCB (SGS 12 e 433) + agenda do IBGE |
| Q10 | Fonte do calendário ANBIMA | F2 | RESOLVIDA: arquivo oficial ANBIMA versionado + conferência com `bizdays` |
| Q11 | Convenção do dia t0 (realizado × curva) | F4 | RESOLVIDA: B (t0 na curva; CDI até a véspera) |
| Q12 | Alcance da regra do IPCA não divulgado nos anos seguintes | F4 | RESOLVIDA: (ii) só o ano corrente |
| Q13 | Alternativa do IPCA-15 para o intervalo (E8.6) | F3 | RESOLVIDA: Forma A, parâmetro desligado por padrão |
| Q14 | Erro de colagem na curva de DI da planilha (E6.12) | F3 | RESOLVIDA: LEGADO (a) reproduz como está; F2 mostra o efeito à parte; diário sem o erro |
| Q15 | Composição das curvas a partir da ANBIMA (LEGADO b e CORRIGIDO) | F4 | RESOLVIDA: LEGADO como o operador (sem o erro); CORRIGIDO só vértices publicados |
| Q16 | CDS diário, gratuito e automático | — | ABERTA (meta; ver texto) |
| Q17 | CDS copiado do Investing.com num repositório público | — | RESOLVIDA: publicar com os valores (decisão de 02/10/2026); links de coleta no site |
| Q18 | CDI do SGS atrasado na véspera de t0 | — | PROVISÓRIO: repetir a última taxa, com alerta |
| Q19 | ANBIMA vai desligar a aba das curvas (download CZ-down.asp) | — | RISCO: monitorar |

## Q1. Curva de inflação implícita

Os inputs de `Dashboard!C11:C31` não batem com a ETTJ ANBIMA colada na mesma aba (`C37:F57`): 6,4827% vs 4,7858% em 126 d.u.; 6,4827% vs 5,2187% em 252 d.u. Os vértices 126 e 252 são idênticos. O comentário em `Dashboard!C10` aponta para `anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm`.

- Qual é a fonte exata (ANBIMA ETTJ, B3, outra) e a data-base da curva digitada?
- Os vértices 126 e 252 iguais são intencionais?

No modo LEGADO, nenhuma substituição será feita sem resposta.

## Q2. Fonte do CDS

Hoje: cópia manual do Investing.com (9 links em `Dashboard!J9:J17`). O diagnóstico (viabilidade, API, termos de uso/robots, risco de bloqueio, alternativas) será entregue no início da F3, antes de qualquer código de coleta. Fallback obrigatório: `data/manual/cds.csv`.

- Existe acesso licenciado (Bloomberg, Refinitiv/LSEG, S&P/Markit) na VAROS?

## Q3. Repositório público ou privado

Pela política que conheço do GitHub Pages, publicar a partir de repositório privado exige plano pago (Pro, Team ou Enterprise); no plano Free, só repositório público. A política será reconferida na F4. Em qualquer caso, o site publicado é público e expõe os dados.

- Qual conta/organização e qual plano?

## Q4. Taxa de desconto

E8.8 deixa em aberto: soma `DI + CDS`, composição `(1+DI)(1+CDS) − 1`, ou spread sobre a curva.

## Q5. Identidade visual

`brand/` não existia. Recebido: captura com a paleta de gráficos (salva em `brand/paleta-graficos.png`):

- fundo do gráfico `#131313`;
- título, legenda e fonte `#E2E5EB`; eixos `#C6CAD2`;
- verdes/turquesas `#296055`, `#239B84`, `#12D8B2`, `#43AF43`, `#4FE04F`;
- uso recomendado: `#C6CAD2`, `#878D96`, `#296055`, `#43AF43`.

Faltam: fonte tipográfica, logo (SVG), cores de fundo/superfície da página (além do gráfico), cores de alerta (verde/amarelo/vermelho do status de fonte) e se existe tema claro.

## Q6. LEGADO (b): derivação de mês e trimestre a partir de t0

A planilha tem dois parâmetros por aba, e o comentário diz que o trimestre é o "posterior à última atualização dos dados". As fórmulas fazem:

- `T` (aplicado no dia 1) = meses do trimestre `q` até o mês `m`;
- `U` (aplicado depois, só no "Ano 1") = meses dos trimestres anteriores a `q`;
- `DI!E4` anualiza com expoente `4/(5−q)`.

Quando `m` é o último mês de um trimestre (ex.: março), `q = 1` e `q = 2` dão o mesmo ano civil, mas o DI 2026 do Dashboard muda (expoente 1 vs 4/3). A instrução da Parte 1 é que mês, trimestre, realizado e YTG sejam iguais nas três curvas.

Proposta (aguarda aprovação):

1. `m` = último mês com IPCA **e** CDI/Selic divulgados até t0 (na prática, o mês do último IPCA, por causa da defasagem).
2. `q` = trimestre que contém `m` (coerente com os exemplos da planilha: Janeiro → 1º Tri; Agosto → 3º Tri).
3. CDS: `YTG = (12 − m)·21`, igual às outras curvas.

Caso a decidir junto (levantado na revisão da F1): a **virada do ano**. Entre a divulgação do IPCA de dezembro (por volta de 10/jan) e a de janeiro, a regra 1 dá `m = 12`. Aí o YTG é 0 e a planilha devolve `#N/A` no ano corrente, embora os anos seguintes saiam normalmente (o motor já reproduz esse `#N/A` parcial). Além disso, nesse período o "ano corrente" do LEGADO ainda é o ano anterior, e o realizado sem ano (E6.5) mistura os anos. Proposta: na virada, o LEGADO (b) publica o ano corrente como indisponível, com alerta, e os anos seguintes normalmente; nada de reinterpretar a fórmula.

## Q7. Recálculo de referência

O LibreOffice não está instalado. O recálculo foi feito com o motor Python `formulas` e conferido por uma reimplementação independente (diferença ≤ 4,4e-16). Aceitar isso como referência, ou instalar o LibreOffice e repetir com `soffice`?

**Resposta (01/10/2026):** sem LibreOffice. A referência de recálculo da regra 3.3 passa a ser o motor `formulas` 1.3.4, que roda só nos scripts de geração de fixtures (`scratch/`) e nunca em runtime.

Evidência de que o motor recalcula de fato e não reaproveita o cache:

- os valores saem com precisão completa (ex.: `DI!E4` = 0,1347318473450274), enquanto o cache tem 10 dígitos;
- com mês/trimestre alterados nas abas DI e Inflação (Agosto/3º Tri e Setembro/3º Tri), as saídas mudam e coincidem exatamente (diferença 0) com a reimplementação independente (`scratch/recalc_cenarios.py`, `scratch/recalc/cenarios_formulas.json`).

## Q8 a Q10. Decisões da F2 (01/10/2026)

- **Q8:** t0 = 04/09/2026 (sexta-feira, último dia útil antes do "Atualizado em" 06/09/2026, um domingo).
  - **Nota (revisão da F2):** o realizado da planilha já traz o IPCA de 08/2026 (−0,32%), que o IBGE divulgou em 11/09/2026. Ou a planilha foi atualizada em parte depois de 11/09, ou o −0,32 é outro número. Se as curvas digitadas forem posteriores a 04/09, toda a coluna CORRIGIDO muda: com t0 = 11/09, por exemplo, dU(2026) cai de 80 para 76 e o IPCA de agosto entra no realizado. **Confirmar a data das curvas** (ligado à Q1).
- **Q9:** CDI diário (SGS 12) e IPCA mensal (SGS 433) do BCB, mais a agenda de divulgações do IBGE (API de calendário), que dá a `publication_date` de cada IPCA. Essa terceira fonte não está em E9; ela é necessária porque o SGS não informa a data de divulgação. Dados em `tests/fixtures/f2/`, com `manifest.json`.
- **Q10:** `data/calendar/feriados_nacionais.xls` (ANBIMA, 2001–2099) → `feriados_anbima.csv`; conferido dia a dia com o `bizdays` e com as datas reais do CDI de 2026.

## Q11. Convenção do dia t0

E8.4 diz "dias úteis de t0 até 31/12/Y" e E8.6 diz "CDI realizado no ano até t0", sem dizer em qual dos dois lados o próprio dia t0 entra. As duas convenções consistentes (nenhum dia contado duas vezes) são:

- **(B) t0 na curva**, que é a adotada provisoriamente: dU = dias úteis de t0 (inclusive) a 31/12 (inclusive), e CDI realizado até a véspera de t0. É a contagem de DU da B3 (pregão inclusive, vencimento exclusive) e coincide com o DU do DI1 de janeiro do ano seguinte. Com t0 = 29/09/2026 (tabela da F2): dU(2026) = 64 e 185 dias de CDI.
- **(A) t0 no realizado:** dU conta a partir do dia seguinte a t0 (63) e o CDI inclui t0 (186 dias).

Impacto de A em relação a B na tabela da F2 (t0 = 29/09): no máximo 0,74 bp (Juro real 2027 −0,74; Inflação 2027 +0,51; DI 2027 −0,23). Recomendação: **manter B**.

## Q12. Alcance da regra do IPCA não divulgado

E8.6 manda cobrir o intervalo entre o último IPCA divulgado e t0 com a curva, "contando os dias a partir do primeiro dia útil depois do último mês realizado". E8.5 define os anos seguintes por dU contado de t0. Com t0 = 29/09/2026 (último IPCA: agosto), as leituras são:

- **(ii) só o ano corrente**, que é a adotada provisoriamente (leitura literal de E8.5 + E8.6): Inflação 2026 = IPCA jan–ago × F(83) − 1; Inflação 2027 = F(315)/F(64) − 1. Os 19 dias de curva entre 64 e 83 entram nos dois anos.
- **(i) a curva inteira contada do 1º dia útil após o último IPCA:** Inflação 2027 = F(334)/F(83) − 1, e assim por diante. É um único encadeamento, mas desloca a curva 19 dias úteis em relação a t0, contra E8.4.

Impacto de (i) em relação a (ii):

| Ano | Inflação | Juro real |
|---|---:|---:|
| 2027 | −9,8 bps | +9,9 bps |
| 2028 | +5,1 bps | −5,3 bps |
| 2029 | +2,7 bps | −2,7 bps |

Recomendação: **manter (ii)**, a leitura literal.

## Q13. IPCA-15 como alternativa para o intervalo (E8.6)

E8.6 prevê, "como alternativa parametrizável", cobrir o intervalo com o IPCA-15. A F2 implementa só a cobertura pela curva. O IPCA-15 tem coleta de meados de um mês a meados do seguinte, então é preciso decidir como encaixá-lo no mês civil. A série também precisa de coletor (SGS 7478) e da agenda do IBGE. Proposta: **adiar para a F3**, junto dos coletores, como parâmetro desligado por padrão e registrado no output.

## Respostas de 01/10/2026 (antes da F3)

- **Q1:** as curvas de inflação e de DI vêm da página da ANBIMA [curvas de juros fechamento](https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm). A resposta dada foi "04/09/2026"; a reconciliação mostrou depois que são da publicação de **29/09/2026** (Q8 revisada). Pendência técnica (sem decisão sua): os valores digitados não batem com a ETTJ colada em `Dashboard!C37:F57` (nem a inflação implícita, nem a Pré). O 1º passo da F3 é baixar a publicação da ANBIMA de 04/09/2026 e reconciliar as três coisas.
- **Q8:** resposta dada: as curvas digitadas são de 04/09/2026. **Superada** pela reconciliação (ver "Q8 reaberta" e as decisões da F3): são de 29/09/2026.
- **Q2:** a VAROS não tem licença de nenhum provedor; o CDS é copiado do Investing.com (links em `Dashboard!J9:J17`). O diagnóstico (viabilidade, API, termos de uso, robots, risco de bloqueio, alternativas) abre a F3 e precisa da sua aprovação antes de qualquer coletor de CDS. Fallback obrigatório: `data/manual/cds.csv`.
- **Q13:** implementar o IPCA-15 na F3, como parâmetro desligado por padrão. A forma de encaixar a coleta (meados a meados do mês) no mês civil será levada a você antes da implementação.

## Q8 reaberta, Q14 e Q15 (reconciliação com a ANBIMA, 01/10/2026)

Detalhes e prova: `docs/F3_RECONCILIACAO_ANBIMA.md` e `tests/test_reconciliacao_anbima.py`.

- **Q8 (reaberta):** as curvas digitadas são idênticas às da ANBIMA de **29/09/2026** (inflação: 21 de 21 valores; DI: 19 de 19, com o deslocamento da Q14). Nenhum outro dia disponível bate. Proposta: **t0 = 29/09/2026** e refazer a tabela da F2 (com t0 = 29/09: dU(2026) = 64; IPCA realizado até agosto; CDI até 28/09).
- **Q14:** na curva de DI, o vértice 378 ficou de fora e os seguintes subiram uma posição. Proposta:
  - (a) LEGADO uso (a): continua reproduzindo a planilha como está (é o teste de fidelidade);
  - (b) tabela da F2: mostrar os dois, a planilha como está e com a curva certa, e atribuir a diferença a "erro de digitação";
  - (c) pipeline diário: monta a curva direto da ANBIMA, sem o erro.
- **Q15:** composição das curvas a partir da ANBIMA, provisória:
  - LEGADO uso (b): repete o processo do operador. Inflação: 126 := 252 e 2646 := 2520. DI: 126 da Circular 3.361 e 252 a 2394 da ETTJ PREF (alinhada).
  - CORRIGIDO: só vértices publicados. Inflação: implícita de 252 a 2520. DI: ETTJ PREF de 252 a 2520 + Circular 3.361 abaixo de 252 (21, 42, 63, 126). A Circular 3.361 coincide com a ETTJ PREF nos vértices comuns (252, 504, 756…), então é a mesma curva.

## Decisões de 01/10/2026 (F3)

- **Q8:** t0 = 29/09/2026 para os inputs da planilha. A tabela da F2 é refeita com essa data, com uma etapa própria para o erro de colagem do DI.
- **Q14:** o LEGADO (a) continua reproduzindo a planilha como está. A tabela da F2 mostra o efeito do erro à parte. O pipeline diário monta a curva da ANBIMA sem o erro.
- **Q15:**
  - LEGADO (b): inflação 126 := 252 e 2646 := 2520; DI 126 da Circular 3.361 e 252 a 2394 da ETTJ PREF alinhada.
  - CORRIGIDO: só vértices publicados. Inflação 252–2520. DI = ETTJ PREF + Circular 3.361 abaixo de 252.
- **Q2:** sem coletor do Investing.com, vedado pelos termos (`docs/F3_DIAGNOSTICO_CDS.md`). Fonte de produção: `data/manual/cds.csv`, com validação de data, `stale` e alerta. Pedido de cotação à Cbonds (API dos índices CDS Brazil, histórico e exibição no site) preparado para a equipe enviar.
- **Q13:** Forma A (`docs/F3_PROPOSTA_IPCA15.md`), como parâmetro desligado por padrão.

## Notas da revisão da F3 (01/10/2026)

- **E6.13 (dado da planilha):** o IPCA de abril em `Dashboard!I23` é 0,43%, que é o de abril de **2025**; o de abril de 2026 (SGS 433) é 0,67%. Os demais meses de 2026 batem. A Selic de setembro (1,09%) não podia ser conhecida na data de atualização; a de setembro/2026 fechou em 1,08%. Outubro a dezembro são de 2025. O LEGADO (a) continua reproduzindo a planilha como está; o CORRIGIDO usa o realizado do BCB.
- **Q11 e Q12** foram atualizadas para t0 = 29/09/2026, a data da tabela publicada.

## Decisões de 02/10/2026 (início da F4)

- **Q3:** repositório e site **públicos** (GitHub Free). Tudo o que estiver no repositório fica visível: código, brutos, JSON e o CDS manual (ver Q17).
- **Q6:** LEGADO (b): m = último mês com IPCA divulgado até t0 (agenda do IBGE); trimestre = o que contém m; YTG = (12 − m)·21 nas três curvas; realizado (IPCA e Selic mensais, com ano) até m. Na virada do ano (m = dezembro do ano anterior ao de t0), o ano corrente do LEGADO sai indisponível com alerta, e os anos seguintes saem normais.
- **Q11:** convenção B confirmada. **Q12:** leitura (ii) confirmada.
- **Q4:** taxa de desconto por **composição**, (1 + DI)(1 + CDS) − 1, por ano civil, nos dois modos.

## Q16. CDS diário, gratuito e automático (registrado em 02/10/2026)

Pedido do usuário: atualizar o CDS todo dia, de graça e sem trabalho manual, de preferência a partir do Investing.com, que hoje se consulta sem conta.

O obstáculo não é técnico, é contratual. Os termos do Investing.com proíbem extração automatizada (§10(c)) e contornar medidas de acesso (§10(h)); o HTTP 403 a clientes automatizados é essa medida. Um robô que imite um navegador para passar pelo bloqueio, com ou sem login, viola os termos. Por isso não será construído. Sites que republicam o Investing herdam o problema e, em geral, só têm o 5A (`docs/F3_DIAGNOSTICO_CDS.md`).

Caminhos legítimos, em ordem:

1. **Autorização por escrito do Investing.com** (tools@investing.com) para coleta automatizada dos 9 vértices e uso interno. Com o aval, o coletor passa a ser permitido. Rascunho do e-mail em `docs/F4_PEDIDO_AUTORIZACAO_INVESTING.md`.
2. **Coleta manual assistida** (implementada na F4): um comando onde a pessoa cola os 9 valores vistos no site; ele valida e acrescenta as linhas em `data/manual/cds.csv`. Leva cerca de 30 segundos por dia, sem scraping.
3. **Trial da Cbonds** (cerca de 2 semanas): medir a série ICE/Cbonds contra a do Investing antes de decidir contratar.

## Q17. CDS do Investing.com num repositório público

Com a Q3 (repositório público), `data/manual/cds.csv` e o JSON publicado expõem valores copiados do Investing.com. A §14 dos termos veda exibir esses dados em site sem permissão. Precisa de parecer jurídico ou da autorização da Q16-1 antes da publicação (F5). Enquanto isso, o pipeline continua usando o arquivo manual normalmente.

## Decisões de 02/10/2026 (início da F5)

- **Q5:** fonte **Instrument Sans**; logo = a palavra "VAROS" em texto, nessa fonte (sem logo gráfico); **tema escuro** derivado da paleta dos gráficos:

  | Token | Cor |
  |---|---|
  | fundo | `#131313` |
  | superfície | `#1C1D1F` |
  | texto | `#E2E5EB` |
  | secundário | `#878D96` |
  | eixos | `#C6CAD2` |
  | séries | `#12D8B2`, `#43AF43`, `#239B84`, `#296055` |
  | ok (fonte atual) | `#43AF43` |
  | defasado | `#E0A526` (âmbar) |
  | erro | `#E5534B` (vermelho) |

- **Q17 (parcial):** o site mostra, ao lado de cada vértice do CDS, o link da aba do Investing.com, como em `Dashboard!J9:J17`. A pessoa abre a aba e pega o valor manualmente, como fazia na planilha. Linkar a página é livre; o link não muda a §14 dos termos, que veda exibir os valores sem permissão. Por isso o site tem uma chave única para esconder os valores de CDS (e a taxa de desconto, que depende deles) caso o jurídico peça, sem mexer no resto. Até lá, a decisão de ligar o Pages com os valores é da VAROS.

## Q18. CDI do SGS atrasado (regra operacional provisória, 02/10/2026)

O CORRIGIDO precisa do CDI diário (SGS 12) de 1º/jan até a véspera de t0 (Q11-B). Se o BCB ainda não tiver publicado os últimos dias quando o pipeline rodar, os dias que faltam **no fim** da série repetem a última taxa observada. O CDI só muda depois das reuniões do Copom, então o erro esperado é nulo ou muito pequeno. A fonte fica marcada no alerta `cdi_preenchido`. Um buraco no meio da série não é preenchido: bloqueia. Alternativa, se preferir: bloquear a publicação até o dado sair. A coleta manual assistida do CDS (Q16, item 2) está em `python -m curvas.cds_add`.

## Q19. Risco: a ANBIMA vai desligar a aba das curvas (registrado em 02/10/2026)

A página [curvas de juros fechamento](https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm) traz um aviso de 17/03/2026: em breve a aba será desligada, e as curvas de juros e de crédito ficarão exclusivamente no **ANBIMA Data**. O endpoint usado pelo coletor (`est-termo/CZ-down.asp`) pode deixar de existir sem aviso.

- **Enquanto funcionar:** nada muda. Se o download falhar, o pipeline usa o último dado válido com `stale` e alerta, e o modo de recuperação não publica dia sem curva.
- **Preparação:** levantar o acesso às curvas no ANBIMA Data (cadastro, API, termos de uso e se há custo) antes do desligamento. Trocar de fonte exige registro aqui (regra "não troque fontes sem documentar").
- **Alternativa para o DI:** taxas referenciais DI × Pré da B3 (E9). Seria troca de fonte, com decisão sua.

## Q17. Decisão final (02/10/2026)

O usuário decidiu publicar repositório e site com os valores de CDS: o site é uma ferramenta operacional, sem dado sensível. A ressalva dos termos do Investing.com (§14) fica registrada acima como risco conhecido e aceito. A chave `site.show_cds_values` / variável `OCULTAR_CDS` continua disponível, desligada por padrão, caso a decisão mude.
