from __future__ import annotations
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo
from .models import PocState, TradePlan, GuardDecision, ScoreBand, Mode

ET = ZoneInfo("America/New_York")
MAX_DAILY_LOSS = 3.00
MAX_DAILY_TRADES = 4
MAX_DRAWDOWN_PCT = 20.0
NO_NEW_ENTRIES_AFTER = time(15, 30)

def score_band(score: float) -> tuple[ScoreBand, float]:
    if score >= 80: return ScoreBand.A, 1.00
    if score >= 65: return ScoreBand.B, 0.75
    if score >= 50: return ScoreBand.C, 0.50
    return ScoreBand.D, 0.25

def drawdown_pct(peak: float, current: float) -> float:
    if peak <= 0: return 0.0
    return max(0.0, (peak-current)/peak*100.0)

def can_open_new_trade(
    state: PocState,
    plan: TradePlan,
    available_buying_power: float,
    now: datetime,
    live_poc_enabled: bool,
    account_reconciled: bool = True,
    protective_stop_supported: bool = True,
) -> GuardDecision:
    band, max_risk = score_band(plan.score)
    risk_per_share = round(plan.entry - plan.stop, 8)
    shares_by_risk = math.floor(max_risk / risk_per_share) if risk_per_share > 0 else 0
    shares_by_cash = math.floor(max(0.0, available_buying_power) / plan.entry)
    approved_shares = min(shares_by_risk, shares_by_cash)
    if plan.requested_shares is not None:
        approved_shares = min(approved_shares, plan.requested_shares)
    planned_risk = approved_shares * risk_per_share
    planned_cost = approved_shares * plan.entry
    notes: list[str] = []

    def out(ok: bool, live: bool, reason: str):
        return GuardDecision(
            approved=ok, live_allowed=live, reason_code=reason,
            score_band=band, max_risk_dollars=max_risk,
            risk_per_share=risk_per_share,
            shares_by_risk=shares_by_risk,
            shares_by_cash=shares_by_cash,
            approved_shares=max(0, approved_shares),
            planned_risk_dollars=max(0.0, round(planned_risk,4)),
            planned_cost_dollars=max(0.0, round(planned_cost,4)),
            notes=notes
        )

    if state.kill_switch: return out(False, False, "KILL_SWITCH")
    if state.poc_status.value in {"PASSED","FAILED","FAILED_DRAWDOWN"}:
        return out(False, False, "POC_NOT_ACTIVE")
    if state.additional_capital_added > 0:
        return out(False, False, "ADDITIONAL_CAPITAL_VIOLATION")
    if state.max_drawdown_pct > MAX_DRAWDOWN_PCT:
        return out(False, False, "DRAWDOWN_FAIL")
    if state.daily_realized_pnl <= -MAX_DAILY_LOSS:
        return out(False, False, "DAILY_LOSS_LIMIT")
    if state.daily_completed_trades >= MAX_DAILY_TRADES:
        return out(False, False, "DAILY_TRADE_LIMIT")
    if state.open_position_state.has_open_position:
        return out(False, False, "OPEN_POSITION_EXISTS")
    if not account_reconciled:
        return out(False, False, "RECONCILIATION_HALT")
    if not protective_stop_supported:
        return out(False, False, "PROTECTIVE_STOP_UNAVAILABLE")
    if now.astimezone(ET).time() >= NO_NEW_ENTRIES_AFTER:
        return out(False, False, "END_OF_DAY_LOCKOUT")
    if approved_shares < 1:
        return out(False, False, "RISK_GEOMETRY_FAIL")

    live_allowed = (
        live_poc_enabled and
        state.mode == Mode.LIVE_POC and
        state.poc_status.value == "RUNNING"
    )
    return out(True, live_allowed, "LIVE_ENTRY" if live_allowed else "SHADOW_ONLY")

def stop_change_allowed(old_stop: float, new_stop: float) -> bool:
    return new_stop >= old_stop
