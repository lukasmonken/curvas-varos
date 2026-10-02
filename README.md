# Plataforma de Curvas VAROS

Converte as curvas de mercado (DI, inflação implícita e CDS Brasil) em premissas anuais de 11 anos civis a partir de t0 (hoje, 2026 a 2036), em dois modos: **LEGADO** (as fórmulas da planilha antiga) e **CORRIGIDO** (metodologia da especificação, E8). Um workflow diário do GitHub Actions coleta as fontes públicas, calcula os dois modos, grava os JSON em `data/` e publica um site estático no GitHub Pages. O CDS é registrado à mão, uma vez por dia útil.

- Instruções do projeto: [docs/INSTRUCOES.md](docs/INSTRUCOES.md) · Especificação: [docs/ESPECIFICACAO.md](docs/ESPECIFICACAO.md)
- Decisões e pendências (Q1–Q19): [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). Quando atualiza as instruções, prevalece.
- Auditoria da planilha (F0): [docs/F0_AUDITORIA.md](docs/F0_AUDITORIA.md) · LEGADO × CORRIGIDO (F2): [docs/F2_LEGADO_X_CORRIGIDO.md](docs/F2_LEGADO_X_CORRIGIDO.md) e [docs/f2_legado_x_corrigido.csv](docs/f2_legado_x_corrigido.csv)
- CDS e fontes (F3/F4): [docs/F3_DIAGNOSTICO_CDS.md](docs/F3_DIAGNOSTICO_CDS.md) · [docs/F3_RECONCILIACAO_ANBIMA.md](docs/F3_RECONCILIACAO_ANBIMA.md) · [docs/F3_PROPOSTA_IPCA15.md](docs/F3_PROPOSTA_IPCA15.md) · [docs/F3_PEDIDO_COTACAO_CBONDS.md](docs/F3_PEDIDO_COTACAO_CBONDS.md) · [docs/F4_PEDIDO_AUTORIZACAO_INVESTING.md](docs/F4_PEDIDO_AUTORIZACAO_INVESTING.md)
- Schema da saída: [docs/schema.json](docs/schema.json)

