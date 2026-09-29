# No-download deployment path

You can deploy this gateway from a browser-based Git repository/cloud host; no software needs to be installed on the computer where you are configuring the OpenAI agent.

## Required secrets

Never put these in the repository:
- GATEWAY_BEARER_TOKEN
- ROBINHOOD_MCP_BEARER_TOKEN
- ROBINHOOD_AGENTIC_ACCOUNT_NUMBER

Keep LIVE_POC_ENABLED=false until the complete integration test passes.

## OpenAI Agent -> Gateway

The final remote MCP URL is:

https://YOUR-GATEWAY-HOST/mcp

The gateway now enforces:

Authorization: Bearer <GATEWAY_BEARER_TOKEN>

OpenAI's Agents API supports supplying this bearer authorization directly on an HTTP MCP connection.

If the visual Agent Builder's advanced credential screen accepts the static access token, use the gateway token as the access token. This specific UI path still needs to be verified before relying on it.

## Current blocker before Robinhood calls

The gateway's upstream client expects an approved OAuth bearer token for Robinhood's official MCP.

Robinhood's official endpoint is:

https://agent.robinhood.com/mcp/trading

Robinhood documents interactive OAuth authentication for MCP clients. Do not substitute account passwords or unofficial web-session scraping.

## Health check

GET /health

should return a non-sensitive service status without authorization.

Every MCP request requires the bearer token.

## Rollout

1. Deploy with LIVE_POC_ENABLED=false.
2. Connect OpenAI agent to gateway.
3. Confirm unauthorized MCP calls get HTTP 401.
4. Confirm authorized connection lists gateway tools.
5. Complete approved Robinhood OAuth for the gateway.
6. Run read-only reconciliation and scanner tests.
7. Run SHADOW stress tests.
8. Integration-test entry fill -> stop install -> target/time exit.
9. Fund Agentic 2 with exactly the intended $100 POC bankroll.
10. Only then flip LIVE_POC_ENABLED=true and use operator control to enter LIVE_POC.
