# Instruções do projeto (Parte 1 do prompt original)

> Cópia da Parte 1 de `prompt_unico_curvas_varos.md`, lida no início do projeto em 01/10/2026. O arquivo original saiu do Desktop. A Parte 2 está em `docs/ESPECIFICACAO.md`, e as decisões tomadas desde então, em `OPEN_QUESTIONS.md`, que prevalecem sobre este texto quando o atualizam.

# PLATAFORMA DE CURVAS VAROS: prompt completo para o Claude Code

Este prompt é autossuficiente. Ele tem duas partes:

- **PARTE 1, Instruções:** o que construir, como e em que ordem.
- **PARTE 2, Especificação (E1 a E11):** como a planilha atual funciona, onde ela erra, a metodologia corrigida, as fontes de dados e os casos de teste.

Ao longo do texto, referências como "E8" apontam para as seções da Parte 2.

O único arquivo externo obrigatório é a planilha original, em `docs/legado/Query-Avila.xlsx`. A pasta `brand/`, com a identidade visual da VAROS, é opcional.

---

# PARTE 1: INSTRUÇÕES

## 1. Missão

Transformar uma planilha Excel, hoje atualizada manualmente, num sistema 100% Python composto por três partes:

1. um pipeline diário automatizado no GitHub Actions;
2. um motor de curvas testado;
3. um site estático gerado em Python, publicado no GitHub Pages com a identidade visual da VAROS.

A planilha converte curvas de mercado (DI futuro, inflação implícita e CDS Brasil) em premissas anuais de 2026 a 2036, que alimentam modelos de valuation.

**Regra de ouro: primeiro reproduza, depois corrija.**

- Não "melhore" fórmulas do legado por interpretação própria.
- Não troque fontes de dados sem documentar a troca.
- Não decida sozinho o que estiver marcado como decisão minha.

## 2. Hierarquia de verdade

| Modo | Fonte soberana |
|---|---|
| CORRIGIDO | Parte 2, seção E8 |
| LEGADO | Fórmulas reais da planilha, recalculadas (ver 3.3) |

A Parte 2 foi escrita a partir dos **valores** da planilha, sem acesso às fórmulas.

- Se uma fórmula real contradisser a Parte 2 no modo LEGADO, **a fórmula vence**. Documente a divergência.
- Os valores salvos no `.xlsx` são evidência, não gabarito.

## 3. F0: auditoria (sem código de implementação)

Nesta fase:

- **Pode:** escrever scripts descartáveis de análise em `scratch/`.
- **Não pode:** criar o motor, os coletores ou o site.
- **Primeiro passo:** salve a Parte 2 deste prompt em `docs/ESPECIFICACAO.md`. Ela será usada pela página de Metodologia do site.

### 3.1 Mapa da planilha

Mapeie:

- abas e blocos;
- inputs manuais e parâmetros (mês atual, trimestre, YTG, campos "<- Mudar");
- fórmulas e outputs;
- links;
- dependências entre abas e intervalos usados.

### 3.2 Inventário de fórmulas

Leia a planilha com `openpyxl` (`data_only=False`) e expanda as fórmulas compartilhadas.

Para cada bloco relevante, registre:

- a célula;
- a fórmula original;
- a forma matemática equivalente;
- as dependências;
- a finalidade;
- a relação com a Parte 2.

### 3.3 Recálculo de referência e regra de desempate

O `openpyxl` não recalcula fórmulas. Gere uma referência recalculada com:

```
soffice --headless --calc --convert-to xlsx --outdir scratch/recalc docs/legado/Query-Avila.xlsx
```

Depois compare três coisas:

1. os valores em cache no arquivo original;
2. os valores do arquivo recalculado;
3. a seção E10.

**Regra de desempate:** o valor recalculado prevalece. Toda divergência é registrada como `FORMULA_RECALC_REQUIRED` ou `SPEC_DIVERGENCE` antes de virar fixture.

(Decisão Q7: o recálculo de referência usa o motor Python `formulas`, sem LibreOffice.)

### 3.4 Confirmações obrigatórias

Para cada item, mostre a fórmula original e confirme a matemática.

1. **Acumulação diária.** Confirme se é recursiva, como descrito em E4.2. Confirme também o termo de realizado no dia 1 e a ordem em que as operações são aplicadas.
2. **Interpolação.** Confirme a interpolação linear nas taxas, em blocos de 126 dias. Confirme o comportamento antes do primeiro vértice e depois do último.
3. **Anualização do DI.** Verifique se ela existe (suspeita: `DI!E4`). Se existir, responda:
   - o que ela anualiza;
   - com quantos dias;
   - como depende do trimestre;
   - se vale só para o primeiro período;
   - se há lógica equivalente nas outras abas.

   Não generalize sem evidência.
