import os, uuid
from datetime import datetime, timezone
from .models import TradePlan, Mode, PocStatus
from .risk import can_open_new_trade
from .state_store import StateStore
from .upstream import RobinhoodMCPClient
from .execution import ExecutionManager, order_id_from_place

def _data(x): return x.get("data",x)

class TraderTimService:
    def __init__(self, broker=None, store=None):
        self.broker = broker or RobinhoodMCPClient()
        self.store = store or StateStore(os.getenv("STATE_PATH","/tmp/tradertim_state.json"))
        self.account_number = os.getenv("ROBINHOOD_AGENTIC_ACCOUNT_NUMBER","")
        self.scan_id = os.getenv("TRADERTIM_SCAN_ID","af8b7362-54b1-4bd2-a100-ee189edf010b")
        self.live_enabled = os.getenv("LIVE_POC_ENABLED","false").lower()=="true"
        self.execution = ExecutionManager(self.broker,self.store,self.account_number) if self.account_number else None

    async def status(self):
        s=self.store.load()
        return s.model_dump() | {"live_poc_environment_enabled":self.live_enabled}

    async def run_candidate_scan(self):
        return await self.broker.run_scan(self.scan_id)

    async def reconcile(self):
        if not self.account_number:
            return {"ok":False,"reason_code":"ACCOUNT_NOT_CONFIGURED"}
        p=await self.broker.get_portfolio(self.account_number)
        pos=await self.broker.get_positions(self.account_number)
        orders=await self.broker.get_orders(self.account_number)
        pd=_data(p)
        self.store.record_account_value(float(pd.get("total_value",0) or 0))
        s=self.store.load()
        s.last_reconciliation_timestamp=datetime.now(timezone.utc).isoformat()
        self.store.save(s)
        return {"ok":True,"portfolio":p,"positions":pos,"orders":orders}

    async def preview_trade_plan(self, plan:TradePlan):
        rec=await self.reconcile()
        if not rec.get("ok"):
            return {"approved":False,"reason_code":"RECONCILIATION_HALT"}
        pd=_data(rec["portfolio"])
        bp=float((pd.get("buying_power") or {}).get("buying_power",0) or 0)
        g=can_open_new_trade(
            self.store.load(),plan,bp,datetime.now(timezone.utc),
            self.live_enabled,True,True
        )
        return {"guard":g.model_dump(),"plan":plan.model_dump()}

    async def execute_trade_plan(self, plan:TradePlan):
        preview=await self.preview_trade_plan(plan)
        g=preview.get("guard") or {}
        if not g.get("live_allowed"):
            s=self.store.load()
            s.shadow_trade_count += 1
            s.last_decision_reason=g.get("reason_code","SHADOW_ONLY")
            self.store.save(s)
            return {"executed":False,"shadow":True,**preview}

        shares=int(g["approved_shares"])
        ref=str(uuid.uuid4())
        payload={
            "account_number":self.account_number,
            "symbol":plan.symbol.upper(),"side":"buy","type":"limit",
            "quantity":str(shares),"limit_price":f"{plan.entry:.4f}",
            "time_in_force":"gfd","market_hours":"regular_hours","ref_id":ref
        }
        entry=await self.broker.place_order(payload)
        entry_order_id=order_id_from_place(entry)
        return {
            "executed":True,
            "entry_order_submitted":True,
            "entry_order":entry,
            "entry_order_id":entry_order_id,
            "protective_stop_pending_fill_confirmation":True,
            "planned_stop":plan.stop,
            "planned_target":plan.target,
            "approved_shares":shares,
            "entry_ref_id":ref,
            "lifecycle_note":"Call protect_entry after fill/partial-fill state changes. Live POC must not treat submission as a fill."
        }

    async def protect_entry(self,entry_order_id:str,planned_stop:float,planned_target:float,
                            setup_type:str,score:float,candidate_rank:int,time_stop_minutes:int=35):
        if not self.execution: return {"ok":False,"reason_code":"ACCOUNT_NOT_CONFIGURED"}
        return await self.execution.protect_filled_entry(
            entry_order_id,planned_stop,planned_target,setup_type,score,candidate_rank,time_stop_minutes
        )

    async def monitor_position(self):
        if not self.execution: return {"ok":False,"reason_code":"ACCOUNT_NOT_CONFIGURED"}
        return await self.execution.monitor()

    def operator_set_mode(self,mode:Mode):
        s=self.store.load()
        if mode==Mode.LIVE_POC:
            if not self.live_enabled: raise RuntimeError("LIVE_POC_ENABLED=false")
            if s.kill_switch: raise RuntimeError("Kill switch active")
            s.poc_status=PocStatus.RUNNING
        s.mode=mode
        self.store.save(s)
        return s.model_dump()
