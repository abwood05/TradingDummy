from tradertim_gateway.state_store import StateStore
from tradertim_gateway.models import Mode,PocStatus

def test_500_trade_gate(tmp_path):
    st=StateStore(str(tmp_path/"s.json"))
    s=st.load(); s.mode=Mode.LIVE_POC; s.poc_status=PocStatus.RUNNING; st.save(s)
    for i in range(250): st.record_completed_trade(1.0,f"w{i}")
    for i in range(249): st.record_completed_trade(-0.5,f"l{i}")
    final=st.record_completed_trade(-0.5,"l249")
    assert final.real_completed_trades==500
    assert final.win_rate==0.5
    assert final.net_realized_pnl>0 and final.expectancy>0
    assert final.poc_status==PocStatus.PASSED

def test_drawdown_halt(tmp_path):
    st=StateStore(str(tmp_path/"s.json"))
    st.record_account_value(100)
    s=st.record_account_value(79)
    assert s.poc_status==PocStatus.FAILED_DRAWDOWN and s.kill_switch