4. **Taxas anuais.** Confirme os cortes em `YTG + 252·(n−1)` e as razões entre fatores (E4.4).
5. **CDS.** Confirme:
   - a conversão de bps para taxa;
   - o YTG manual;
   - o significado das colunas 2026 e YTG no Dashboard.
6. **Realizado.** Confirme a matriz "Usar" e identifique de qual célula ela depende.

### 3.5 Formato da entrega da F0

A resposta da F0 contém exatamente estas sete seções:

1. Estrutura encontrada
2. Fórmulas críticas confirmadas
3. Divergências entre a Parte 2 e a planilha
4. Problemas no `.xlsx` (cache, inputs, datas, rótulos)
5. Fixtures propostas
6. Decisões necessárias (só as que bloqueiam; ver seção 4)
7. Plano de F1 a F6

**Depois de entregar, pare e aguarde minha aprovação.**

## 4. Decisões que são minhas

Registre cada uma em `OPEN_QUESTIONS.md` e pergunte. Não assuma resposta.

1. **Curva de inflação.** Qual é a fonte e a data-base da curva usada hoje? Ela diverge da ETTJ ANBIMA (ver E6.4). Não substitua uma pela outra no modo LEGADO.
2. **Fonte do CDS.** Antes de escrever qualquer scraper, me entregue um diagnóstico com:
   - viabilidade técnica e estabilidade;
   - existência de API;
   - termos de uso e robots;
   - risco de bloqueio;
   - alternativas.

   Ordem de preferência: fonte licenciada, depois API pública permitida, depois fonte alternativa confiável. O fallback obrigatório é `data/manual/cds.csv`.
3. **Repositório público ou privado.** Verifique a política atual do GitHub Pages. Lembre que o site expõe os dados de qualquer forma.
4. **Convenção da taxa de desconto.** Soma DI + CDS, composição ou spread sobre a curva.
5. **Identidade visual**, caso `brand/` não exista: paleta, fontes, logo e referências.

O juro real **não** é uma pergunta: use E8.8. Também não pergunte nada que possa ser descoberto lendo os arquivos.

## 5. Stack (100% Python)

| Camada | Ferramenta |
|---|---|
| Linguagem | Python 3.12 |
| Ambiente | `uv` (com `pyproject.toml` e lockfile) |
| Qualidade | `ruff`, `mypy --strict` no `engine/`, `pytest`, `hypothesis` |
| Dados | `pandas`, `numpy`, `httpx` (com timeouts), `pydantic` v2 |
| Calendário | Feriados ANBIMA via `bizdays`, ou arquivo oficial versionado em `data/calendar/` (avalie e justifique a escolha) |
| Site | `jinja2` + `plotly` |
| Exportação | `openpyxl` |

Restrições:

- JavaScript só para interface: abas, alternância Corrigido/Legado e seleção de datas.
- Nenhuma regra de negócio no navegador. Todo número exibido é pré-calculado em Python.
- Nem Excel nem LibreOffice em runtime. O LibreOffice serve só para a auditoria e para gerar fixtures.

## 6. Arquitetura

```
/
├── pyproject.toml
├── src/curvas/
│   ├── config.py          # limites de alerta, tolerâncias, URLs
│   ├── models.py          # schemas pydantic
│   ├── calendar.py        # dias úteis ANBIMA
│   ├── fetch/             # só baixa e salva o bruto (b3_di, anbima_ettj, bcb_sgs, cds)
│   ├── normalize/         # bruto → inputs tipados
│   ├── validate/          # datas, nº de vértices, faixas plausíveis
│   ├── engine/            # funções puras, sem I/O
│   │   ├── curves.py      # interpolação linear e flat-forward, fatores
│   │   ├── legacy.py
│   │   ├── corrected.py
│   │   └── annual.py
│   ├── output/            # JSON, CSV, XLSX
│   ├── site/              # build do site + templates/
│   └── run.py             # fetch → validate → normalize → compute → compare → alerts → write → build
├── tests/                 # fixtures/, test_legacy, test_corrected, test_curves, test_fetch_* (sem rede)
├── data/
│   ├── raw/AAAA/MM/AAAA-MM-DD/   # brutos + manifest.json (URL, timestamp, hash, data econômica)
│   ├── curves/AAAA-MM-DD.json
│   ├── latest.json
│   ├── manual/cds.csv
│   └── calendar/
├── docs/                  # ESPECIFICACAO.md, legado/, schema.json
├── scratch/
├── OPEN_QUESTIONS.md
├── README.md
└── .github/workflows/     # tests.yml, daily.yml
```

