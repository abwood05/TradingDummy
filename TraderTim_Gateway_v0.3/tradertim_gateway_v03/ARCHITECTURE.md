# TraderTim Gateway Trust Model

## Model layer
Ranks candidates and proposes:
- symbol
- score
- setup
- entry
- stop
- target

It cannot change risk constants or enable live trading.

## Gateway layer
Authoritative safety kernel:
- sizing
- daily loss gate
- drawdown gate
- single-position gate
- time lock
- POC bookkeeping
- live/shadow lock

## Broker layer
Robinhood remains source of truth for:
- buying power
- positions
- orders
- fills

## Fail-closed rule
Any auth, data, reconciliation, or protective-stop uncertainty blocks a new live entry.
