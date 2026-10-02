# Plataforma de Curvas VAROS

Converte as curvas de mercado (DI, inflação implícita e CDS Brasil) em premissas anuais de 2026 a 2036, em dois modos: **LEGADO** (as fórmulas da planilha antiga) e **CORRIGIDO** (metodologia da especificação, E8). A documentação completa de operação é a fase F6; esta página cobre o que já existe.

- Instruções do projeto: [docs/INSTRUCOES.md](docs/INSTRUCOES.md) · Especificação: [docs/ESPECIFICACAO.md](docs/ESPECIFICACAO.md)
- Decisões e pendências: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
- Auditoria da planilha (F0): [docs/F0_AUDITORIA.md](docs/F0_AUDITORIA.md) · LEGADO × CORRIGIDO (F2): [docs/F2_LEGADO_X_CORRIGIDO.md](docs/F2_LEGADO_X_CORRIGIDO.md)
- Schema da saída: [docs/schema.json](docs/schema.json)

## Uso local

```bash
uv sync
uv run pytest
uv run python -m curvas.run --as-of 2026-10-01   # uma data-base, coletando as fontes
uv run python -m curvas.run --catch-up           # dias úteis pendentes (modo do workflow)
uv run python -m curvas.run --as-of 2026-10-01 --offline   # refaz só com os brutos gravados
```

Saídas: `data/curves/AAAA-MM-DD.json` (uma por data-base) e `data/latest.json`. Brutos em `data/raw/AAAA/MM/AAAA-MM-DD/` com `manifest.json`; meses com mais de 90 dias viram `data/raw/AAAA/MM.zip`.

## Site

```bash
uv run python -m curvas.site.build --out site                # lê data/latest.json e data/curves/*.json
uv run python -m curvas.site.build --out site --ocultar-cds  # sem valores de CDS nem taxa de desconto (Q17)
```

Site estático com Jinja2 e Plotly auto-hospedado. Todo número sai pronto do JSON; o JavaScript só alterna abas, modo (CORRIGIDO/LEGADO) e datas.

| Página | Conteúdo |
|---|---|
| Visão geral | Taxas anuais nos dois modos, CORRIGIDO − LEGADO em bps, alertas, status de cada fonte e downloads |
| Curvas | Vértices e curva interpolada, em taxa e em fator, com comparação a outra data-base |
| Realizado | IPCA e CDI mensais, acumulados do ano, regra do IPCA não divulgado e Selic mensal do LEGADO |
| Histórico | Cada taxa anual ao longo das datas-base |
| Metodologia | LEGADO × CORRIGIDO e a especificação renderizada |
| Coleta do CDS | Link da aba do Investing.com de cada vértice e como registrar os valores |

Downloads, gerados no build em `site/downloads/`:

- `curvas-AAAA-MM-DD.csv`: tabela anual do dia nos dois modos, em decimal ao ano;
- `curvas-AAAA-MM-DD.xlsx`: layout do Dashboard da planilha com o LEGADO do dia, mais as abas Corrigido e Fontes, só valores;
- `historico.csv`: a tabela anual de todas as datas-base.

Com o CDS visível, o site também publica `latest.json` e `curves/`. Cores e fonte ficam em `src/curvas/site/static/tokens.css` (Q5).

## CDS: entrada manual diária

Não há fonte gratuita que permita coleta automática (`docs/F3_DIAGNOSTICO_CDS.md`, Q16). A coleta é manual, como na planilha:

1. Uma vez por dia útil, alguém abre a página **Coleta do CDS** do site, que traz o link da aba do Investing.com de cada vértice (como `Dashboard!J9:J17`), e lê os 9 fechamentos.
2. Registra os valores de uma destas formas:
   - **pelo navegador:** aba Actions → **cds** → *Run workflow*, com `data` (AAAA-MM-DD), `valores` e `por` (nome). O workflow grava com o comando abaixo, commita `data/manual/cds.csv` e dispara o **daily**;
   - **pela linha de comando:**

     ```bash
     uv run python -m curvas.cds_add --data 2026-10-01 --por "Nome" --valores "45.67 54.35 67.89 87.28 109.84 130.71 171.71 213.22 245.59"
     ```

3. Na execução seguinte do daily, a recuperação refaz a data-base cujo CDS foi lançado ou corrigido depois, se ela ainda estiver na janela de 5 dias úteis da ANBIMA. Fora da janela, o registro fica em `cds.csv`, mas a saída publicada daquele dia não muda.

A ordem é 6M 1A 2A 3A 4A 5A 7A 10A 20A, em bps, com ponto ou vírgula decimal. Sem `--valores`, o comando pergunta um por um. Valores inválidos: nada é gravado. Para corrigir um dia, basta registrar de novo: a linha mais recente vale. Sem CDS do dia, o pipeline usa o último disponível, marca `stale` e gera alerta.

