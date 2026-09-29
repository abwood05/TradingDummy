from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from .models import PositionState
from .state_store import StateStore

OPEN_STATES={"new","queued","confirmed","unconfirmed","partially_filled","pending_cancelled"}
CLOSED_CANCEL_STATES={"cancelled","canceled","partially_filled_rest_cancelled"}
FILLED_STATES={"filled"}

def _data(x): return x.get("data",x)

def _orders(payload):
    d=_data(payload)
    return d.get("orders",[]) if isinstance(d,dict) else []

def first_order(payload):
    arr=_orders(payload)
    return arr[0] if arr else None

def order_id_from_place(payload):
    d=_data(payload)
    o=d.get("order") if isinstance(d,dict) else None
    if isinstance(o,dict):
        return o.get("id") or o.get("order_id")
    return None

def qty_float(v):
    try:return float(v or 0)
    except Exception:return 0.0

class ExecutionManager:
    def __init__(self,broker,store:StateStore,account_number:str):
        self.broker=broker; self.store=store; self.account=account_number

    async def protect_filled_entry(self, entry_order_id:str, planned_stop:float, planned_target:float,
                                   setup_type:str,score:float,candidate_rank:int,time_stop_minutes:int=35):
        """Poll a submitted entry. Once shares exist, cancel any unfilled remainder and install a stop."""
        result=await self.broker.get_order(self.account,entry_order_id)
        order=first_order(result)
        if not order:
            return {"ok":False,"reason_code":"ENTRY_ORDER_NOT_FOUND"}
        state=(order.get("state") or "").lower()
        filled=qty_float(order.get("cumulative_quantity"))
        requested=qty_float(order.get("quantity"))
        avg=qty_float(order.get("average_price") or order.get("price"))

        if state in {"rejected","failed","voided"} and filled<=0:
            return {"ok":False,"reason_code":"ENTRY_REJECTED","order_state":state}

        if state in OPEN_STATES and filled<=0:
            return {"ok":True,"status":"ENTRY_PENDING","order_state":state}

        # Partial fill: stop further entry exposure first.
        if filled>0 and requested>filled and state not in CLOSED_CANCEL_STATES and state not in FILLED_STATES:
            await self.broker.cancel_order(self.account,entry_order_id)
            return {"ok":True,"status":"ENTRY_PARTIAL_CANCEL_REQUESTED","filled_quantity":filled}

        # Only protect whole filled shares.
        whole=int(filled)
        if whole<1:
            return {"ok":False,"reason_code":"NO_WHOLE_FILLED_SHARES"}

        # Do not place a second protective stop if one already exists in local state.
        s=self.store.load()
        if s.open_position_state.stop_order_id:
            return {"ok":True,"status":"ALREADY_PROTECTED","stop_order_id":s.open_position_state.stop_order_id}

        stop_ref=str(uuid.uuid4())
        stop_payload={
            "account_number":self.account,
            "symbol":order.get("symbol"),
            "side":"sell",
            "type":"stop_market",
            "quantity":str(whole),
            "stop_price":f"{planned_stop:.4f}",
            "time_in_force":"gfd",
            "market_hours":"regular_hours",
            "ref_id":stop_ref,
        }
        try:
            stop_resp=await self.broker.place_order(stop_payload)
        except Exception as e:
            # Caller must immediately invoke emergency_flatten. Never claim protected.
            return {"ok":False,"reason_code":"STOP_PLACEMENT_EXCEPTION","emergency_flatten_required":True,"error":str(e)}

        stop_id=order_id_from_place(stop_resp)
        if not stop_id:
            return {"ok":False,"reason_code":"STOP_ID_MISSING","emergency_flatten_required":True,"stop_response":stop_resp}

        # Save live position only after stop submission returned an id.
        p=PositionState(
            has_open_position=True,
            symbol=order.get("symbol"),
            quantity=whole,
            entry_price=avg if avg>0 else None,
            stop_price=planned_stop,
            target_price=planned_target,
            entry_time=datetime.now(timezone.utc).isoformat(),
            time_stop_minutes=time_stop_minutes,
            position_state="INITIAL_RISK",
            entry_order_id=entry_order_id,
            stop_order_id=stop_id,
            setup_type=setup_type,
            candidate_rank=candidate_rank,
            score=score,
            trade_id=str(uuid.uuid4()),
        )
        s.open_position_state=p
        self.store.save(s)
        return {"ok":True,"status":"PROTECTED","stop_order_id":stop_id,"quantity":whole,"stop_price":planned_stop}

    async def emergency_flatten(self,symbol:str,quantity:int):
        """Best-effort emergency exit. Uses a regular-hours market sell because protection failed."""
        payload={
            "account_number":self.account,"symbol":symbol,"side":"sell","type":"market",
            "quantity":str(int(quantity)),"time_in_force":"gfd","market_hours":"regular_hours",
            "ref_id":str(uuid.uuid4())
        }
        resp=await self.broker.place_order(payload)
        return {"ok":True,"status":"EMERGENCY_EXIT_SUBMITTED","response":resp}

    async def _cancel_stop_and_resolve(self, stop_order_id:str):
        await self.broker.cancel_order(self.account,stop_order_id)
        current=first_order(await self.broker.get_order(self.account,stop_order_id))
        if not current:
            return {"safe_to_exit":False,"reason_code":"STOP_STATE_UNKNOWN"}
        state=(current.get("state") or "").lower()
        if state in FILLED_STATES:
            return {"safe_to_exit":False,"position_likely_flat":True,"reason_code":"STOP_FILLED_DURING_CANCEL"}
        if state in CLOSED_CANCEL_STATES:
            return {"safe_to_exit":True,"reason_code":"STOP_CANCELLED"}
        return {"safe_to_exit":False,"reason_code":"STOP_CANCEL_PENDING","state":state}

    async def request_planned_exit(self, reason:str, bid_price:float|None=None):
        """
        Race-safe target/time/EOD exit:
        cancel stop -> verify final stop state -> reconcile -> submit exit only if shares remain.
        """
        s=self.store.load(); p=s.open_position_state
        if not p.has_open_position:
            return {"ok":False,"reason_code":"NO_OPEN_POSITION"}
        if not p.stop_order_id:
            return {"ok":False,"reason_code":"UNPROTECTED_POSITION","emergency_flatten_required":True}

        resolved=await self._cancel_stop_and_resolve(p.stop_order_id)
        if not resolved.get("safe_to_exit"):
            return {"ok":True,"status":"WAIT_RECONCILE",**resolved}

        positions=_data(await self.broker.get_positions(self.account))
        rows=positions.get("positions",[]) if isinstance(positions,dict) else []
        row=next((x for x in rows if (x.get("symbol") or "").upper()==(p.symbol or "").upper()),None)
        qty=int(qty_float(row.get("quantity"))) if row else 0
        if qty<=0:
            p.has_open_position=False;p.position_state="NONE"
            self.store.save(s)
            return {"ok":True,"status":"ALREADY_FLAT_AFTER_CANCEL"}

        # Price-protected exit if bid is available; otherwise market regular-hours.
        if bid_price and bid_price>0:
            payload={
                "account_number":self.account,"symbol":p.symbol,"side":"sell","type":"limit",
                "quantity":str(qty),"limit_price":f"{bid_price:.4f}",
                "time_in_force":"gfd","market_hours":"regular_hours","ref_id":str(uuid.uuid4())
            }
        else:
            payload={
                "account_number":self.account,"symbol":p.symbol,"side":"sell","type":"market",
                "quantity":str(qty),"time_in_force":"gfd","market_hours":"regular_hours","ref_id":str(uuid.uuid4())
            }
        resp=await self.broker.place_order(payload)
        oid=order_id_from_place(resp)
        p.exit_order_id=oid;p.position_state="EXIT_PENDING"
        self.store.save(s)
        return {"ok":True,"status":"EXIT_SUBMITTED","reason":reason,"exit_order_id":oid,"response":resp}

    async def monitor(self, now:datetime|None=None):
        """One position-management iteration."""
        now=now or datetime.now(timezone.utc)
        s=self.store.load(); p=s.open_position_state
        if not p.has_open_position:
            return {"ok":True,"status":"FLAT"}

        # First see whether the protective stop already filled.
        stop=first_order(await self.broker.get_order(self.account,p.stop_order_id)) if p.stop_order_id else None
        if stop and (stop.get("state") or "").lower() in FILLED_STATES:
            p.position_state="EXIT_PENDING"
            self.store.save(s)
            return {"ok":True,"status":"STOP_FILLED_RECONCILE","stop_order":stop}

        q=_data(await self.broker.get_quotes([p.symbol]))
        results=q.get("results",[]) if isinstance(q,dict) else []
        quote=(results[0].get("quote") if results else {}) or {}
        bid=qty_float(quote.get("bid_price"))
        last=qty_float(quote.get("last_trade_price"))
        px=bid or last

        if p.target_price and px>=p.target_price:
            return await self.request_planned_exit("TARGET",bid or None)

        if p.entry_time:
            entered=datetime.fromisoformat(p.entry_time)
            if now>=entered+timedelta(minutes=p.time_stop_minutes):
                return await self.request_planned_exit("TIME_STOP",bid or None)

        return {"ok":True,"status":"HOLD","price":px,"target":p.target_price,"stop":p.stop_price}