**Retenção dos dados brutos:** guardar os últimos 90 dias soltos. Meses anteriores vão compactados em `data/raw/AAAA/MM.zip`. Nunca sobrescreva um bruto.

## 7. Datas

Cada execução tem **uma única** data-base, `as_of_date` (t0).

Cada fonte registra quatro datas distintas:

| Campo | Significado |
|---|---|
| `requested_date` | Data pedida à fonte |
| `source_date` | Data econômica do dado |
| `publication_date` | Quando a fonte publicou |
| `retrieved_at` | Quando o pipeline baixou |

Os dias úteis seguem o calendário ANBIMA. No modo CORRIGIDO, os anos são cortados em 31/12 pelo calendário real; **nunca** use "252 dias = 1 ano".

## 8. Modo LEGADO

O modo LEGADO tem **dois usos distintos**, que devem ficar explícitos no código e nos testes.

**(a) Validação.**
- Usa os inputs e parâmetros exatamente como estão na planilha: abas Inflação e DI em "Janeiro", YTG de 231 dias e YTG de 62 dias no CDS.
- Deve reproduzir a planilha recalculada com tolerância de 1e-8.
- Existe **só nos testes**.

**(b) Execução diária.**
- Usa as mesmas **fórmulas** do legado: interpolação linear, acumulação recursiva, anos de 252 dias e a anualização do DI, se ela for confirmada.
- Mês, trimestre, realizado e YTG são derivados de t0 e são **iguais nas três curvas**.
- Em resumo: o erro de método é preservado, o erro de operação não.

Em ambos os usos:

- Cada fórmula relevante tem um correspondente explícito em Python, com comentário indicando a célula de origem.
- A ordem das operações é a mesma da planilha.

## 9. Modo CORRIGIDO (padrão do site)

Implemente exatamente o que está em E8:

- fatores calculados a partir da curva spot;
- interpolação flat-forward;
- extrapolação pela forward do último segmento;
- cortes por ano civil;
- realizado de CDI via SGS;
- regra explícita e registrada para o IPCA ainda não divulgado;
- CDS com dois campos separados: `annualized_rate` e `remaining_period_accumulated`;
- juro real conforme E8.8.

Não crie correções além dessas. Se encontrar ambiguidade, registre em `OPEN_QUESTIONS.md` antes de decidir.

## 10. Testes obrigatórios

1. Todos os casos de E10, ajustados pela regra de desempate (3.3), com tolerância de 1e-8.
2. Reprodução completa do Dashboard no uso (a) do LEGADO.
3. Reprecificação: no modo CORRIGIDO, cada vértice é recuperado com erro menor que 1e-12.
4. Curva flat: LEGADO e CORRIGIDO dão o mesmo resultado.
5. Sanidade das curvas: fatores positivos, nenhum NaN e continuidade nos vértices.
6. Calendário: os dias úteis entre os cortes batem com o calendário ANBIMA.
7. Testes de propriedade (`hypothesis`) para a interpolação.
8. Coletores testados com respostas gravadas, sem acesso à rede.

As funções do `engine/` devem ser puras, determinísticas e tipadas. Cada docstring cita a seção da Parte 2 que a função implementa.

## 11. Saída JSON

O schema é definido em pydantic e exportado para `docs/schema.json`.

Blocos obrigatórios:

| Bloco | Conteúdo |
|---|---|
| `metadata` | `as_of_date`, versão do código, hash do commit |
| `sources` | Uma entrada por fonte |
| `inputs` | Inputs usados no cálculo |
| `curves` | Vértices e amostra da curva diária |
| `annual` | Resultados com `legacy` e `corrected` |
| `realized` | Dados realizados, sempre com mês **e ano** |
| `comparison` | Diferenças entre LEGADO e CORRIGIDO |
| `alerts` | Alertas da execução |

Cada fonte registra: `source`, `requested_date`, `source_date`, `publication_date`, `retrieved_at`, `stale`, `fallback_reason`.

## 12. Coleta, fallback e alertas

**Coleta.** Cada coletor tem:
- timeout;
- retry com backoff exponencial;
- validação de schema, data, número de vértices e faixa plausível;
- logging estruturado.

