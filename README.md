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

## CDS: entrada manual diária

Não há fonte gratuita que permita coleta automática (`docs/F3_DIAGNOSTICO_CDS.md`, Q16). Uma vez por dia útil, alguém consulta os 9 vértices e registra:

```bash
uv run python -m curvas.cds_add --data 2026-10-01 --por "Nome" --valores "45.67 54.35 67.89 87.28 109.84 130.71 171.71 213.22 245.59"
```

A ordem é 6M 1A 2A 3A 4A 5A 7A 10A 20A, em bps. Sem `--valores`, o comando pergunta um por um. Para corrigir um dia, basta rodar de novo: a linha mais recente vale. Sem CDS do dia, o pipeline usa o último disponível, marca `stale` e gera alerta.

## Operação diária (GitHub Actions)

### Horário do cron

| Execução | BRT | Cron (UTC) | Por quê |
|---|---|---|---|
| Principal | 21h37, seg–sex | `37 0 * * 2-6` | A ETTJ da ANBIMA sai entre 19h e 20h (ANBIMA Feed: "a partir das 20h"). O CDI da véspera de t0 está no SGS desde a manhã. A Selic do dia sai até 19h. |
| Recuperação | 07h23, ter–sáb | `23 10 * * 2-6` | O agendamento do GitHub atrasa em picos e às vezes descarta execuções. |

- O Brasil não tem horário de verão desde 2019 (Decreto 9.772/2019), então BRT = UTC−3 o ano todo.
- Os minutos "quebrados" evitam o pico do início da hora.
- As duas execuções rodam `--catch-up`. Elas processam todo dia útil ANBIMA da janela de 5 dias úteis que a página pública guarda, a partir de 29/09/2026 (início do pipeline), que ainda não tenha saída ou cuja saída tenha usado a ETTJ de outro dia.
- **ETTJ de hoje ainda não publicada:** o dia fica pendente, sem erro, e a próxima execução tenta de novo.
- **Qualquer outra falha da ANBIMA** (fora do ar, layout novo, dado reprovado na validação, dia passado sem ETTJ): erro visível, workflow vermelho e a causa no log. Assim nenhum dia sai da janela em silêncio.
- Em dia não útil não há nada pendente, e o workflow termina sem publicar.

### Sequência (`.github/workflows/daily.yml`)

1. `uv sync --locked`
2. testes: ruff, mypy e pytest; teste falhando bloqueia
3. `python -m curvas.run --catch-up`
4. validação do schema
5. commit dos JSON e brutos (`[skip ci]`)
6. build do site
7. deploy no GitHub Pages

Um dia bloqueado (schema inválido, NaN, fator inválido, fonte sem nenhum dado válido, série fora da faixa plausível) faz o workflow falhar. Mesmo assim, os outros dias são publicados.

Reprodutibilidade (16.7): mesmos t0, brutos, configuração e CDS manual dão o mesmo JSON. A única exceção são os alertas de variação diária, que comparam com a saída do dia útil anterior, se ela existir.

Execução manual: aba Actions → **daily** → *Run workflow*. O campo `as_of` vazio faz a recuperação; com uma data, roda só aquela data-base.

### Credenciais

Nenhum segredo é necessário. As fontes são públicas, e o commit e o deploy usam o `GITHUB_TOKEN` automático, com as permissões declaradas em cada job.

### Configuração inicial do repositório (uma vez)

1. Criar o repositório **público** no GitHub (Q3) e enviar o branch `main`.
2. *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
3. Rodar o workflow **daily** à mão uma vez, para confirmar o acesso às fontes a partir dos servidores do GitHub.

### Cuidados

- **Inatividade:** em repositório público, o GitHub desativa workflows agendados depois de 60 dias sem atividade no repositório, e não está documentado se os commits do bot contam. Se o workflow for desativado, reative-o na aba Actions.
- **ANBIMA:** a página das curvas avisa que a aba será desligada e que as curvas ficarão só no ANBIMA Data (Q19). Se o download parar, o pipeline usa o último dado válido com alerta e os testes do coletor continuam passando com as respostas gravadas. O coletor terá de ser trocado.
- **CDS no site público (Q17):** com o Pages ligado, o `latest.json` e o site passam a exibir o CDS copiado do Investing.com, o que os termos dele vedam sem permissão. Resolver a Q17 (parecer jurídico ou autorização, Q16) antes de ligar o Pages.
- **Planilha legada:** é interna e fica fora do repositório (`docs/legado/*.xlsx` no `.gitignore`). Os testes que dependem dela são pulados quando ela não existe.
