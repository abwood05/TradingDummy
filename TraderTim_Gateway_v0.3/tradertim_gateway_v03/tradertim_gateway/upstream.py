import json, os
from typing import Any

class UpstreamAuthRequired(RuntimeError): pass

class RobinhoodMCPClient:
    def __init__(self,url=None,bearer_token=None):
        self.url=url or os.getenv("ROBINHOOD_MCP_URL","https://agent.robinhood.com/mcp/trading")
        self.bearer_token=bearer_token or os.getenv("ROBINHOOD_MCP_BEARER_TOKEN")

    def _headers(self):
        if not self.bearer_token:
            raise UpstreamAuthRequired("Robinhood OAuth bearer token not configured. Never use a Robinhood password.")
        return {"Authorization":f"Bearer {self.bearer_token}"}

    async def call_tool(self,name:str,args:dict[str,Any]):
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async with httpx.AsyncClient(headers=self._headers(),timeout=30.0) as client:
            async with streamable_http_client(self.url,http_client=client) as streams:
                r,w=streams[0],streams[1]
                async with ClientSession(r,w) as session:
                    await session.initialize()
                    result=await session.call_tool(name,arguments=args)
                    structured=getattr(result,"structuredContent",None)
                    if structured is not None:return structured
                    content=getattr(result,"content",[]) or []
                    if content and hasattr(content[0],"text"):
                        try:return json.loads(content[0].text)
                        except Exception:return {"text":content[0].text}
                    return {"raw":str(result)}

    async def get_portfolio(self,a):return await self.call_tool("get_portfolio",{"account_number":a})
    async def get_positions(self,a):return await self.call_tool("get_equity_positions",{"account_number":a})
    async def get_orders(self,a):return await self.call_tool("get_equity_orders",{"account_number":a})
    async def get_order(self,a,oid):return await self.call_tool("get_equity_orders",{"account_number":a,"order_id":oid})
    async def get_quotes(self,symbols):return await self.call_tool("get_equity_quotes",{"symbols":symbols})
    async def run_scan(self,s):return await self.call_tool("run_scan",{"scan_id":s})
    async def review_order(self,p):return await self.call_tool("review_equity_order",p)
    async def place_order(self,p):return await self.call_tool("place_equity_order",p)
    async def cancel_order(self,a,oid):return await self.call_tool("cancel_equity_order",{"account_number":a,"order_id":oid})
