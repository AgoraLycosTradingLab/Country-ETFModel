# Country-ETFModel
Ranks country ETFs by market-confirmed macro conditions: equity trend &amp; momentum, FX strength vs USD (regime-aware), and curated policy/inflation inputs. The output is a relative Top-10 list of countries with the most supportive conditions for allocation right now.


Simple model outline
Load a universe of country ETFs with curated macro data (rates, inflation, FX regime).
Pull ETF prices and FX rates vs USD.
Compute signals: equity momentum & trend, FX momentum, real rates.
Apply regime rules and gates.
Score, rank, and output the top-10 most favorable countries/ETFs.
