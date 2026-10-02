# F3: diagnóstico da fonte do CDS Brasil (USD) — Q2

Pesquisa de 01/10/2026: 4 frentes, cada uma conferida por um verificador independente. Sem scraping, sem contornar bloqueios, sem criar contas e sem aceitar termos. Notas brutas em `scratch/f3/pesquisa/`.

## Conclusão

1. **Não construir coletor do Investing.com.** O risco jurídico é alto e o risco técnico também. Os termos proíbem coleta automatizada, e o site bloqueia clientes automatizados.
2. **Nenhuma fonte pública e gratuita** entrega a curva diária de CDS Brasil de 6M a 20A com permissão de uso automatizado e de exibição.
3. **Melhor rota licenciada fora de Bloomberg, LSEG e S&P: API da Cbonds.** Ela tem índices "CDS Brazil" com cálculo da ICE Data Derivatives e os mesmos vértices de hoje (mais 15A e 30A). Exibir no site exige contrato de redistribuição.
4. **Produção, por ora:** `data/manual/cds.csv`, preenchido pela equipe, com data, fonte e alerta de defasagem.
5. **Atenção jurídica:** pelos termos do Investing.com, até a prática atual (cópia manual para uso da empresa e publicação no site) é restrita (seções 10(a) e 14). Vale um parecer jurídico.

## Investing.com

| Item | Achado |
|---|---|
| Termos (PDF "Last Modified: August 2025", Fusion Media Ltd.) | §10(a): só uso pessoal, vedado uso comercial. §10(c): vedada extração automatizada. §10(h): vedado contornar restrições de acesso. §14: dados de mercado só para uso interno e não comercial, vedado exibir em site. §23: lei inglesa. [Termos](https://cdn.investing.com/about-us/terms_and_conditions.pdf) |
| API | Não existe. O próprio suporte cita os contratos com os provedores de dados. |
| Acesso automatizado | HTTP 403 (Cloudflare) até no `robots.txt`. Bibliotecas como investpy e investiny estão sem funcionar desde o Cloudflare. |
| Origem do dado | Os símbolos `BRGV5YUSAC=R` etc. seguem o formato de RIC da LSEG. É provável que a série seja o composto LSEG, mas isso não foi confirmado. |

## Rotas licenciadas

| Rota | O que entrega | Acesso | Custo | Observações |
|---|---|---|---|---|
| **Cbonds API** (recomendada para cotação) | Diária, em bps: 6M (13579), 1A (13641), 2A (13703), 3A (13765), 4A (13827), 5A (13889), 7A (13951), 10A (14013), 15A (14075), 20A (14137) e 30A (14199). Cálculo da ICE Data Derivatives, senioridade SNRFOR. | JSON/SOAP via HTTPS com login e senha (`ws.cbonds.info`), viável no GitHub Actions. O método de índices traz só os últimos 100 dias; o histórico vem por bulk. Limite de 30 requisições/min. Trial de cerca de 2 semanas. | Sem preço público ("depends on the volume of data and the scope of retransmission"). | O acordo de usuário do site (§7.2) restringe a uso interno, e citar em research é permitido com atribuição. Exibir no site exige licença "displaying mode", com anuência da ICE e por escrito. Confirmar moeda (USD), convenção do spread e horário de disponibilidade. |
| ICE Data Services (direto) | De 6M a 30A, EOD até intradiário, mais de 18 anos de histórico. | API, SFTP ou arquivos. | Enterprise, sem preço público. | É a fonte primária da Cbonds. |
| ICE Clear Credit (settlement) | Só o 5A, em **preço** (cupom 100 ou 500), não em spread. | Página pública; o histórico é licenciado via S&P/Markit. | 5A grátis na web. A tabela de 2014 (o PDF baixado por engano) não vale mais. | Termos proíbem uso para terceiros e montar base de dados. Serve só para conferência interna. Fica fora porque a licença passa pela S&P. |
| LSEG (DataScope Select, Datastream, platform session) | Composite CDS, provavelmente a mesma família que o Investing mostra. | Para servidor, só com licença própria; o Workspace desktop não roda no GitHub Actions. | Caro: Datastream de cerca de US$ 1.000 a 2.500 por usuário/mês (Vendr). | É a única que daria continuidade exata à série atual. |
| Bloomberg Data License, S&P/Markit, FactSet, Parameta | Curva completa. | Enterprise. | Caro e sem preço público. | Bloomberg e S&P estão fora da lista que você aceitou (sem licença hoje). |

## Fontes públicas (nenhuma serve como fonte da curva)

- **Só o 5A:**
  - worldgovernmentbonds (redistribui o Investing);
  - página gratuita da ICE Clear Credit (preço, uso interno);
  - MacroMicro (semanal, pago para baixar);
  - Tesouro, no RMD (mensal, em imagem; fonte Bloomberg).
- **Sem CDS:** BCB (SGS e dados abertos), ANBIMA, B3, FRED, Trading Economics, Twelve Data, FMP, Nasdaq Data Link, Barchart.
- **Proxies que exigiriam trocar a métrica:**
  - EMBI+ no Ipeadata (descontinuado em jul/2024);
  - SPA CRP (spread de bonds);
  - Damodaran e EODHD (anual).
- **Negócios reportados à SEC** (ICE Trade Vault, DTCC): negócio a negócio, sem curva de fechamento. Os termos proíbem montar base de dados.

## Recomendação

1. **Coletor manual (implementado na F3):** `data/manual/cds.csv` com data de referência, vértice, bps, fonte, quem preencheu e quando. O leitor valida o arquivo, usa o último conjunto completo até t0, marca `stale` com a data real e gera alertas (seção 12). Correção = nova linha com `preenchido_em` posterior. A primeira entrada (29/09/2026) é a da planilha; essa data é inferida da reconciliação das curvas, porque a planilha não registra quando o CDS foi copiado.
2. **Pedir cotação à Cbonds** (e, como comparação, à ICE). Escopo: os 9 índices (ou os 11, com 15A e 30A) via API, um bulk histórico e uma cláusula de exibição no site.
3. Se o contrato sair, o coletor da Cbonds entra como fonte primária, e o manual vira fallback. A troca de fornecedor quebra a série; por isso, gravar a coluna "fonte" e fazer o backfill com o mesmo fornecedor.
4. Levar ao jurídico o uso atual do Investing.com, inclusive a publicação no site.
