# TraderTim Gateway v0.2

This is the safety-controlled middle layer between an OpenAI agent and Robinhood Agentic Trading MCP.

## Architecture

OpenAI Agent -> TraderTim Gateway -> Robinhood Trading MCP -> Agentic 2

The model proposes trades. The gateway independently decides whether they are allowed.

## Enforced in code

- $100 POC framework
- no added-capital allowance
- one live position maximum
- four completed trades/session
- $3 daily realized-loss stop
- score-based $1/$0.75/$0.50/$0.25 risk ceilings
- whole-share sizing
- no stop widening
- 3:30 PM ET new-entry lockout
- 20% max-drawdown halt
- frozen 500-trade statistics
- >=50% win-rate + positive P&L + positive expectancy gate
- SHADOW by default
- model cannot enable LIVE_POC

## Current intentional blocker

The gateway does not accept a Robinhood username/password.

The upstream Robinhood MCP at:

https://agent.robinhood.com/mcp/trading

requires approved OAuth. The adapter accepts an OAuth bearer token only after a legitimate OAuth flow has produced one.

Your existing ChatGPT TraderTim connection's credential is not exported to this gateway.

Until upstream OAuth is configured, the package is fail-closed for Robinhood calls.

## Test

Core risk/state tests do not need Robinhood:

```bash
pip install pydantic pytest
pytest -q
```

## Full install

```bash
pip install .
```

Copy `.env.example` to your secret environment and keep:

`LIVE_POC_ENABLED=false`

Start:

```bash
python -m tradertim_gateway.server
```

The MCP endpoint is normally:

`https://YOUR_HOST/mcp`

## Two live locks

Live execution requires BOTH:

1. environment: `LIVE_POC_ENABLED=true`
2. persistent state: `LIVE_POC`

The agent has no tool to change either lock.

## Critical next integration test

Before any live POC, implement and verify the complete entry lifecycle:

1. submit entry
2. confirm actual fill
3. place broker-held protective stop for actual filled quantity
4. verify stop accepted
5. if stop placement fails, flatten immediately
6. manage target/time/EOD exit
7. reconcile closed position

v0.1 deliberately does not claim that lifecycle is complete yet.


## v0.2 lifecycle protections

v0.2 adds a tested entry-protection and exit lifecycle:

- entry submission is never treated as a fill
- actual cumulative fill quantity is polled
- partial fills cancel the unfilled remainder before protection
- a whole-share `stop_market` sell is placed for actual filled quantity
- target/time exits cancel and resolve the stop first
- if the stop fills while cancellation is racing, the gateway does **not** send a second sell
- position manager exposes one deterministic monitoring iteration

Live execution is still blocked until approved upstream Robinhood OAuth is configured and the lifecycle is integration-tested against Agentic 2.