**Falha de fonte.**
- Use o último dado válido.
- Marque `stale: true` com a data real do dado.
- Gere um alerta.
- Nunca publique dado antigo como se fosse atual.

**Variação diária.** Se uma taxa anual variar acima de `max_daily_change_bps` (configurável), gere um alerta sem bloquear a publicação.

**Bloqueiam a publicação:**
- testes falhando;
- schema inválido;
- NaN na curva;
- fatores inválidos.

## 13. GitHub Actions

**`tests.yml`** roda `ruff`, `mypy` e `pytest` em todo push e todo PR.

**`daily.yml`**
- **Gatilhos:** `workflow_dispatch` e cron.
- **Sequência:** `uv` → testes → `python -m curvas.run` → validação → commit dos JSON e brutos → build do site → deploy no Pages.
- **Horário do cron:** só defina depois de checar os horários de publicação da B3, ANBIMA e BCB (em BRT, considerando feriados).
- **Dia não útil ANBIMA:** o workflow encerra sem publicar.
- **Documentação:** registre a escolha do horário no README.
- **Credenciais:** apenas em GitHub Secrets, com o nome de cada uma documentado.

## 14. Site

| Página | Conteúdo |
|---|---|
| **Visão geral** | Data-base; tabela ano × {DI, Inflação, CDS, Juro real} de 2026 a 2036; alternância Corrigido/Legado; status de cada fonte (verde = atual, amarelo = defasado) com a data real do dado; alertas |
| **Curvas** | Vértices (pontos) e curva interpolada (linha), em taxa e em fator; comparação com uma data-base anterior |
| **Realizado** | IPCA e CDI mensais com mês e ano; acumulado do ano; regra aplicada ao IPCA não divulgado |
| **Histórico** | Evolução de cada taxa anual ao longo das datas-base |
| **Metodologia** | `docs/ESPECIFICACAO.md` renderizado, com explicação objetiva de LEGADO × CORRIGIDO |

Também:
- **Downloads:** CSV e XLSX do dia, gerados no build. O XLSX segue o layout do Dashboard original e contém valores, sem fórmulas.
- **Identidade visual:** tokens CSS centralizados a partir de `brand/`. Se `brand/` não existir, pergunte; não invente.
- **Qualidade:** layout responsivo, bom contraste e densidade de informação adequada para leitura financeira.

## 15. Fases

| Fase | Escopo | Saída obrigatória |
|---|---|---|
| F0 | Auditoria (seção 3) | Relatório no formato 3.5; **parar** |
| F1 | `curves.py`, `legacy.py`, `annual.py`, fixtures e testes | Uso (a) do LEGADO passando em todos os testes |
| F2 | `corrected.py` e testes | Tabela LEGADO × CORRIGIDO (ver abaixo) |
| F3 | Calendário e coletores | Testes com respostas gravadas; diagnóstico do CDS aprovado |
| F4 | `run.py`, JSON, stale, alertas e Actions | Execução manual ponta a ponta |
| F5 | Site e exportações | Site publicado |
| F6 | README | Documentação de operação completa |

**Tabela da F2.**
- Colunas: DI, Inflação, CDS e Juro real, cada uma com valor LEGADO, valor CORRIGIDO e diferença em bps, para os inputs da planilha.
- Para cada diferença, indique a causa: interpolação, acumulação, calendário, corte em 31/12, realizado, anualização ou CDS.
- Não julgue qual metodologia é "melhor".

**Conteúdo do README (F6).**
- Arquitetura e instalação.
- Execução local e manual.
- Schema e fontes.
- Secrets e política de stale.
- Horário do cron.
- Metodologias.
- Troubleshooting e manutenção.

**Regras entre fases:**
- Não avance se houver decisão minha pendente.
- Ao fim de cada fase, responda neste formato:

```
FASE X: CONCLUÍDA
Testes: N passed / M failed
Decisões tomadas: ...
Divergências: ...
Arquivos criados/alterados: ...
Bloqueios para a próxima fase: ...
```

## 16. Critérios de aceite

1. Todos os testes passam, sem nenhuma dependência de Excel.
2. O LEGADO (a) reproduz a planilha recalculada.
3. O CORRIGIDO reprecifica os vértices com erro menor que 1e-12.
4. Nenhum fallback acontece em silêncio.
5. O cron e a execução manual funcionam.
6. O site consome `latest.json`, alterna os modos, mostra o histórico, exporta CSV e XLSX e funciona em desktop e mobile.
7. Mesmos `as_of_date`, brutos e configuração produzem exatamente o mesmo resultado.
