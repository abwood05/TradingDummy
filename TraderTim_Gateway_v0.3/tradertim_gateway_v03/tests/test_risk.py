from datetime import datetime
from zoneinfo import ZoneInfo
from tradertim_gateway.models import PocState,TradePlan,Mode,PocStatus
from tradertim_gateway.risk import can_open_new_trade,stop_change_allowed
ET=ZoneInfo("America/New_York")
def mkplan(score=80,entry=10,stop=9.5,target=10.625):
    return TradePlan(symbol="TEST",score=score,setup_type="Momentum Continuation",
                     entry=entry,stop=stop,target=target,candidate_rank=1)
def mkstate():
    s=PocState(); s.mode=Mode.LIVE_POC; s.poc_status=PocStatus.RUNNING; return s
def at(h,m=0): return datetime(2026,9,29,h,m,tzinfo=ET)

def test_a_band_risk():
    d=can_open_new_trade(mkstate(),mkplan(85,10,9.5,10.625),100,at(10),True)
    assert d.live_allowed and d.approved_shares==2 and d.planned_risk_dollars==1.0

def test_low_score_still_can_trade():
    d=can_open_new_trade(mkstate(),mkplan(40,10,9.8,10.25),100,at(10),True)
    assert d.live_allowed and d.approved_shares==1

def test_risk_geometry_fail():
    d=can_open_new_trade(mkstate(),mkplan(40,40,38,42.5),100,at(10),True)
    assert d.reason_code=="RISK_GEOMETRY_FAIL"

def test_daily_loss():
    s=mkstate(); s.daily_realized_pnl=-3
    assert can_open_new_trade(s,mkplan(),100,at(10),True).reason_code=="DAILY_LOSS_LIMIT"

def test_open_position():
    s=mkstate(); s.open_position_state.has_open_position=True
    assert can_open_new_trade(s,mkplan(),100,at(10),True).reason_code=="OPEN_POSITION_EXISTS"

def test_eod_lock():
    assert can_open_new_trade(mkstate(),mkplan(),100,at(15,31),True).reason_code=="END_OF_DAY_LOCKOUT"

def test_shadow_mode_blocks_live():
    s=mkstate(); s.mode=Mode.SHADOW
    d=can_open_new_trade(s,mkplan(),100,at(10),True)
    assert d.approved and not d.live_allowed and d.reason_code=="SHADOW_ONLY"

def test_env_switch_blocks_live():
    d=can_open_new_trade(mkstate(),mkplan(),100,at(10),False)
    assert d.approved and not d.live_allowed

def test_stop_never_widens():
    assert stop_change_allowed(9.5,9.6)
    assert not stop_change_allowed(9.5,9.4)
