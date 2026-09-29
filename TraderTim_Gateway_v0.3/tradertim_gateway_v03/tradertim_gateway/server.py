from __future__ import annotations
import os
from .models import TradePlan
from .service import TraderTimService
from mcp.server.fastmcp import FastMCP

TOKEN=os.getenv("GATEWAY_BEARER_TOKEN","")
if len(TOKEN)<24:
    raise RuntimeError("GATEWAY_BEARER_TOKEN must be a long random secret (>=24 chars).")

mcp=FastMCP(
    "TraderTim Gateway",
    instructions=(
        "Bounded TraderTim V1.0 safety gateway. "
        "Defaults to SHADOW. The model cannot enable LIVE_POC."
    )
)
svc=TraderTimService()

@mcp.tool()
async def gateway_status()->dict:
    """Read-only POC/risk status."""
    return await svc.status()

@mcp.tool()
async def reconcile_account()->dict:
    """Read-only broker reconciliation."""
    return await svc.reconcile()

@mcp.tool()
async def run_candidate_scan()->dict:
    """Run the saved TraderTim candidate scan. Read-only."""
    return await svc.run_candidate_scan()

@mcp.tool()
async def preview_trade_plan(
    symbol:str,score:float,setup_type:str,entry:float,stop:float,target:float,
    candidate_rank:int,rationale:str="",requested_shares:int|None=None,
    time_stop_minutes:int=35
)->dict:
    """Risk validation only. Never places an order."""
    p=TradePlan(symbol=symbol,score=score,setup_type=setup_type,entry=entry,stop=stop,
                target=target,candidate_rank=candidate_rank,rationale=rationale,
                requested_shares=requested_shares,time_stop_minutes=time_stop_minutes)
    return await svc.preview_trade_plan(p)

@mcp.tool()
async def execute_trade_plan(
    symbol:str,score:float,setup_type:str,entry:float,stop:float,target:float,
    candidate_rank:int,rationale:str="",requested_shares:int|None=None,
    time_stop_minutes:int=35
)->dict:
    """Request bounded execution. Gateway may force SHADOW_ONLY."""
    p=TradePlan(symbol=symbol,score=score,setup_type=setup_type,entry=entry,stop=stop,
                target=target,candidate_rank=candidate_rank,rationale=rationale,
                requested_shares=requested_shares,time_stop_minutes=time_stop_minutes)
    return await svc.execute_trade_plan(p)

@mcp.tool()
async def protect_entry(
    entry_order_id:str,planned_stop:float,planned_target:float,setup_type:str,
    score:float,candidate_rank:int,time_stop_minutes:int=35
)->dict:
    """Verify actual fill quantity and install the broker-held stop."""
    return await svc.protect_entry(
        entry_order_id,planned_stop,planned_target,setup_type,score,candidate_rank,time_stop_minutes
    )

@mcp.tool()
async def monitor_position()->dict:
    """One deterministic position-management iteration."""
    return await svc.monitor_position()


class BearerAuthMiddleware:
    def __init__(self,app,token:str):
        self.app=app
        self.expected=("Bearer "+token).encode()

    async def __call__(self,scope,receive,send):
        if scope["type"]=="http":
            path=scope.get("path","")
            # health is deliberately non-sensitive and unauthenticated.
            if path not in {"/health","/health/"}:
                headers=dict(scope.get("headers") or [])
                auth=headers.get(b"authorization",b"")
                if auth!=self.expected:
                    body=b'{"error":"unauthorized"}'
                    await send({"type":"http.response.start","status":401,
                                "headers":[(b"content-type",b"application/json"),
                                           (b"content-length",str(len(body)).encode())]})
                    await send({"type":"http.response.body","body":body})
                    return
        await self.app(scope,receive,send)


class HealthWrapper:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope["type"]=="http" and scope.get("path") in {"/health","/health/"}:
            body=b'{"status":"ok","service":"tradertim-gateway"}'
            await send({"type":"http.response.start","status":200,
                        "headers":[(b"content-type",b"application/json"),
                                   (b"content-length",str(len(body)).encode())]})
            await send({"type":"http.response.body","body":body})
            return
        await self.app(scope,receive,send)


# Standard remote MCP app, normally mounted at /mcp.
app=HealthWrapper(BearerAuthMiddleware(mcp.streamable_http_app(),TOKEN))

def main():
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","8000")))

if __name__=="__main__": main()
