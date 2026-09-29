from pathlib import Path
from threading import RLock
from .models import PocState, Mode, PocStatus
from .risk import drawdown_pct, MAX_DRAWDOWN_PCT

class StateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        if not self.path.exists():
            self.save(PocState())

    def load(self) -> PocState:
        with self.lock:
            return PocState.model_validate_json(self.path.read_text())

    def save(self, state: PocState):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(state.model_dump_json(indent=2))
            tmp.replace(self.path)

    def record_account_value(self, value: float) -> PocState:
        s = self.load()
        s.current_account_value = value
        s.peak_account_value = max(s.peak_account_value, value)
        s.max_drawdown_pct = max(s.max_drawdown_pct, drawdown_pct(s.peak_account_value, value))
        if s.max_drawdown_pct > MAX_DRAWDOWN_PCT:
            s.poc_status = PocStatus.FAILED_DRAWDOWN
            s.mode = Mode.HALTED
            s.kill_switch = True
        self.save(s)
        return s

    def record_completed_trade(self, pnl: float, trade_id: str) -> PocState:
        s = self.load()
        s.real_completed_trades += 1
        s.daily_completed_trades += 1
        s.net_realized_pnl = round(s.net_realized_pnl + pnl, 6)
        s.daily_realized_pnl = round(s.daily_realized_pnl + pnl, 6)
        s.last_trade_id = trade_id
        if pnl > 0:
            s.wins += 1; s.gross_wins += pnl
            s.current_streak = s.current_streak+1 if s.current_streak >= 0 else 1
            s.longest_win_streak = max(s.longest_win_streak, s.current_streak)
        elif pnl < 0:
            s.losses += 1; s.gross_losses += abs(pnl)
            s.current_streak = s.current_streak-1 if s.current_streak <= 0 else -1
            s.longest_loss_streak = max(s.longest_loss_streak, abs(s.current_streak))
        else:
            s.breakevens += 1; s.current_streak = 0

        total = s.real_completed_trades
        s.win_rate = s.wins/total if total else 0
        s.avg_win = s.gross_wins/s.wins if s.wins else 0
        s.avg_loss = s.gross_losses/s.losses if s.losses else 0
        loss_rate = s.losses/total if total else 0
        s.expectancy = s.win_rate*s.avg_win - loss_rate*s.avg_loss
        s.profit_factor = s.gross_wins/s.gross_losses if s.gross_losses > 0 else None

        if total >= 500:
            passed = (
                s.win_rate >= .50 and s.net_realized_pnl > 0 and s.expectancy > 0
                and s.max_drawdown_pct <= 20 and s.additional_capital_added <= 0
            )
            s.poc_status = PocStatus.PASSED if passed else PocStatus.FAILED
            s.mode = Mode.POC_COMPLETE if passed else Mode.HALTED
            s.kill_switch = not passed
        self.save(s)
        return s
