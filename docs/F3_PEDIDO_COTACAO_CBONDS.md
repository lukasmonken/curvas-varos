# Pedido de cotação à Cbonds (rascunho para a equipe enviar)

Contexto: Q2 e `docs/F3_DIAGNOSTICO_CDS.md`. Canal sugerido: o formulário de contato da página da API (https://cbonds.com/api/) ou o comercial da Cbonds. Antes de enviar, ajuste remetente, assinatura e o uso pretendido.

---

**Subject:** Quote request – API access to "CDS Brazil" indices (ICE Data Derivatives), incl. display rights

Hello,

We are VAROS, an investment research company in Brazil. We would like a quote for daily API access to the Brazil sovereign CDS indices on Cbonds (calculating organization: ICE Data Derivatives):

| Tenor | Cbonds index ID |
|---|---|
| 6M | 13579 |
| 1Y | 13641 |
| 2Y | 13703 |
| 3Y | 13765 |
| 4Y | 13827 |
| 5Y | 13889 |
| 7Y | 13951 |
| 10Y | 14013 |
| 20Y | 14137 |
| (optional) 15Y, 30Y | 14075, 14199 |

Scope:

1. Daily end-of-day values via the Cbonds API (JSON over HTTPS), consumed by an automated job running on GitHub Actions (cloud runners, no fixed IP).
2. A one-off historical backfill of the same indices, as far back as available.
3. **Display rights:** publication of the values (and of annual figures derived from them) on our website / client platform, with attribution to Cbonds and ICE as required. Please tell us whether this requires a separate redistribution license and whether ICE must also approve it.

Questions:

- Currency and convention: are these USD-denominated contracts (SNRFOR, CR14)? Are the values par spreads in bps, mid quotes? Is bid/ask available?
- At what time (Brazil time) is the end-of-day value for a given date available through the API?
- Does the 100-day limit of `get_index_value_new` apply to these indices, and how is the history delivered?
- Do you require IP whitelisting for API access?
- Is a trial possible for these 9–11 instruments?
- Pricing for: (a) internal use only; (b) internal use plus public display on our website.

Thank you,

[nome, cargo, VAROS, e-mail, telefone]
