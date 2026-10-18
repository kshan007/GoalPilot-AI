# API and Data Source Register

Every external source the platform touches, what it is, what it costs, what it may legally be
used for, and whether access was **actually tested** from this build host on 2026-10-17.

Status vocabulary (used verbatim in the handoff):

| Status | Meaning |
|---|---|
| **Verified Live** | Retrieved successfully from this host during the build, no credentials |
| **Verified Download** | A file/endpoint that was downloaded and parsed successfully |
| **Fixture Only** | Implemented and tested against a recorded fixture; live call not verified |
| **Configured but Untested** | Code path exists and is wired, but no key/credential was supplied |
| **Unavailable** | Attempted and failed (with the reason), or blocked by policy |

---

## 1. Economic and market data

### 1.1 AMFI — public daily NAV file
| Field | Value |
|---|---|
| Provider | Association of Mutual Funds in India (AMFI) |
| Documentation | https://www.amfiindia.com/ |
| Endpoint | `https://www.amfiindia.com/spages/NAVAll.txt` (plain text, `;`-delimited) |
| Class | Public data file published by an industry body; no authentication |
| Pricing / quota | Free. No published rate limit; the client fetches once per cache window |
| Fields | scheme code, ISIN(s), scheme name, plan, option, latest NAV, NAV date |
| Not provided | expense ratio, exit load, minimum investment, historical series |
| Update frequency | Daily (business days) |
| Tested | **Verified Live** — 1,833 direct-growth records parsed, NAV date 2026-10-16 |
| Fallback | Labelled `category_scenario` rows; the page still explains categories |

### 1.2 NSE — index snapshot
| Field | Value |
|---|---|
| Provider | National Stock Exchange of India |
| Endpoint | `https://www.nseindia.com/api/allIndices` |
| Class | Public market page feed. Redistribution may be restricted by NSE terms — used for a single displayed index level, not redistributed as a data product |
| Auth | None observed; a browser-like UA and Referer are sent |
| Tested | **Verified Live** — NIFTY 50 level returned |
| Fallback | `unavailable`; the UI then shows only the historical series |

### 1.3 NIFTY 50 history (local)
| Field | Value |
|---|---|
| Source | Project research dataset `datasets/GoalPilot_AI/extracted_features/nifty_monthly_features.csv`, derived from NIFTY 50 closes |
| Class | Historical observations already in the repository |
| Tested | **Verified Download** (read locally; 141 monthly observations, 2015-01 → 2026-09) |
| Use | Descriptive statistics only: volatility, drawdown, trailing CAGR. Never used as an expected return |

### 1.4 RBI — weighted average lending rate
| Field | Value |
|---|---|
| Provider | Reserve Bank of India |
| Local artefact | `datasets/GoalPilot_AI/extracted_features/walr_features.csv` |
| Class | Historical aggregate series (RBI source), already calibrated in the research tree |
| Units | Per cent per annum; monthly; system-wide, all scheduled commercial banks |
| Tested | **Verified Download** (read locally; latest observation reported with its month) |
| Use | Reference benchmark only. Not a product rate, not an offer |
| Fallback | Provider reports `unavailable`; no benchmark shown rather than a guessed one |

### 1.5 Government small savings (DEA / NSI)
| Field | Value |
|---|---|
| Provider | Department of Economic Affairs, Ministry of Finance |
| Official URL | https://dea.gov.in/ (small-savings scheme page) |
| Class | Official government publication; no API |
| Tested | **Unavailable** — TLS certificate chain is not trusted by this host, and TLS verification was deliberately **not** disabled. `dea.gov.in/small-saving-scheme` also returns 404 |
| Workaround | Curated, source-annotated snapshot of the rates that were cross-checked from published reporting of the Q3 FY2026-27 notification (PPF 7.1%, SSY 8.2%, SCSS 8.2%). NSC and KVP were **not** verified and are therefore absent |
| Maintenance | Re-verify against the official quarterly notification; `effective_from` and `curated_at` are surfaced in the API |

---

## 2. Investment history (optional)

