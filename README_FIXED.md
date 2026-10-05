# Pro Scalping MEXC — Logic Fix 1.1.0

This revision focuses on logic and real-account consistency.

## Important fixes

- Atomic, cross-process `settings.json` writes; the UI and background service no longer overwrite each other's keys through read/modify/write races.
- Manual real-position close is now actually consumed by the service.
- Existing real positions are persisted and managed after service restarts.
- Stop Scan stops new entries but does not abandon an already-open real position.
- Entry price uses the real average fill (`cummulativeQuoteQty / executedQty`) instead of the scanned candle price.
- Sell quantity is reconciled with the real free balance on MEXC.
- Market-buy logic honors MEXC's `quoteOrderQtyMarketAllowed`; when unavailable it falls back to quantity-based market buying using the symbol's base-size precision.
- Buy/sell responses are validated; zero-filled/error responses cannot become fake active trades.
- HTTP 5xx / network ambiguity is treated as UNKNOWN rather than retried blindly, reducing duplicate-order risk.
- Technical signals use the last closed candle.
- Volume compares the closed candle against the preceding 20 candles, excluding the signal candle from its own baseline.
- MACD is implemented as MACD(12,26,9), replacing the old synthetic `signal = macd * 0.9` logic.
- User-configurable Stop Loss and Max Profit / Take Profit percentages.
- Live Trades / Account screens show non-zero real balances from MEXC `/api/v3/account`.
- Windows can run the same service loop in a daemon thread.
- Android service packaging includes `pyjnius` and both ARM64 + ARMv7 architectures.

## Safety

This is real-money trading software. Test with a dedicated account and small size first. API keys should have only the permissions required for spot trading and should never be committed to Git.