Seções: [1. Arquitetura e instalação](#1-arquitetura-e-instalação) · [2. Execução local e manual](#2-execução-local-e-manual) · [3. Schema e fontes](#3-schema-e-fontes) · [4. Secrets e política de stale](#4-secrets-e-política-de-stale) · [5. Horário do cron e operação diária](#5-horário-do-cron-e-operação-diária) · [6. Metodologias](#6-metodologias) · [7. Troubleshooting e manutenção](#7-troubleshooting-e-manutenção) · [8. Configuração inicial do repositório](#8-configuração-inicial-do-repositório-uma-vez) · [9. Cuidados](#9-cuidados)

## 1. Arquitetura e instalação

### Fluxo

```
ANBIMA (ETTJ) ──┐
BCB (SGS) ──────┼── coleta + validação ──> data/raw/  (brutos imutáveis + manifest.json)
IBGE (agenda) ──┘                                │
data/manual/cds.csv  (CDS manual) ──────────────┤
data/calendar/       (feriados ANBIMA) ─────────┤
                                                 v
             normalização -> motor (LEGADO e CORRIGIDO) -> data/curves/AAAA-MM-DD.json
                                                           data/latest.json
                                                                 │
                                     curvas.site.build -> site/ -> GitHub Pages
```

Uma execução de `python -m curvas.run`, passo a passo:

1. **Calendário.** Carrega os feriados ANBIMA. Recusa t0 que não seja dia útil ou que esteja no futuro. Sem `--as-of`, t0 = hoje em Brasília.
2. **Coleta.** Para cada fonte: baixa, interpreta e valida; só então grava o bruto em `data/raw/`. Resposta inválida não é gravada. Depois relê o bruto gravado de t0. Sem bruto válido de t0, procura o último bruto válido nos 60 dias corridos anteriores e marca a fonte como defasada (`stale`). Sem nenhum, bloqueia.
3. **CDS manual.** Lê `data/manual/cds.csv` e escolhe o último conjunto completo com data ≤ t0.
4. **Cálculo.** Monta os inputs dos dois modos e roda o motor (funções puras, sem I/O).
5. **Saída.** Monta o JSON, acrescenta os alertas de variação diária contra a saída do dia útil anterior e revalida o schema inteiro. Grava `data/curves/AAAA-MM-DD.json` e, se t0 for ≥ à data atual de `data/latest.json`, também o `latest.json` (ele nunca regride).
6. **Retenção.** Só em execução online: meses de brutos com mais de 90 dias viram zip.

O pipeline não gera o site. O build é outro comando (`curvas.site.build`), que o workflow roda depois do commit dos dados.

### Módulos (`src/curvas/`)

| Módulo | Papel |
|---|---|
| `run.py` | Orquestrador do pipeline e CLI (`--as-of`, `--today`, `--offline`, `--ipca15`, `--catch-up`) |
| `config.py` | URLs, timeouts e retry, séries do SGS, faixas plausíveis, limite do alerta diário, chave do CDS no site, início do pipeline |
| `models.py` | Schemas pydantic da saída (`RunOutput`, versão 1.1) |
| `schema.py` | CLI `export` (gera `docs/schema.json`) e `validate` |
| `calendar.py` | Calendário ANBIMA (`data/calendar/feriados_anbima.csv`), contagem de dias úteis em [a, b) |
| `logs.py` | Log estruturado: uma linha JSON por evento, em stderr |
| `cds_add.py` | CLI de registro do CDS manual |
| `fetch/` | `http.py` (cliente com retry), `sources.py` (só baixa bytes), `raw.py` (brutos imutáveis, manifesto, zip mensal) |
| `validate/checks.py` | Validação da ETTJ da ANBIMA |
| `normalize/` | Parsers da ANBIMA, do SGS, do IBGE e do CDS manual; montagem dos inputs do CORRIGIDO e do LEGADO |
| `engine/` | Motor puro: `curves.py`, `annual.py`, `legacy.py`, `corrected.py` e `attribution.py` (cascata da tabela da F2) |
| `output/` | `json_out.py` (monta a saída e os alertas diários), `csv_out.py`, `xlsx_out.py` e `comparacao.py` (tabela da F2) |
| `site/` | `build.py` (CLI do site), `view.py` (textos), `charts.py` (Plotly), `spec_doc.py` (especificação em HTML), `templates/` e `static/` |

Camadas: `fetch` só importa `config` e `httpx`; `engine` só importa a si mesmo; `site` lê `models`, `output` e `calendar` e nunca importa `fetch` nem `run`.

### Pastas do repositório

| Pasta | Conteúdo | No git |
|---|---|---|
| `src/curvas/` | Pacote (37 arquivos `.py`) | sim |
| `tests/` e `tests/fixtures/` | 411 testes; respostas gravadas (`f2/`, `f3/anbima/`), CDS congelado (`f4/`), dados congelados do site (`f5/data/`), fixtures do LEGADO (`legacy/`) | sim |
| `data/` | Brutos, saídas, CDS manual e calendário (seção 3) | sim |
| `docs/` | Instruções, especificação, relatórios das fases e `schema.json` | sim |
| `docs/legado/` | Planilha legada interna, só na máquina local | não |
| `tools/` | Scripts offline de manutenção (seção 7) | sim |
| `brand/` | `paleta-graficos.png`, origem dos tokens de cor (Q5) | sim |
| `scratch/` | Só `scratch/*.py` (scripts da auditoria F0, que leem a planilha local) | parcial |
| `site/` | Saída do build | não |

### Dependências (`pyproject.toml`, versões travadas em `uv.lock`)

| Grupo | Pacotes | Quando |
|---|---|---|
| runtime | httpx, pydantic, jinja2, plotly, openpyxl, markdown-it-py, numpy, pandas | sempre |
| `dev` (padrão) | pytest, hypothesis, mypy, ruff, bizdays | testes e checks; o bizdays só confere o calendário |
| `tools` | formulas, xlrd | só os scripts de `tools/`; nunca em runtime |

numpy e pandas estão declarados, mas nenhum arquivo do projeto os importa: hoje só chegam como dependência do bizdays.

Python ≥ 3.12. O CI usa 3.12; o mypy confere a semântica de 3.12 em qualquer versão local. O pacote só funciona a partir do checkout (os caminhos de `data/` e `docs/` vêm da posição de `src/curvas`), e o `uv sync` o instala em modo editável.

### Instalação

O projeto usa o [uv](https://docs.astral.sh/uv/). Para não instalar nada no sistema, ponha o uv num ambiente virtual descartável dentro de `scratch/`, que o git ignora:

```bash
python3 -m venv scratch/.venv
scratch/.venv/bin/pip install uv
alias uv="$PWD/scratch/.venv/bin/uv"
```

O `alias` vale só para o terminal aberto; sem ele, troque `uv` por `scratch/.venv/bin/uv` nos comandos deste README. Depois, na raiz do repositório:

```bash
uv sync
uv run pytest -q
```

- O `uv sync` cria `.venv/` com o runtime e o grupo `dev`. O primeiro precisa de rede (PyPI).
- O uv usa um Python ≥ 3.12 já instalado; se não achar nenhum, baixa um para a pasta do usuário.
- O grupo `tools` só entra com `uv sync --group tools`. Um `uv sync` puro depois disso remove formulas e xlrd; `uv run --group tools ...` os traz de volta.

## 2. Execução local e manual

Todo comando abaixo roda na raiz do repositório. Os que escrevem em `data/`, `docs/` ou `tests/fixtures/` alteram arquivos versionados: confira o diff no GitHub Desktop antes de commitar, ou experimente numa cópia (fim desta seção).

### Testes e checks (os mesmos do CI)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
CI=true uv run pytest -q
```

- `CI=true` deixa o hypothesis determinístico, como no CI. Sem ele, os exemplos são aleatórios; use-o para reproduzir uma falha do CI.
- Nenhum teste acessa a rede: coletores e pipeline usam respostas gravadas.
- Resultado esperado: `411 passed` com a planilha local em `docs/legado/Query-Avila.xlsx`; sem ela (clone limpo e CI), `409 passed, 2 skipped`, com o motivo "planilha fora do repositório (confidencial)".
- Alguns testes leem arquivos de produção: `data/manual/cds.csv`, `data/calendar/*`, `docs/schema.json`, `docs/F2_LEGADO_X_CORRIGIDO.md`, `docs/f2_legado_x_corrigido.csv` e `docs/ESPECIFICACAO.md`. Um `cds.csv` quebrado reprova a suíte e, com ela, o daily.

| Arquivo | Cobre |
|---|---|
| `test_legacy.py` | LEGADO uso (a) contra a planilha recalculada |
| `test_e10.py` | Casos E10 |
| `test_corrected.py`, `test_corrected_inputs.py` | Reprecificação (< 1e-12), flat-forward, curva flat, sanidade |
| `test_curves.py`, `test_annual.py` | Propriedades com hypothesis |
| `test_calendar.py` | Calendário dia a dia contra o bizdays até 2099 |
| `test_fetch.py`, `test_run.py` | Retry, brutos imutáveis, pipeline ponta a ponta sem rede, stale, bloqueios, recuperação, zip, schema |
| `test_anbima.py`, `test_normalize.py`, `test_cds_manual.py`, `test_cdi_monthly.py`, `test_reconciliacao_anbima.py` | Parsers e regras das fontes |
| `test_attribution.py` | Cascata da F2 e tabela publicada em dia |
| `test_exports.py`, `test_site.py` | CSV, XLSX, páginas, links, Q17, determinismo |

### Pipeline: `python -m curvas.run`

```bash
uv run python -m curvas.run --catch-up
uv run python -m curvas.run --as-of 2026-10-01
uv run python -m curvas.run --as-of 2026-10-01 --offline
```

| Opção | Efeito |
|---|---|
| `--as-of AAAA-MM-DD` | t0. Sem ela, t0 = hoje em Brasília (UTC−3 fixo no código; a variável `TZ` não muda nada) |
| `--today AAAA-MM-DD` | Simula a data de hoje |
| `--offline` | Não acessa a rede: usa só os brutos já gravados, não grava brutos e não compacta meses. Reproduz o JSON publicado byte a byte, exceto `metadata.git_commit` |
| `--catch-up` | Modo do workflow: processa os dias pendentes da janela de 5 dias úteis (seção 5). Ignora `--as-of` em silêncio |
| `--ipca15` | Forma A do IPCA-15 (Q13), desligada por padrão. Muda só o CORRIGIDO do ano corrente. O daily nunca a usa |

| Saída | Código | Quando |
|---|---|---|
| `Publicado: t0 = AAAA-MM-DD, N alerta(s), <arquivo>` | 0 | Dia publicado |
| `Sem publicação: DD/MM/AAAA não é dia útil ANBIMA` | 0 | Sem `--as-of`, em dia não útil |
| `Pendente: AAAA-MM-DD: ETTJ da ANBIMA de DD/MM/AAAA ainda não publicada` | 0 | Só no `--catch-up`, para t0 ≥ hoje |
| `Nada pendente.` | 0 | Só no `--catch-up` |
| `BLOQUEADO: <motivo>` (stderr) | 1 | Dia bloqueado; no `--catch-up`, uma linha por dia (`BLOQUEADO: AAAA-MM-DD: <motivo>`) e código 1 se algum bloqueou, mesmo com outros publicados |
| erro do argparse (ex.: `--as-of 2026-13-01`) | 2 | Argumento inválido |

- O log de cada evento sai em stderr, em JSON. O resumo legível vai para stdout.
- Se a variável `GITHUB_OUTPUT` existir, o comando escreve nela `published=true|false` e `as_of` (a data publicada mais recente, ou vazio). É o que o workflow usa.
- `git_commit` é o HEAD, com `-dirty` se houver alteração fora de `data/`. Commite o código antes de gerar saídas que vão para o repositório.
- **`--as-of` (e o run sem opções) publica mesmo sem a ETTJ do dia:** usa a do último dia válido, com `stale` e alerta, e atualiza `latest.json`. Só o `--catch-up` exige a curva do dia. Não rode `--as-of` com a data de hoje antes de a ANBIMA publicar.
- Uma execução online de um dia já coletado acrescenta entradas ao manifesto e pode criar arquivos `.v2`, `.v3`. Para reproduzir um dia, use `--offline`.
- **`--catch-up --offline` não é offline:** o catch-up roda sem cliente HTTP, cada fonte falha com `FetchError: sem cliente HTTP` e cai no bruto do próprio dia (alerta `fonte_bruto_do_dia`); dia sem bruto bloqueia. Para refazer sem rede, use `--as-of D --offline`, dia a dia.

### CDS: entrada manual diária

Não há fonte gratuita que permita coleta automática (`docs/F3_DIAGNOSTICO_CDS.md`, Q16). A coleta é manual, como na planilha:

1. Uma vez por dia útil, alguém abre a página **Coleta do CDS** do site, que traz o link da aba do Investing.com de cada vértice (como `Dashboard!J9:J17`), e lê os 9 fechamentos.
2. Registra os valores de uma destas formas:
   - **Pelo navegador** (precisa de acesso de escrita ao repositório): aba Actions → **cds** → *Run workflow*, branch `main`, com `data` (AAAA-MM-DD), `valores` (os 9 números separados por espaço) e `por` (nome, sem vírgula). O workflow grava com o `cds_add`, commita `data/manual/cds.csv` com `[skip ci]` e dispara o **daily** em modo de recuperação.
   - **Pela linha de comando:**

     ```bash
     uv run python -m curvas.cds_add --data 2026-10-01 --por "Nome" --valores "45,67 54,35 67,89 87,28 109,84 130,71 171,71 213,22 245,59"
     ```

     Sem `--valores`, o comando pergunta um por um (`CDS 6M (bps):` … `CDS 20A (bps):`); um valor inválido aborta e é preciso recomeçar do 6M. Depois, no GitHub Desktop: *Fetch origin* / *Pull* (o bot commita `data/` todo dia), commit de `data/manual/cds.csv` e *Push*. O push não dispara o daily: a refação fica para o próximo cron ou para um daily manual com `as_of` vazio.
3. A recuperação seguinte refaz a data-base cujo CDS foi lançado ou corrigido, se ela ainda estiver na janela de 5 dias úteis da ANBIMA. Fora da janela, o registro fica em `cds.csv`, mas a saída publicada daquele dia não muda (seção 7 mostra como forçar).

Regras do registro:

- Ordem fixa 6M 1A 2A 3A 4A 5A 7A 10A 20A, em bps, separados por **espaço**, com ponto ou vírgula decimal. Separar por vírgula (`45.67,54.35`) ou usar milhar (`1.045,67`) falha.
- Validações: exatamente 9 valores; 0 < bps < 3000; data de referência dia útil ANBIMA e não posterior ao preenchimento; nome e fonte sem vírgula. O arquivo inteiro é revalidado e gravado de forma atômica.
- Sucesso: `ok: 9 vértices de DD/MM/AAAA em <arquivo>`, código 0. Erro: `NADA GRAVADO: <motivo>` em stderr, código 1, arquivo intacto.
- Para corrigir um dia, registre os 9 valores de novo: vale a linha com `preenchido_em` mais recente. A saída ganha um alerta "CDS <vértice> de DD/MM/AAAA corrigido (linha N)" por vértice. Uma correção no mesmo segundo da gravação anterior é recusada; espere 1 s.
- Sem CDS do dia, o pipeline usa o último conjunto completo, marca `stale` e gera o alerta "CDS defasado: usando DD/MM/AAAA para t0 = DD/MM/AAAA".
- Opções: `--fonte` (padrão `Investing.com (cópia manual)`) e `--arquivo` (padrão `data/manual/cds.csv`). Datas anteriores a 29/09/2026 são aceitas, mas a recuperação nunca as processa.

### Site

```bash
uv run python -m curvas.site.build --out site
uv run python -m curvas.site.build --out site --ocultar-cds
uv run python -m http.server 8799 --bind 127.0.0.1 -d site
```

Depois do terceiro comando, abra `http://127.0.0.1:8799/` (Ctrl-C encerra; qualquer porta livre serve). O build lê `--dados` (padrão `data/`: `latest.json` e `curves/*.json`, todos validados contra o schema), apaga do `--out` o que um build anterior deixou com os mesmos nomes e grava de novo. Dois builds seguidos dão os mesmos bytes. **Nunca aponte `--out` para `data/`** nem para a pasta de `--dados`: o build apaga `latest.json` e `curves/` antes de ler.

Site estático com Jinja2 e Plotly auto-hospedado. Todo número sai pronto do JSON; o JavaScript só alterna abas, modo (CORRIGIDO/LEGADO) e datas, e guarda o modo escolhido no navegador. A única dependência externa é a fonte Instrument Sans, do Google Fonts.

| Página | Conteúdo |
|---|---|
| Visão geral | Taxas anuais nos dois modos, CORRIGIDO − LEGADO em bps, alertas, status de cada fonte (Atual/Defasado, com a data real e o motivo) e downloads |
| Curvas | Vértices e curva interpolada, em taxa e em fator, com comparação a outra data-base |
| Realizado | IPCA e CDI mensais, acumulados do ano, regra do IPCA não divulgado e Selic mensal do LEGADO |
| Histórico | Cada taxa anual ao longo das datas-base |
| Metodologia | LEGADO × CORRIGIDO e a especificação renderizada (`docs/ESPECIFICACAO.md`) |
| Coleta do CDS | Link da aba do Investing.com de cada vértice e como registrar os valores |

O link "Abrir o formulário" do workflow cds só aparece quando o build roda no GitHub (variáveis `GITHUB_SERVER_URL` e `GITHUB_REPOSITORY`). Downloads, gerados no build:

- `downloads/curvas-AAAA-MM-DD.csv`: tabela anual do dia nos dois modos, em decimal ao ano;
- `downloads/curvas-AAAA-MM-DD.xlsx`: layout do Dashboard da planilha com o LEGADO do dia, mais as abas Corrigido e Fontes, só valores;
- `downloads/historico.csv`: a tabela anual de todas as datas-base;
- com o CDS visível, também `latest.json` e `curves/AAAA-MM-DD.json` na raiz do site.

Cores e fonte ficam em `src/curvas/site/static/tokens.css` (Q5). `--ocultar-cds` é a chave da Q17 (seção 4).

### Schema

```bash
uv run python -m curvas.schema validate data/latest.json data/curves/*.json
uv run python -m curvas.schema export
```

- `validate` imprime `ok: <arquivo> (t0 = AAAA-MM-DD)` por arquivo, ou `INVÁLIDO: <arquivo>: <erro>` em stderr e código 1. É o passo de validação do daily.
- `export` reescreve `docs/schema.json`. Rode só quando `src/curvas/models.py` mudar: o teste `test_schema_publicado_atualizado` falha se o arquivo ficar desatualizado.

### Execução manual no GitHub Actions

| Workflow | Como | O que roda |
|---|---|---|
| **daily**, recuperação | Actions → daily → *Run workflow*, branch `main`, `as_of` vazio | `uv run python -m curvas.run --catch-up` |
| **daily**, um dia | Mesmo caminho, `as_of` = AAAA-MM-DD | `uv run python -m curvas.run --as-of "$AS_OF"` (publica mesmo com a ETTJ defasada) |
| **cds** | Actions → cds → *Run workflow*, branch `main`: `data`, `valores`, `por` | `cds_add`, commit `cds: <data> por <nome> [skip ci]`, push e `gh workflow run daily.yml` |

Os inputs chegam aos comandos só por variáveis de ambiente, nunca interpolados no script. Rodar num branch que não seja o `main` grava nesse branch.

### Experimentar sem mexer em `data/`

O CLI do pipeline não tem opção de pasta de dados: a raiz vem da posição de `src/curvas`. Para testar sem alterar o repositório, use uma cópia e o Python do `.venv` com `PYTHONPATH` apontando para a cópia:

```bash
REPO=$PWD
rsync -a --exclude .venv --exclude scratch --exclude .git "$REPO/" "$REPO-copia/"
cd "$REPO-copia"
PYTHONPATH=$PWD/src "$REPO/.venv/bin/python" -m curvas.run --as-of 2026-10-01 --offline
PYTHONPATH=$PWD/src "$REPO/.venv/bin/python" -m curvas.run --as-of 2026-10-01 --offline --ipca15
PYTHONPATH=$PWD/src "$REPO/.venv/bin/python" -m curvas.site.build --out site
cd "$REPO"
```

Na cópia sem `.git`, `metadata.git_commit` sai `null`. Para recomeçar do zero, apague a pasta da cópia.

## 3. Schema e fontes

### Saída: `RunOutput` (schema 1.1)

Arquivos: `data/curves/AAAA-MM-DD.json` (um por data-base, regravado a cada execução) e `data/latest.json` (a data-base mais recente). Todo modelo recusa campo desconhecido, NaN e infinito; fatores precisam ser > 0.

| Bloco | Conteúdo |
|---|---|
| `metadata` | `as_of_date` (t0 único), `code_version`, `git_commit`, `schema_version`, `default_mode` (`corrected`) |
| `sources` | 7 registros: `anbima_ettj`, `bcb_sgs_12`, `bcb_sgs_433`, `bcb_sgs_4390`, `bcb_sgs_7478`, `ibge_calendario`, `cds_manual`. Cada um com `requested_date`, `source_date`, `publication_date`, `retrieved_at`, `stale`, `fallback_reason`, `url`, `sha256` e `raw_path` (relativo a `data/raw`) |
| `inputs` | `legacy`: mês e trimestre do LEGADO, YTG, curvas de 19 vértices e CDS de 9; `corrected`: dias úteis até cada 31/12, intervalo da inflação, interpolação, regra do intervalo (`curve` ou `ipca15_same_month`), fatores realizados |
| `curves` | `di`, `inflation` e `cds`, cada uma com vértices e amostra (127 prazos de 1 a 2646 d.u.; o CDS acrescenta 5040) nos dois modos |
| `annual` | 11 linhas por modo com `di`, `inflation`, `cds`, `real` e `discount`; `corrected_cds_current_year`; `legacy_ytg` |
| `realized` | IPCA mensal (com data de divulgação), IPCA do ano, regra E8.6, IPCA-15 usado, fator do CDI de 1º/jan até a véspera de t0, CDI mensal (calculado do SGS 12; o mês de t0 entra parcial) e Selic mensal do LEGADO |
| `comparison` | Por ano: (CORRIGIDO − LEGADO) × 10.000, em bps |
| `alerts` | `level` (`info`, `warning`; o schema aceita `error`, que hoje nenhum código emite), `code`, `message`, `source` |

| Campo | Unidade |
|---|---|
| `annual.*`, `Vertex.rate`, `CurvePoint.rate` | decimal ao ano, base 252 (0.1397 = 13,97% a.a.) |
| `CurvePoint.factor`, `realized.cdi.factor` | fator acumulado |
| `Vertex.days`, `CurvePoint.days` | dias úteis a partir de t0 |
| `inputs.legacy.*_curve_pct` | % ao ano, como na planilha |
| `inputs.legacy.cds_bps`, `comparison.*_bps` | bps |
| `realized.*.value_pct` | % no mês |
| `realized.ipca_ytd` | decimal acumulado |
| `corrected_cds_current_year.annualized_rate` / `remaining_period_accumulated` | decimal ao ano / decimal acumulado de t0 a 31/12 |
| datas | ISO 8601; `retrieved_at` das fontes baixadas em UTC; o CDS manual com fuso −03:00 |

`null` tem dois sentidos. Em `annual` e `comparison`, é valor indisponível do LEGADO e sempre vem com alerta (`legado_virada_do_ano` ou `legado_indisponivel`). Nos demais campos, é "não informado" ou "não se aplica": `publication_date` de fontes que não a informam, `inputs.legacy.month` antes do primeiro IPCA do ano, `ipca15_used` sem a Forma A.

**Mudança de schema:** o daily e o build validam todos os `data/curves/*.json`, inclusive os antigos. Campo novo precisa de valor padrão (ou as saídas antigas precisam ser regeneradas offline). Depois de mexer em `models.py`: suba `SCHEMA_VERSION`, rode `uv run python -m curvas.schema export` e commite `docs/schema.json`.

### Fontes

| Fonte | Endpoint | Período pedido | Uso |
|---|---|---|---|
| `anbima_ettj` | POST `https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp` com `Idioma=PT`, `saida=csv`, `Dt_Ref=DD/MM/AAAA` | t0 | Curvas de DI e inflação implícita (Q15) |
| `bcb_sgs_12` | GET `https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados` com `formato=json`, `dataInicial`, `dataFinal` | 1º/jan do ano de t0 até t0 | CDI diário: realizado do CORRIGIDO (até a véspera de t0, Q11-B) e CDI mensal |
| `bcb_sgs_433` | idem, série 433 | 1º/jan do ano anterior a 31/12 do ano de t0 | IPCA mensal: realizado dos dois modos; define m e o trimestre do LEGADO (Q6) |
| `bcb_sgs_4390` | idem, série 4390 | idem | Selic mensal: só o LEGADO (meses 1..m) |
| `bcb_sgs_7478` | idem, série 7478 | idem | IPCA-15: só com `--ipca15`. É baixado e validado mesmo assim |
| `ibge_calendario` | GET `https://servicodados.ibge.gov.br/api/v3/calendario/` com `de`, `ate` (MM-DD-AAAA) e `qtd=1000` | 1º/jan do ano anterior a 31/12 do ano seguinte | Datas de divulgação do IPCA e do IPCA-15 |
| `cds_manual` | `data/manual/cds.csv` | último conjunto completo ≤ t0 | CDS (9 vértices) |
| calendário | `data/calendar/feriados_anbima.csv` | 2001 a 2099 | Dias úteis, t0 e janela |

Todas são públicas e sem autenticação. HTTP: timeout de 10 s (conexão) e 60 s (leitura), 4 tentativas com espera de 2, 4 e 8 s (teto de 30 s, respeitando `Retry-After`), repetição em 408, 429, 500, 502, 503, 504 e erro de rede; outro 4xx falha na hora.

**ANBIMA (ETTJ).**
- CSV latin-1, `;`, vírgula decimal, em quatro seções (parâmetros de Svensson; ETTJ IPCA, PREF e Inflação Implícita; PREFIXADOS Circular 3.361; erro título a título).
- Corpo vazio = ainda não publicada. HTML com status 200 = erro de formato.
- A página pública só guarda os últimos 5 dias úteis, por isso o bruto precisa ser gravado todo dia útil: um dia não coletado não pode ser reconstruído depois.
- Validação: data do arquivo = data pedida; vértices crescentes; PREF e implícita com ≥ 15 vértices na grade de 126 em 126; Circular 3.361 igual à PREF nos vértices comuns; faixas PREF/Circular [0, 60], real [−5, 25] e implícita [−5, 40] % a.a.; relação de Fisher com tolerância de 0,002 p.p.
- A ETTJ IPCA (real) só entra na validação.

**BCB (SGS).**
- A resposta só é aceita se for JSON; HTML com status 200 ("requisição rejeitada") conta como falha transitória.
- Checagem: série não vazia e valores na faixa (CDI 0 a 0,2% a.d.; IPCA e IPCA-15 −3 a 5% no mês; Selic mensal 0 a 5%). Séries mensais datadas no 1º dia do mês, sem repetição nem desordem.
- `source_date` = última observação ≤ t0. No SGS 433, vira o mês do último IPCA usado, e `publication_date` a divulgação dele pelo IBGE. `source_date` = t0 no SGS 12 não significa que o CDI de t0 entrou: o realizado vai até a véspera.
- As séries 4391 (CDI mensal) e 11 (Selic diária) estão declaradas em `config.py`, mas não são baixadas.

**IBGE (agenda).**
- Filtra pelo título exato do IPCA e do IPCA-15 e usa só a data de `data_divulgacao` (a hora da API não é a hora real).
- Resposta paginada é recusada.
- O período vai até o fim do ano seguinte porque, depois do IPCA de novembro, a próxima divulgação já é de janeiro, e o montador exige uma divulgação depois de t0 e sem buraco na agenda.

**CDS manual (`data/manual/cds.csv`).**
- Só acréscimo, UTF-8, linhas `#` ignoradas.
- Colunas: `data_referencia,vertice,bps,fonte,preenchido_por,preenchido_em`.
- Vértices em dias úteis: 6M = 126, 1A = 252, 2A = 504, 3A = 756, 4A = 1008, 5A = 1260, 7A = 1764, 10A = 2520, 20A = 5040. Na curva, bps ÷ 10.000.
- Correção = linha nova do mesmo dia e vértice com `preenchido_em` posterior.
- No JSON, `publication_date` e `retrieved_at` são o maior `preenchido_em` do conjunto (saída determinística).
- O pipeline nunca baixa as páginas do Investing.com.

**Calendário.** `data/calendar/feriados_nacionais.xls` (original da ANBIMA, com `manifest.json`) convertido em `feriados_anbima.csv`, com o sha256 do `.xls` e a cobertura no cabeçalho (Q10).

### Brutos: `data/raw/`

```
data/raw/AAAA/MM/AAAA-MM-DD/   pasta da data-base t0 (não da data da coleta)
  anbima_ettj.csv
  bcb_sgs_12.json  bcb_sgs_433.json  bcb_sgs_4390.json  bcb_sgs_7478.json
  ibge_calendario.json
  manifest.json
data/raw/AAAA/MM.zip           meses compactados
```

- Bruto nunca é sobrescrito. Conteúdo novo para o mesmo nome vira `<nome>.v2.<ext>`, `.v3`…; conteúdo repetido só ganha entrada no manifesto com `duplicate: true`. Vale a última entrada da fonte no manifesto.
- Cada entrada do manifesto: `file`, `source`, `url`, `requested_date`, `source_date`, `publication_date`, `retrieved_at`, `sha256`, `bytes`, `duplicate`. A URL do ANBIMA não traz os campos do POST. `publication_date` sai sempre `null` no manifesto (existe só no JSON). O `source_date` do manifesto é o da hora da coleta; vale o do JSON.
- O manifesto é atualizado sob trava (`.manifest.lock`, ignorado pelo git) e gravado de forma atômica.
- Retenção: um mês vira `AAAA/MM.zip` quando o último dia dele fica mais de 90 dias antes de t0. O zip nunca é refeito; a leitura junta o zip e uma eventual pasta solta do mesmo mês.
- Tamanho: cerca de 0,6 MB por dia útil, quase tudo `ibge_calendario.json`; um JSON de saída tem cerca de 96 KB.

### Exportações

- **CSV:** cabeçalho `data_base,modo,ano,di,inflacao,cds,juro_real,desconto`; modo `corrigido` primeiro e depois `legado`; taxas em decimal ao ano com precisão total; célula vazia para `null`; vírgula como separador, ponto decimal, UTF-8. O histórico traz todas as datas-base em ordem crescente.
- **XLSX:** aba Dashboard com as posições de `Dashboard!A1:Q31` e o LEGADO do dia (inclui os links do Investing em J9:J17); aba Corrigido com a tabela anual, o CDS do ano corrente, o realizado e CORRIGIDO − LEGADO; aba Fontes com as datas, `stale`, motivo e URL de cada fonte, os alertas e a execução. Sem fórmulas, até 16 algarismos significativos, determinístico (datas internas do arquivo = t0).
- Com o CDS oculto, o CSV sai sem `cds` e `desconto`, e as células de CDS e de taxa de desconto do XLSX ficam vazias.

## 4. Secrets e política de stale

### Credenciais e permissões

Nenhum segredo é necessário. As fontes são públicas, e o commit, o deploy e o disparo do daily pelo workflow **cds** usam o `GITHUB_TOKEN` automático, com as permissões declaradas em cada job:

| Workflow / job | Permissões |
|---|---|
| `daily` / pipeline | `contents: write` (commit de `data/`) |
| `daily` / deploy | `pages: write`, `id-token: write`; environment `github-pages` |
| `cds` | `contents: write` (commit de `cds.csv`), `actions: write` (`gh workflow run daily.yml`) |
| `tests` | `contents: read` |

Variáveis de ambiente que o código lê: `GITHUB_OUTPUT` (saída do run), `GITHUB_SHA` (reserva para `git_commit`), `GITHUB_SERVER_URL` e `GITHUB_REPOSITORY` (link do formulário no site) e `CI` (hypothesis determinístico). A única variável de repositório é `OCULTAR_CDS`.

Commits feitos com o `GITHUB_TOKEN` não disparam outros workflows (exceto `workflow_dispatch`): por isso o cds dispara o daily com `gh workflow run`, e os commits do bot não rodam o `tests`.

### CDS no site: variável `OCULTAR_CDS` (Q17)

Decisão de 02/10/2026 (Q17): repositório e site publicam os valores de CDS. A ressalva dos termos do Investing.com (§14), que vedam exibir os valores sem permissão, fica registrada como risco conhecido e aceito. A chave continua disponível, desligada por padrão:

| `OCULTAR_CDS` | Build |
|---|---|
| ausente, vazia ou `false` | mostra o CDS |
| `true` | `--ocultar-cds` |
| qualquer outro valor | o passo de build falha e nada novo é implantado |

- O workflow também aceita `1`, `sim`, `0`, `nao` e `não`, sem diferenciar maiúsculas ASCII nem espaços; `NÃO` maiúsculo falha. Use só `true` ou `false`.
- Crie a variável no nível do repositório (*Settings → Secrets and variables → Actions → Variables*), não no environment `github-pages`.
- Oculto: nenhuma página, gráfico ou download traz CDS nem taxa de desconto, que depende dele; os alertas de variação de CDS e desconto perdem o valor em bps; `latest.json` e `curves/` não são publicados; os links de coleta ficam.
- A chave vale só para o site e os downloads. O repositório público continua com `data/manual/cds.csv` e os JSON de `data/` completos.
- Sem a flag, vale `DEFAULT.site.show_cds_values` em `src/curvas/config.py` (hoje `True`); com `False` ali, o site sempre esconde.
- A troca vale no próximo build, que só roda quando algum dia é publicado. Para aplicar já, rode o daily à mão com `as_of` = a data-base mais recente do site.

### Política de stale por fonte

Toda fonte segue a mesma ordem:

1. Baixa e valida. Se der certo, grava o bruto e usa (fonte atual).
2. Se falhar, usa o bruto já gravado do próprio t0, sem `stale`, com o alerta informativo `fonte_bruto_do_dia`.
3. Sem bruto de t0, usa o último bruto válido dos 60 dias corridos anteriores: `stale: true`, `fallback_reason` "…; usado o bruto de DD/MM/AAAA" e alerta `fonte_defasada`.
4. Sem nenhum: o dia é bloqueado.

Erros que levam ao fallback: falha de rede ou HTTP, ETTJ não publicada, formato inesperado, validação reprovada e JSON inválido. O site mostra cada fonte como Atual ou Defasado, com a data real do dado.

| Fonte | `--catch-up` (cron) | `--as-of` (manual) |
|---|---|---|
| ETTJ ANBIMA | Nunca publica ETTJ de outro dia. Corpo vazio com t0 ≥ hoje: **pendente**, sem erro. Qualquer outra falha: **bloqueia** o dia | Publica com a ETTJ do último dia válido, `stale` e alerta; a recuperação refaz o dia se ele ainda estiver na janela |
| SGS e IBGE | `stale` com alerta, publica | igual |
| SGS 12 com dias faltando no fim (Q18, provisório) | Repete a última taxa até a véspera de t0, alerta `cdi_preenchido`, fonte `stale`. Buraco no meio bloqueia | igual |
| IPCA divulgado pelo IBGE e ainda fora do SGS 433 | Tratado como não divulgado (a curva cobre o mês), alerta `ipca_sem_valor_no_sgs` | igual |
| CDS manual | Último conjunto completo ≤ t0, sem idade máxima; `stale` e alerta se for de antes de t0. Arquivo inválido ou sem conjunto completo bloqueia | igual |

Dias publicados com SGS/IBGE defasados ou com `cdi_preenchido` não são refeitos sozinhos quando o dado sai (a recuperação só olha a ETTJ e o CDS). Para corrigir, rode o daily com `as_of` daquele dia.

### O que bloqueia, o que fica pendente

**Bloqueia o dia** (`BLOQUEADO`, workflow vermelho):
- `--as-of` em dia não útil ou no futuro;
- fonte sem nenhum bruto válido nos 60 dias;
- ETTJ do cron que não seja "ainda não publicada hoje";
- CDS manual ilegível ou sem conjunto completo;
- erro de montagem ou de cálculo (`cálculo: …`);
- schema inválido (NaN, infinito, fator ≤ 0).

Fora do run, bloqueiam também os checks e testes do daily (antes do pipeline), a validação do schema e um `OCULTAR_CDS` inválido.

**Fica pendente, sem erro:** a ETTJ de hoje ainda não saiu (`Pendente: …`). A próxima execução tenta de novo.

**Termina sem publicar e sem erro:** dia não útil sem `--as-of` (`Sem publicação: …`) ou recuperação sem pendências (`Nada pendente.`).

Um dia bloqueado não impede os outros: os dias que saíram são commitados e implantados, e o workflow fica vermelho no último passo.

### Códigos de alerta

| Código | Nível | Significado |
|---|---|---|
| `fonte_bruto_do_dia` | info | A coleta de agora falhou, mas havia bruto válido de t0. Não indica dado velho |
| `fonte_defasada` | warning | Fonte usou o bruto de outro dia (`stale`) |
| `ipca_sem_valor_no_sgs` | warning | IPCA divulgado pelo IBGE, ainda sem valor no SGS 433 |
| `cdi_preenchido` | warning | Q18: dias finais do CDI repetem a última taxa |
| `cds_manual` | warning | CDS defasado, conjunto mais recente incompleto ou correção aplicada |
| `legado_virada_do_ano` | warning | Nenhum IPCA do ano de t0 divulgado: ano corrente do LEGADO indisponível (Q6) |
| `legado_indisponivel` | warning | `#N/A` do LEGADO em outro ano |
| `variacao_diaria` | warning | Taxa anual variou mais de 50 bps desde a saída do dia útil anterior |

**Variação diária:** compara os campos `di`, `inflation`, `cds`, `real` e `discount`, nos dois modos e em cada ano, com a saída do dia útil imediatamente anterior, se ela existir. Alerta quando |variação| > 50 bps (`AlertConfig.max_daily_change_bps` em `config.py`; não há flag). Nunca bloqueia. É a única exceção à reprodutibilidade (16.7): mesmos t0, brutos, configuração e CDS manual dão o mesmo JSON, salvo esses alertas, que dependem da saída anterior.

## 5. Horário do cron e operação diária

### Cron (`.github/workflows/daily.yml`)

| Execução | BRT | Cron (UTC) | Por quê |
|---|---|---|---|
| Principal | 21h37, seg–sex | `37 0 * * 2-6` | A ETTJ do dia sai no fim da tarde ou à noite (ANBIMA Feed: "a partir das 20h"; às 15h12 de 02/10/2026 ainda não estava publicada). O CDI da véspera de t0 já está no SGS (às 12h25 de 02/10/2026, o de 01/10 já estava). |
| Recuperação | 07h23, ter–sáb | `23 10 * * 2-6` | O agendamento do GitHub atrasa em picos e às vezes descarta execuções. |

- O cron do GitHub está em UTC. O Brasil não tem horário de verão desde 2019 (Decreto 9.772/2019), então BRT = UTC−3 o ano todo. O código também fixa UTC−3 (`run.py` e `cds_add.py`); se o horário de verão voltar, revise o cron e essas constantes.
- Os minutos "quebrados" evitam o pico do início da hora.
- O schedule só roda no branch padrão.

### Janela e recuperação (`--catch-up`)

As duas execuções agendadas rodam `--catch-up`. Ele olha os 5 dias úteis ANBIMA mais recentes até hoje (inclusive), a janela que a página pública da ANBIMA guarda, a partir de 29/09/2026 (início do pipeline), e refaz o dia que:

- não tem saída;
- tem saída que usou a ETTJ de outro dia;
- tem saída com um CDS manual diferente do que valeria agora (lançado ou corrigido depois).

Consequências:

- Em dia não útil, hoje não entra na janela, mas os dias úteis anteriores ainda pendentes entram: a execução das 07h23 de sábado recupera a sexta. Só sem pendências o resultado é "Nada pendente.".
- Às 07h23 do dia seguinte, um dia que continuar sem ETTJ já é passado e bloqueia.
- **Um dia que sai da janela sem saída nunca mais é tentado**, e a ANBIMA não o oferece mais. O daily não pode ficar mais de 5 dias úteis sem rodar.
- CDS lançado fora da janela fica em `cds.csv`, mas não refaz aquela data-base. Os dias da janela que usavam um CDS defasado mais antigo são refeitos.

### Sequência do daily

1. Checkout da ponta do branch (não do commit do disparo) e `uv sync --locked`.
2. `ruff check`, `ruff format --check`, `mypy` e `pytest -q`. Falha aqui impede o pipeline.
3. Pipeline: `--catch-up` (ou `--as-of` com o input preenchido). O código de saída fica guardado.
4. Se algo foi publicado: validação do schema de `data/latest.json` e `data/curves/*.json`.
5. Commit de `data/` (`dados: t0 = <data> [skip ci]`), `git pull --rebase` e push.
6. Build do site (com `--ocultar-cds` se `OCULTAR_CDS` = `true`) e upload do artefato do Pages.
7. Workflow vermelho se algum dia foi bloqueado.
8. Job de deploy no GitHub Pages, sempre que houve publicação, mesmo com outro dia bloqueado.

Sem publicação (só pendentes, só bloqueados ou nada pendente), não há commit, build nem deploy. Concorrência: o daily roda um por vez (grupo `daily`); um disparo novo na fila substitui o que esperava. Como cada recuperação processa a janela inteira, nada se perde, mas um daily manual com `as_of` que estava na fila pode aparecer como cancelado e precisa ser repetido. O cds não tem grupo de concorrência: execuções simultâneas se resolvem refazendo a gravação sobre a ponta do branch (até 5 tentativas). Timeouts: daily 90 min, cds 10 min, tests 15 min.

### Rotina diária

1. **Todo dia útil:** registrar os 9 valores do CDS do dia pelo formulário **cds**. O horário não importa: se a ETTJ ainda não saiu, o daily disparado deixa o dia pendente e a execução das 21h37 publica com o CDS; se o dia já foi publicado, o daily disparado o refaz.
2. **Na manhã seguinte:** na aba Actions, conferir se o **daily** ficou verde; no site, conferir a data-base, os alertas e as fontes (Atual/Defasado).
3. **Vermelho ou dia faltando:** seção 7, com prazo de 5 dias úteis para resolver antes de o dia sair da janela.
4. **Toda semana:** conferir se os workflows agendados continuam ativos (seção 9).

## 6. Metodologias

Os dois modos são calculados na mesma execução, com as mesmas fontes e o mesmo t0. O modo padrão de exibição é o **CORRIGIDO** (`metadata.default_mode = "corrected"`); o seletor do site só troca o que aparece.

**LEGADO** (`engine/legacy.py`) tem dois usos:
- **(a) validação:** a planilha exatamente como está (Janeiro/1º Tri, YTG do CDS = 62). Existe só nos testes, contra as fixtures recalculadas da planilha.
- **(b) diário (o do site):** as mesmas fórmulas, com m = mês do último IPCA divulgado até t0, trimestre = o que contém m e YTG = (12 − m)·21 nas três curvas (Q6). As curvas são montadas da ANBIMA como o operador fazia, sem o erro de colagem da planilha (Q14, Q15).

**CORRIGIDO** (`engine/corrected.py`) segue a E8.

| Etapa | LEGADO | CORRIGIDO |
|---|---|---|
| Vértices | Grade de 126 em 126 d.u.: DI e inflação com 19 vértices de 126 a 2394 (inflação 126 := 252; DI 126 da Circular 3.361); CDS com 9 | Só os publicados: inflação implícita de 252 a 2520; DI = ETTJ PREF + Circular 3.361 abaixo de 252 (21, 42, 63, 126) |
| Interpolação | Linear nas taxas | Flat-forward nos fatores F(v) = (1 + s)^(v/252); spot constante antes do 1º vértice, forward do último segmento depois do último |
| Acumulação | Dia a dia, com a taxa interpolada do dia tratada como forward | Fator spot da curva interpolada (reprecifica os vértices com erro < 1e-12) |
| Corte dos anos | YTG + 252·(n − 1) | Dias úteis de t0 (inclusive) até 31/12, pelo calendário ANBIMA (Q11) |
| Realizado do ano | IPCA de jan a m; Selic dos meses do trimestre de m, anualizada com expoente 4/(5 − q) | CDI do SGS 12 de 1º/jan até a véspera de t0; IPCA até o último mês divulgado, com o intervalo até t0 coberto pela curva, só no ano corrente (E8.6, Q12) |
| CDS do ano corrente | Acumulado do CDS nos YTG dias, anualizado: (1 + Acum)^(252/YTG) − 1 | Taxa anualizada só dos dias úteis restantes até 31/12, com o acumulado ao lado |

Regras comuns:
- **Juro real** = (1 + DI)/(1 + Inflação) − 1 (E8.8), linha a linha das taxas anuais, nos dois modos.
- **Taxa de desconto** = (1 + DI)(1 + CDS) − 1, por ano civil, nos dois modos (Q4). No ano corrente do CORRIGIDO, compõe o DI do ano civil com o CDS anualizado do período restante. O texto da E8.8 na especificação ainda trata a convenção como "a definir"; vale a Q4.
- **Virada do ano:** enquanto nenhum IPCA do ano de t0 saiu, o ano corrente do LEGADO sai `null`, com alerta, e os anos seguintes saem normais (Q6).
- **IPCA-15 (Q13, Forma A):** alternativa para o intervalo do IPCA não divulgado, só com `--ipca15`. Em produção vale a curva.
- **Comparação:** `comparison` = (CORRIGIDO − LEGADO) em bps; `null` se o LEGADO estiver indisponível.

Onde está o detalhe:
- página **Metodologia** do site (`src/curvas/site/templates/metodologia.html` mais a especificação renderizada);
- `docs/ESPECIFICACAO.md`: E4 (motor da planilha), E6 (diagnóstico) e E8 (metodologia corrigida);
- `docs/F2_LEGADO_X_CORRIGIDO.md`: a diferença decomposta por causa (corte em 31/12, realizado, acumulação, interpolação, calendário, anualização, erro de colagem). Usa o LEGADO **uso (a)** com os inputs da planilha e t0 = 29/09/2026, não o LEGADO diário do site;
- `docs/F0_AUDITORIA.md`: mapa e inventário de fórmulas da planilha.

## 7. Troubleshooting e manutenção

### Mensagens do pipeline

| Mensagem | Causa | O que fazer |
|---|---|---|
| `BLOQUEADO: t0 = … não é dia útil ANBIMA` / `… está no futuro (hoje = …)` | `--as-of` (ou `as_of` do formulário) inválido | Corrigir a data |
| `BLOQUEADO: <fonte>: …; nenhum bruto válido anterior` | Coleta falhou e não há bruto válido nos 60 dias anteriores (primeira coleta, pausa longa ou `--offline` sem bruto) | Ver a causa no log; com a fonte de volta, rodar de novo |
| `BLOQUEADO: AAAA-MM-DD: anbima_ettj de DD/MM/AAAA: FetchError: … HTTP 503 depois de 4 tentativas` | ANBIMA fora do ar | A próxima execução tenta de novo; o dia tem até sair da janela |
| `… anbima_ettj …: FetchError` com HTTP 404 ou outro 4xx | Endpoint mudou ou sumiu (Q19) | Ver "Troca da fonte da ANBIMA" |
| `… anbima_ettj …: AnbimaFormatError: seções ausentes: […]` | A ANBIMA devolveu HTML ou mudou o layout | Idem |
| `… anbima_ettj …: NotPublishedError: resposta vazia da ANBIMA` | Dia passado ainda sem ETTJ | Tentar de novo mais tarde; se persistir, investigar na página da ANBIMA |
| `… anbima_ettj …: ValidationError: …` (`ANBIMA devolveu X, pedido Y`, `grade de vértices irregular`, `Circular 3.361 difere da ETTJ PREF`, `Fisher não fecha`, `fora de […]`) | Dado reprovado na validação | Conferir o CSV da ANBIMA; não forçar a publicação sem entender |
| `Pendente: …: ETTJ da ANBIMA de … ainda não publicada` | Normal antes da publicação | Nada |
| `BLOQUEADO: CDS manual: …` | `cds.csv` inválido (`não está em UTF-8`, `cabeçalho esperado`, `linha N: …`, `correção … precisa de preenchido_em posterior`) ou `nenhum conjunto completo de CDS até …` | Reverter a edição manual e lançar pelo `cds_add` ou pelo formulário |
| `BLOQUEADO: cálculo: …` | `CDI sem observação em N dia(s) útil(eis)` (buraco no meio do SGS 12), `agenda do IPCA com buraco`, `a agenda de divulgações do IPCA não cobre t0`, `último IPCA divulgado … defasado`, `IPCA/Selic de MM/AAAA ausente` | Esperar a fonte corrigir e rodar de novo |
| `BLOQUEADO: schema inválido: …` | Saída com NaN, infinito ou fator ≤ 0 | Bug: investigar com `--as-of D --offline` numa cópia |
| `INVÁLIDO: <arquivo>: …` (`curvas.schema validate`) | JSON fora do schema | Idem; se `models.py` mudou, ver "Mudança de schema" (seção 3) |

O log JSON (`fonte falhou`, `publicação bloqueada`) traz a causa de cada falha. Nas mensagens do CDS, "linha N" conta só as linhas de dados (sem cabeçalho e comentários): o primeiro lançamento novo do arquivo atual é a linha 10.

### Erros do CDS

| Mensagem | Causa |
|---|---|
| `NADA GRAVADO: esperados 9 valores, vieram N` | Faltou ou sobrou valor |
| `NADA GRAVADO: could not convert string to float: …` | Texto, valores separados por vírgula ou separador de milhar |
| `NADA GRAVADO: linha N: bps fora da faixa: X` | Valor ≤ 0 ou ≥ 3000 |
| `NADA GRAVADO: linha N: data de referência D depois do preenchimento` | Data futura (inclusive sábado ou feriado futuros) |
| `NADA GRAVADO: linha N: D não é dia útil ANBIMA` | Fim de semana ou feriado passado |
| `NADA GRAVADO: fonte e nome não podem ter vírgula` | Vírgula em `--por` ou `--fonte` |
| `error: argument --data: invalid fromisoformat value` | Data fora do formato AAAA-MM-DD |
| `::error::Não foi possível gravar o CDS depois de 5 tentativas; nada foi gravado.` | Workflow cds: push recusado 5 vezes; rodar de novo |

Editar `data/manual/cds.csv` no Excel pode trocar a codificação ou o separador e bloquear todos os dias. Use só o `cds_add` ou o formulário.

### Workflow vermelho

| Passo do daily | Causa provável |
|---|---|
| Instalar | `uv.lock` desatualizado em relação ao `pyproject.toml` (`uv sync --locked`) |
| Testes | ruff, formatação, mypy ou pytest; inclui `cds.csv` inválido e `docs/schema.json` ou tabela da F2 desatualizados. Reproduza com os 4 comandos da seção 2, com `CI=true` |
| Pipeline (vermelho no passo "Falhar se algum dia foi bloqueado") | Linhas `BLOQUEADO:` no log do passo Pipeline |
| Validar o schema | Algum `data/curves/*.json` antigo fora do schema |
| Commit dos JSON e brutos | Push recusado ou sem permissão de escrita (a organização pode limitar as permissões do `GITHUB_TOKEN`; não verificado) |
| Build do site | `OCULTAR_CDS` inválido, com a mensagem `::error::OCULTAR_CDS inválido…` |

Se um passo depois do Pipeline falhar, os seguintes não rodam e o site anterior continua no ar.

### Dia pendente que não sai

- A ETTJ ainda não foi publicada: normal até a noite.
- O passo de testes falhou e o pipeline nem rodou.
- O dia saiu da janela de 5 dias úteis: a recuperação não o tenta mais. Rode o daily com `as_of` = o dia; se a ANBIMA não servir mais a data, o run usa o bruto da ETTJ já gravado de t0 (com o alerta `fonte_bruto_do_dia`). Sem bruto gravado, o dia não pode mais ser feito com a ETTJ dele.
- Datas anteriores a 29/09/2026 nunca entram.
- O dia já tem saída com ETTJ do próprio dia e o CDS não mudou: não há o que refazer. Para forçar, rode o daily com `as_of`.

Para refazer um dia fora da janela sem rede: `uv run python -m curvas.run --as-of AAAA-MM-DD --offline` no repositório, commit e push pelo GitHub Desktop. O site só é refeito no próximo daily que publicar.

### Site não atualiza

O build e o deploy só rodam quando algum dia é publicado. Uma execução com "Nada pendente.", só pendentes ou só bloqueados não refaz o site. Mudança em `OCULTAR_CDS`, nos templates ou no código do site só aparece no próximo dia publicado; para aplicar já, rode o daily com `as_of` = a data-base mais recente (não a de hoje antes de a ETTJ sair, que publicaria com a curva defasada). Rodar com uma data antiga não muda a data principal do site, porque o `latest.json` não regride. Confira também se *Settings → Pages → Source* está em **GitHub Actions**.

### Manutenção

**Calendário ANBIMA.**
- Cobertura de 2001 a 2099; o CORRIGIDO precisa de 11 anos à frente, então o arquivo atual atende t0 até 2088.
- Atualize quando a ANBIMA mudar os feriados: apague `data/calendar/feriados_nacionais.xls` (o script não sobrescreve) e rode os comandos abaixo.

```bash
uv run python tools/baixar_dados_f2.py
uv run --group tools python tools/converter_feriados_anbima.py
CI=true uv run pytest -q tests/test_calendar.py
```

- O primeiro comando acessa a rede e também tenta as fixtures de `tests/fixtures/f2/`, pulando as que já existem. O segundo imprime `N feriados de … a … → data/calendar/feriados_anbima.csv`.
- `test_dia_a_dia_igual_ao_bizdays` falha se o bizdays não tiver o feriado novo: atualize o bizdays junto.
- Outra cobertura exige ajustar `test_cobertura`. Mudança de feriado altera os dias úteis: regenere offline as saídas afetadas, se quiser coerência.

**Troca da fonte da ANBIMA (Q19).**
- A ANBIMA avisou que a aba das curvas será desligada e que elas ficarão só no ANBIMA Data. Quando o endpoint parar, o cron bloqueia todo dia útil (404 ou HTML), e os testes continuam verdes porque usam respostas gravadas.
- Trocar de fonte exige registro em `OPEN_QUESTIONS.md` (regra "não troque fontes sem documentar"); a alternativa para o DI (B3 DI × Pré, E9) depende de decisão.
- Pontos acoplados à fonte: URL em `config.py`; POST em `fetch/sources.py`; parser em `normalize/anbima_ettj.py` (inclusive "corpo vazio = não publicado", de que o `Pendente` depende); validação em `validate/checks.py`; o nome `anbima_ettj` em `run.py` e `site/view.py`; a janela `ANBIMA_WINDOW = 5` em `run.py`; os testes `test_anbima.py`, `test_fetch.py`, `test_run.py`, `test_reconciliacao_anbima.py` e as fixtures `tests/fixtures/f3/anbima/`.
- Os brutos antigos continuam no formato antigo: a regeneração offline de dias antigos depende do parser antigo.

**Dependências.** Os três workflows rodam `uv sync --locked`: depois de mexer no `pyproject.toml`, rode `uv lock` e commite o `uv.lock`. Para atualizar:

```bash
uv lock --upgrade
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
CI=true uv run pytest -q
```

- Para um pacote só, use `uv lock --upgrade-package <pacote>`.
- Um ruff novo pode reformatar código e bloquear o daily; uma versão nova do formulas muda a referência de recálculo da Q7 (registrada no `_meta` das fixtures).
- O CI usa Python 3.12 e não fixa a versão do uv. Uma falha só no CI pode vir daí; `uv sync --python 3.12` reproduz o Python do CI (baixa um CPython para a pasta do usuário).
- Actions: só o `astral-sh/setup-uv` está fixado por SHA (v10.2.0, nos três arquivos; troque o SHA e o comentário juntos). `actions/checkout@v7`, `actions/upload-pages-artifact@v5` e `actions/deploy-pages@v5` seguem a tag maior. Não há Dependabot.

**Artefatos gerados com teste de igualdade.**

| Mudou | Rode | Senão falha |
|---|---|---|
| `src/curvas/models.py` | `uv run python -m curvas.schema export` | `test_schema_publicado_atualizado` |
| motor ou fixtures da F2 | `uv run python tools/tabela_f2.py` | `test_tabela_publicada_esta_atualizada` |
| planilha legada | `uv run --group tools python tools/gerar_fixtures_legado.py` | `test_fixtures_vem_da_planilha_atual` (só com a planilha local) |
| `docs/ESPECIFICACAO.md` | nada; o site renderiza o arquivo | (muda a página Metodologia) |

- `tools/tabela_f2.py` é offline e regenera `docs/F2_LEGADO_X_CORRIGIDO.md` e `docs/f2_legado_x_corrigido.csv`. O texto do `.md` vem de `src/curvas/output/comparacao.py`: editar só o `.md` é desfeito na próxima execução.
- `tools/gerar_fixtures_legado.py` precisa da planilha em `docs/legado/Query-Avila.xlsx` e do grupo `tools`. Leva cerca de 3,5 min (`--inputs-only`: só os inputs, cerca de 2 s) e grava `tests/fixtures/legacy/`, que vai para o repositório público: confira que nenhum link interno entrou.

**Regenerar saídas offline** (depois de mudar o motor, por exemplo):
- Commite o código antes, para o `git_commit` não sair `-dirty`.
- Rode `uv run python -m curvas.run --as-of D --offline` para cada data-base, em ordem crescente (os alertas de variação comparam com o dia anterior já regenerado).
- O resultado usa o `cds.csv` de agora. Os brutos de 29/09 a 01/10/2026 têm a agenda do IBGE só até 31/12/2026; reprocessá-los depois de meados de dezembro de 2026 pode falhar por "agenda não cobre".

**Integridade dos brutos.** A leitura não confere o sha256. Para conferir à mão (pastas soltas e zips):

```bash
uv run python - <<'EOF'
import hashlib, json, pathlib, zipfile
ruins = []
for m in pathlib.Path("data/raw").glob("*/*/*/manifest.json"):
    for e in json.loads(m.read_text("utf-8")):
        if hashlib.sha256((m.parent / e["file"]).read_bytes()).hexdigest() != e["sha256"]:
            ruins.append(str(m.parent / e["file"]))
for a in pathlib.Path("data/raw").glob("*/*.zip"):
    with zipfile.ZipFile(a) as zf:
        for n in [n for n in zf.namelist() if n.endswith("/manifest.json")]:
            d = n.rsplit("/", 1)[0]
            for e in json.loads(zf.read(n)):
                if hashlib.sha256(zf.read(f"{d}/{e['file']}")).hexdigest() != e["sha256"]:
                    ruins.append(f"{a}:{d}/{e['file']}")
print("\n".join(sorted(set(ruins))) or "sha256 ok")
EOF
```

**Pendências conhecidas na documentação e no código.**
- `docs/ESPECIFICACAO.md` (E8.8) ainda diz que a taxa de desconto depende de convenção a definir; a decisão é a Q4.
- `docs/F2_LEGADO_X_CORRIGIDO.md` ainda marca Q11 e Q12 como "a confirmar" (texto em `output/comparacao.py`).
- `docs/F0_AUDITORIA.md` e `docs/F3_DIAGNOSTICO_CDS.md` citam pastas de `scratch/` que não são versionadas.
- `raw.latest_raw_before` e `validate.checks.validate_daily_series` não são usados (o fallback está em `run.py`).
- numpy e pandas são dependências de runtime sem uso direto.

## 8. Configuração inicial do repositório (uma vez)

1. Publicar o repositório **público** (Q3) com o branch `main` atualizado: GitHub Desktop → *Publish repository*, com "Keep this code private" desmarcado. Os três workflows já estão no `main`.
2. *Settings → General → Default branch*: conferir que é `main`. O cron e o botão *Run workflow* só existem para workflows do branch padrão.
3. *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
4. `OCULTAR_CDS`: não criar (Q17 resolvida: o site mostra o CDS). Só se a decisão mudar: *Settings → Secrets and variables → Actions → Variables*, `OCULTAR_CDS` = `true`.
5. Rodar o **daily** à mão uma vez (Actions → daily → *Run workflow*, branch `main`, `as_of` vazio), para recuperar a janela e confirmar o acesso às fontes a partir dos servidores do GitHub. **Prazo: até 08/10/2026.** Em 09/10/2026 a data-base de 02/10/2026 sai da janela da ANBIMA e se perde.
6. Conferir o site publicado e a página Coleta do CDS (o link "Abrir o formulário" aparece a partir desse build).

## 9. Cuidados

- **Janela de 5 dias úteis:** se o daily ficar parado (desativado, vermelho por testes, sem remoto) por mais de 5 dias úteis, os dias que saem da janela se perdem. Não há como reconstruí-los depois.
- **Inatividade:** em repositório público, o GitHub desativa workflows agendados depois de 60 dias sem atividade no repositório, e não está documentado se os commits do bot contam. Um workflow desativado não fica vermelho, só para de rodar. Reative na aba Actions → daily → *Enable workflow*.
- **ANBIMA (Q19):** a página das curvas avisa que a aba será desligada e que as curvas ficarão só no ANBIMA Data. Se o download parar, o cron não publica dia sem curva: cada dia útil fica bloqueado (workflow vermelho) até a troca da fonte. Só o `as_of` manual publica com a ETTJ anterior, marcada `stale` e com alerta. Os testes do coletor continuam passando com as respostas gravadas.
- **CDS no site público (Q17):** o site e os downloads exibem o CDS copiado do Investing.com, por decisão de 02/10/2026, com o risco dos termos (§14) aceito. Para esconder, `OCULTAR_CDS` = `true` (seção 4); o repositório público continua com os valores.
- **Planilha legada:** é interna e fica fora do repositório (`docs/legado/*.xlsx` no `.gitignore`). Os 2 testes que dependem dela são pulados quando ela não existe.
- **`data/manual/cds.csv`:** só acréscimo, pelo `cds_add` ou pelo formulário. Nunca edite nem apague linhas antigas.
- **Commits locais:** o bot commita `data/` todo dia. Antes de commitar pelo GitHub Desktop, faça *Fetch origin* e *Pull*.
- **Comandos que escrevem no repositório:** `curvas.run`, `curvas.cds_add`, `curvas.schema export` e os scripts de `tools/` alteram arquivos versionados; para experimentar, use uma cópia (seção 2). Nunca rode `curvas.site.build --out data`.
- **Tamanho do repositório:** o histórico cresce cerca de 0,6 MB por dia útil com os brutos; a compactação em zip não reduz o que já foi commitado.