### 2.1 mfapi.in
| Field | Value |
|---|---|
| Provider | api.mfapi.in — a free community mirror of AMFI NAV history |
| Documentation | https://www.mfapi.in/ |
| Endpoint | `https://api.mfapi.in/mf/{scheme_code}` |
| Class | Third-party public API, no key. **Not** an AMFI service |
| Pricing / quota | Free; no published SLA. Called for at most 6 schemes per discovery request, with a 6 s timeout |
| Fields | date + NAV series, scheme meta |
| Tested | **Verified Live** — series returned for a known scheme code |
| Labelling | Every enriched record is marked `unofficial_mirror`, and the attribution travels with the data |
| Fallback | Returns omitted; the option is still listed without a return series |
| Toggle | `GOALPILOT_ENABLE_MFAPI_HISTORY=false` disables it entirely |

---

## 3. Lending products

### 3.1 ICICI Bank — personal loan
| Field | Value |
|---|---|
| URL | https://www.icicibank.com/personal-banking/loans/personal-loan |
| Class | Public product page (lender's own disclosure) |
| Extracted | Advertised "starting at 9.99%" and maximum amount, plus the quoted sentence |
| Tested | **Verified Live** on 2026-10-17 |
| Not extracted | processing fee, tenure range, APR (not stated verbatim) |
| Fallback | Bundled snapshot (`official_snapshot`) with its own retrieval date |

### 3.2 Axis Bank — personal loan
| Field | Value |
|---|---|
| URL | https://www.axisbank.com/retail/loans/personal-loan/features-benefits |
| Tested | **Verified Live** on 2026-10-17 — "starting at 9.99% p.a." |
| Fallback | Snapshot |

### 3.3 Bank of Baroda — personal loan
| Field | Value |
|---|---|
| URL | https://www.bankofbaroda.in/personal-banking/loans/personal-loan |
| Tested | **Verified Live** on 2026-10-17 — rate published in the page's description metadata ("11% p.a.") |
| Note | The extractor reads description metadata as well as body text; the matched sentence is returned as evidence |
| Fallback | Snapshot |

### 3.4 Attempted and unavailable
| Lender | URL | Result |
|---|---|---|
| State Bank of India | `sbi.co.in` rates path | HTTP 404 on the current domain structure |
| Punjab National Bank | `pnbindia.in/personal-loan.html` | Page served, but no rate present in the HTML (client-rendered) |
| HDFC Bank | product page | HTTP 403 to non-browser clients |

No substitute rate was invented for any of these.

### 3.5 Loan aggregators / credit bureaus
**Not integrated by design.** No authorised aggregator or bureau API was available to this
project, and none is claimed. `app/providers/loans.py` defines the provider interface a future
authorised connection would implement, and the user-supplied-quote path covers the analysis
needs without one.

---

## 4. Language model

### 4.1 Google Gemini
| Field | Value |
|---|---|
| Provider | Google (Gemini API) — the **only** proprietary AI service used |
| SDK | Official `google-genai` Python SDK |
| Auth | `GEMINI_API_KEY` in the backend environment only |
| Model | Configurable via `GOALPILOT_GEMINI_MODEL` (default `gemini-2.5-flash`) |
| Structured output | `response_mime_type='application/json'`, then validated server-side against a Pydantic schema |
| Tested | **Verified Live** 2026-10-17 — one generation, `used: true`, schema-valid, 26.6 s |
| Fallback | Deterministic explanation built from computed values, flagged in the response's `llm` block |
| Cost control | One call per generation, 45 s timeout, no retries that could double-bill |

---

## 5. Cross-cutting rules applied to every source

1. **No invented values.** A field a source does not publish is `null`, never estimated in place.
2. **No silent staleness.** `retrieved_at`, `effective_date` and a computed `freshness` travel with
   every record.
3. **Failure isolation.** A provider exception becomes `status: unavailable` with a reason; the
   rest of the application — profile, goals, LP, RL, hybrid, stored data — keeps working.
4. **Caching, not persistence, for external payloads.** A 6-hour in-process TTL cache prevents
   hammering a source; it is never written to the database, so there is only one source of truth
   for user data.
5. **No credentials in source control.** See `.env.example` for placeholders only.
6. **No scraping behind access controls.** Nothing here bypasses authentication, and the one host
   with an untrusted certificate chain was left unfetched rather than fetched insecurely.
