import pytest
from pathlib import Path
from tradertim_gateway.state_store import StateStore
from tradertim_gateway.execution import ExecutionManager
from tradertim_gateway.models import PositionState

class FakeBroker:
    def __init__(self):
        self.orders={}
        self.positions=[]
        self.quotes={}
        self.placed=[]
        self.cancelled=[]

    async def get_order(self,a,oid):
        o=self.orders.get(oid)
        return {"data":{"orders":[o] if o else []}}

    async def place_order(self,p):
        self.placed.append(p)
        oid=f"placed-{len(self.placed)}"
        o={"id":oid,"symbol":p["symbol"],"state":"confirmed","quantity":p.get("quantity","0"),
           "cumulative_quantity":"0","type":p["type"]}
        self.orders[oid]=o
        return {"data":{"order":o}}

    async def cancel_order(self,a,oid):
        self.cancelled.append(oid)
        o=self.orders[oid]
        # Fake immediate cancel unless test pre-marks as filled.
        if o["state"]!="filled": o["state"]="cancelled"
        return {"data":{"accepted":True}}

    async def get_positions(self,a):
        return {"data":{"positions":self.positions}}

    async def get_quotes(self,symbols):
        s=symbols[0];q=self.quotes.get(s,{"bid_price":"0","last_trade_price":"0"})
        return {"data":{"results":[{"quote":q}]}}

@pytest.mark.asyncio
async def test_filled_entry_installs_stop(tmp_path):
    b=FakeBroker(); st=StateStore(str(tmp_path/"s.json")); ex=ExecutionManager(b,st,"A")
    b.orders["e1"]={"id":"e1","symbol":"F","state":"filled","quantity":"2",
                    "cumulative_quantity":"2","average_price":"12.00"}
    r=await ex.protect_filled_entry("e1",11.6,12.5,"Momentum Continuation",82,1)
    assert r["status"]=="PROTECTED"
    assert b.placed[-1]["type"]=="stop_market"
    assert b.placed[-1]["side"]=="sell"
    assert b.placed[-1]["quantity"]=="2"
    assert st.load().open_position_state.stop_order_id

@pytest.mark.asyncio
async def test_partial_fill_cancels_remainder_before_stop(tmp_path):
    b=FakeBroker(); st=StateStore(str(tmp_path/"s.json")); ex=ExecutionManager(b,st,"A")
    b.orders["e1"]={"id":"e1","symbol":"F","state":"partially_filled","quantity":"3",
                    "cumulative_quantity":"1","average_price":"12.00"}
    r=await ex.protect_filled_entry("e1",11.6,12.5,"Momentum Continuation",82,1)
    assert r["status"]=="ENTRY_PARTIAL_CANCEL_REQUESTED"
    assert "e1" in b.cancelled
    assert not b.placed

@pytest.mark.asyncio
async def test_target_exit_cancels_stop_then_exits(tmp_path):
    b=FakeBroker(); st=StateStore(str(tmp_path/"s.json")); ex=ExecutionManager(b,st,"A")
    b.orders["s1"]={"id":"s1","symbol":"F","state":"confirmed","quantity":"1","cumulative_quantity":"0"}
    b.positions=[{"symbol":"F","quantity":"1"}]
    b.quotes["F"]={"bid_price":"12.60","last_trade_price":"12.61"}
    s=st.load();s.open_position_state=PositionState(
        has_open_position=True,symbol="F",quantity=1,entry_price=12.0,stop_price=11.6,target_price=12.5,
        entry_time="2026-09-29T14:00:00+00:00",stop_order_id="s1",position_state="INITIAL_RISK"
    );st.save(s)
    r=await ex.monitor()
    assert r["status"]=="EXIT_SUBMITTED"
    assert b.cancelled==["s1"]
    assert b.placed[-1]["side"]=="sell"
    assert b.placed[-1]["type"]=="limit"

@pytest.mark.asyncio
async def test_stop_fill_race_prevents_second_sell(tmp_path):
    class RaceBroker(FakeBroker):
        async def cancel_order(self,a,oid):
            self.cancelled.append(oid)
            self.orders[oid]["state"]="filled"
            self.orders[oid]["cumulative_quantity"]="1"
            return {"data":{"accepted":True}}
    b=RaceBroker(); st=StateStore(str(tmp_path/"s.json")); ex=ExecutionManager(b,st,"A")
    b.orders["s1"]={"id":"s1","symbol":"F","state":"confirmed","quantity":"1","cumulative_quantity":"0"}
    b.positions=[{"symbol":"F","quantity":"1"}]
    s=st.load();s.open_position_state=PositionState(
        has_open_position=True,symbol="F",quantity=1,entry_price=12,stop_price=11.6,target_price=12.5,
        entry_time="2026-09-29T14:00:00+00:00",stop_order_id="s1",position_state="INITIAL_RISK"
    );st.save(s)
    r=await ex.request_planned_exit("TARGET",12.6)
    assert r["reason_code"]=="STOP_FILLED_DURING_CANCEL"
    assert not b.placed