## Operação diária (GitHub Actions)

### Horário do cron

| Execução | BRT | Cron (UTC) | Por quê |
|---|---|---|---|
| Principal | 21h37, seg–sex | `37 0 * * 2-6` | A ETTJ da ANBIMA sai entre 19h e 20h (ANBIMA Feed: "a partir das 20h"). O CDI da véspera de t0 está no SGS desde a manhã. A Selic do dia sai até 19h. |
| Recuperação | 07h23, ter–sáb | `23 10 * * 2-6` | O agendamento do GitHub atrasa em picos e às vezes descarta execuções. |

- O Brasil não tem horário de verão desde 2019 (Decreto 9.772/2019), então BRT = UTC−3 o ano todo.
- Os minutos "quebrados" evitam o pico do início da hora.
- As duas execuções rodam `--catch-up`. Elas processam todo dia útil ANBIMA da janela de 5 dias úteis que a página pública guarda, a partir de 29/09/2026 (início do pipeline), que ainda não tenha saída, cuja saída tenha usado a ETTJ de outro dia ou cujo CDS manual mudou depois (lançado ou corrigido).
- **ETTJ de hoje ainda não publicada:** o dia fica pendente, sem erro, e a próxima execução tenta de novo.
- **Qualquer outra falha da ANBIMA** (fora do ar, layout novo, dado reprovado na validação, dia passado sem ETTJ): erro visível, workflow vermelho e a causa no log. Assim nenhum dia sai da janela em silêncio.
- Em dia não útil não há nada pendente, e o workflow termina sem publicar.

### Sequência (`.github/workflows/daily.yml`)

1. `uv sync --locked`
2. testes: ruff, mypy e pytest; teste falhando bloqueia
3. `python -m curvas.run --catch-up`
4. validação do schema
5. commit dos JSON e brutos (`[skip ci]`)
6. build do site (com `--ocultar-cds` se a variável `OCULTAR_CDS` for `true`, sem diferenciar maiúsculas; `false` ou vazia mostra o CDS, e qualquer outro valor faz o build falhar)
7. deploy no GitHub Pages

Um dia bloqueado (schema inválido, NaN, fator inválido, fonte sem nenhum dado válido, série fora da faixa plausível) faz o workflow falhar. Mesmo assim, os outros dias são publicados.

Reprodutibilidade (16.7): mesmos t0, brutos, configuração e CDS manual dão o mesmo JSON. A única exceção são os alertas de variação diária, que comparam com a saída do dia útil anterior, se ela existir.

Execução manual: aba Actions → **daily** → *Run workflow*. O campo `as_of` vazio faz a recuperação; com uma data, roda só aquela data-base.

### Credenciais

Nenhum segredo é necessário. As fontes são públicas, e o commit, o deploy e o disparo do daily pelo workflow **cds** usam o `GITHUB_TOKEN` automático, com as permissões declaradas em cada job.

### Configuração inicial do repositório (uma vez)

1. Criar o repositório **público** no GitHub (Q3) e enviar o branch `main`.
2. *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
3. Se os valores de CDS não puderem aparecer no site (Q17): *Settings → Secrets and variables → Actions → Variables*, criar `OCULTAR_CDS` = `true`.
4. Rodar o workflow **daily** à mão uma vez, para confirmar o acesso às fontes a partir dos servidores do GitHub.

### Cuidados

- **Inatividade:** em repositório público, o GitHub desativa workflows agendados depois de 60 dias sem atividade no repositório, e não está documentado se os commits do bot contam. Se o workflow for desativado, reative-o na aba Actions.
- **ANBIMA:** a página das curvas avisa que a aba será desligada e que as curvas ficarão só no ANBIMA Data (Q19). Se o download parar, o pipeline usa o último dado válido com alerta e os testes do coletor continuam passando com as respostas gravadas. O coletor terá de ser trocado.
- **CDS no site público (Q17):** por padrão, o site e os downloads exibem o CDS copiado do Investing.com, o que os termos dele vedam sem permissão. Com a variável `OCULTAR_CDS` = `true` (ou `DEFAULT.site.show_cds_values = False` em `curvas.config`), o build esconde todo valor de CDS e a taxa de desconto, que depende dele, e não publica `latest.json` nem `curves/`; os links de coleta ficam. A troca vale no próximo build (para aplicar já, rode o daily à mão com `as_of` = a data-base mais recente). Isso não cobre o repositório público: `data/manual/cds.csv` e os JSON em `data/` continuam com os valores. Ligar o Pages com os valores é decisão da VAROS (parecer jurídico ou autorização, Q16).
- **Planilha legada:** é interna e fica fora do repositório (`docs/legado/*.xlsx` no `.gitignore`). Os testes que dependem dela são pulados quando ela não existe.
