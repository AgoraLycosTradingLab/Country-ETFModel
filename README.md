# Country ETF Macro Allocator

This project is for research and educational purposes only.
It does not constitute investment advice.
All trading involves risk.

A systematic country-selection model that ranks **country equity ETFs** based on
**market-confirmed macro conditions**, using a combination of:

- Equity trend and momentum
- FX strength vs USD
- Curated macro data (policy rates, inflation, growth)
- Simple regime logic

The model is designed to be **robust, explainable, and dependency-light**, avoiding
brittle macro APIs (e.g. OECD SDMX) in favor of **market data + curated slow-moving macro**.

---

## Philosophy

> If macro conditions matter, they should show up in **FX and equities**.

This model prioritizes:
- Capital flow confirmation (FX)
- Local growth and policy pricing (equity ETFs)
- Slow, structural macro data entered manually from reliable sources
  (e.g. Trading Economics, World Bank)

The result is a **country allocation framework** suitable for:
- Global rotation strategies
- Top-down macro overlays
- Risk-on / risk-off country exposure selection

---

## Model Overview

### Inputs

#### Market Data (Automated)
- **Country ETFs** (Yahoo Finance)
- **FX vs USD** (Yahoo Finance)

#### Macro Data (Manual / Curated)
Stored in `data/Country ETF list.xlsx`:
- Policy rate (current, 3M ago)
- Inflation (YoY)
- Growth momentum (qualitative)
- FX regime (free float vs peg)
- Optional: current account, debt, risk flags

---

### Signals Used

| Category | Signal |
|--------|-------|
| Equity | 12M momentum, MA200 trend |
| FX | 3M + 12M FX momentum vs USD |
| Macro | Real rate (policy − inflation) |
| Policy | Rate change (tightening / easing) |
| Regime | FX peg adjustment, growth vetoes |

---

### Scoring Logic (High Level)

A country scores well when:
- Its equity ETF is **above MA200**
- Equity momentum is positive
- FX is strengthening vs USD
- Real rates are attractive or improving
- Monetary policy is not tightening into weak growth

Pegged currencies automatically **downweight FX signals**.


