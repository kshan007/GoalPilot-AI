# Free/Public Data Source Review

Date checked: 2026-10-10

## AMFI / SEBI Mutual Fund Data

- Source reviewed: SEBI curated list of mutual-fund and RTA resources, including AMFI scheme details and latest NAV/NAV history pages.
- URL: https://www.sebi.gov.in/curation/mutual_funds_and_rtas.html
- Potential fields: scheme details, NAV history, AUM, category-level mutual fund data.
- Integration status: documented only; no live API call added.
- Limitation: NAV history is data, not a personalized recommendation engine. Historical NAV/returns are not forecasts.

## NSE / Nifty Indices

- Source reviewed: Nifty Indices historical reports page and NIFTY 50 index information.
- URLs: https://www.niftyindices.com/reports and https://www.nseindia.com/static/products-services/indices-nifty50-index
- Potential fields: index open/high/low/close and total return index values where available.
- Integration status: existing project CSV fixture is used offline.
- Limitation: index history supports scenario assumptions and benchmarking only; it is not stock-picking advice.

## RBI WALR / Lending Rates

- Source reviewed: RBI lending-rate page describing base-rate tables and WALR tables.
- URL: https://m.rbi.org.in/rbi-sourcefiles/lendingrate/lendingrates.aspx
- Potential fields: bank group weighted average lending rates for outstanding and fresh rupee loans.
- Integration status: existing project WALR/market-credit artifacts are used offline.
- Limitation: WALR is aggregate reference data, not a lender offer or approval.

## MoSPI CPI API

- Source reviewed: CPI API user manual.
- URL: https://api.mospi.gov.in/API/CPI%20API%20User%20Manual.pdf
- Potential fields: CPI index and inflation records by year/month/group/sector.
- Integration status: not live-integrated because complete access requires signup/login/token flow. Existing CPI fixture data is used offline.
- Limitation: CPI is an inflation input, not a guarantee of future goal-cost inflation.

## Offline Fixtures Added

- `data/offline_funding_options.json` contains deterministic investment, loan, savings, and economic-scenario records.
- Loan fixtures are labelled synthetic and are not lender quotes.
- Savings/deposit fixtures are labelled assumptions and are not current verified product rates.
- Investment fixtures are modelling candidates/proxies and are not recommendations.
