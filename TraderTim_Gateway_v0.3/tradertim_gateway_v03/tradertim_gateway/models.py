from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Optional

class Mode(str, Enum):
    BUILD="BUILD"; SHADOW="SHADOW"; LIVE_POC="LIVE_POC"; HALTED="HALTED"; POC_COMPLETE="POC_COMPLETE"

class PocStatus(str, Enum):
    NOT_STARTED="NOT_STARTED"; RUNNING="RUNNING"; PASSED="PASSED"; FAILED="FAILED"; FAILED_DRAWDOWN="FAILED_DRAWDOWN"

class ScoreBand(str, Enum):
    A="A"; B="B"; C="C"; D="D"

class TradePlan(BaseModel):
    symbol:str=Field(min_length=1,max_length=12)
    score:float=Field(ge=0,le=100)
    setup_type:str
    entry:float=Field(gt=0)
    stop:float=Field(gt=0)
    target:float=Field(gt=0)
    requested_shares:int|None=Field(default=None,ge=1)
    candidate_rank:int=Field(ge=1)
    rationale:str=""
    time_stop_minutes:int=Field(default=35,ge=1,le=120)

    @model_validator(mode="after")
    def geometry(self):
        if self.stop>=self.entry: raise ValueError("Long stop must be below entry")
        if self.target<=self.entry: raise ValueError("Long target must be above entry")
        return self

class GuardDecision(BaseModel):
    approved:bool
    live_allowed:bool
    reason_code:str
    score_band:ScoreBand
    max_risk_dollars:float
    risk_per_share:float
    shares_by_risk:int
    shares_by_cash:int
    approved_shares:int
    planned_risk_dollars:float
    planned_cost_dollars:float
    notes:list[str]=[]

class PositionState(BaseModel):
    has_open_position:bool=False
    symbol:Optional[str]=None
    quantity:int=0
    entry_price:Optional[float]=None
    stop_price:Optional[float]=None
    target_price:Optional[float]=None
    entry_time:Optional[str]=None
    time_stop_minutes:int=35
    position_state:str="NONE"
    entry_order_id:Optional[str]=None
    stop_order_id:Optional[str]=None
    exit_order_id:Optional[str]=None
    setup_type:Optional[str]=None
    candidate_rank:Optional[int]=None
    score:Optional[float]=None
    trade_id:Optional[str]=None

class PocState(BaseModel):
    strategy_version:str="TraderTim V1.0"
    mode:Mode=Mode.SHADOW
    poc_status:PocStatus=PocStatus.NOT_STARTED
    starting_capital:float=100.0
    additional_capital_added:float=0.0
    current_account_value:float=100.0
    peak_account_value:float=100.0
    max_drawdown_pct:float=0.0
    real_completed_trades:int=0
    wins:int=0; losses:int=0; breakevens:int=0
    win_rate:float=0.0
    net_realized_pnl:float=0.0
    avg_win:float=0.0; avg_loss:float=0.0; expectancy:float=0.0
    profit_factor:float|None=None
    longest_win_streak:int=0; longest_loss_streak:int=0; current_streak:int=0
    daily_realized_pnl:float=0.0; daily_completed_trades:int=0
    last_trade_id:str|None=None
    open_position_state:PositionState=PositionState()
    kill_switch:bool=False
    config_hash:str=""
    last_reconciliation_timestamp:str|None=None
    shadow_trade_count:int=0
    last_decision_reason:str|None=None
    strategy_reset_count:int=0
    gross_wins:float=0.0; gross_losses:float=0.0
