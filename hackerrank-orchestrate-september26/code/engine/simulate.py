from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple

from ingestion.models import FinancialEvent, RequestData, FinancialProfile

class Simulator:
    def __init__(self, ledger: List[FinancialEvent], profile: FinancialProfile, request: RequestData):
        self.ledger = ledger
        self.profile = profile
        self.request = request
        self.forecast_days = 90
        
        # We will build a daily balance curve
        self.daily_balances = {}
        self._build_baseline_curve()
        
    def _build_baseline_curve(self):
        """
        Calculates the baseline end-of-day balance for every day in the 90-day forecast.
        """
        current_balance = self.profile.current_available_balance
        
        # Group events by date
        events_by_date = {}
        for e in self.ledger:
            dt = e.settlement_date if e.settlement_date else e.event_date
            if not dt: dt = e.event_date
            if dt not in events_by_date:
                events_by_date[dt] = []
            events_by_date[dt].append(e)
            
        cur_date = self.request.request_date
        end_date = cur_date + timedelta(days=self.forecast_days)
        
        while cur_date <= end_date:
            day_net = 0.0
            if cur_date in events_by_date:
                for e in events_by_date[cur_date]:
                    amt = e.amount if e.amount is not None else 0.0
                    if e.direction == 'debit':
                        day_net -= amt
                    else:
                        day_net += amt
            
            current_balance += day_net
            self.daily_balances[cur_date] = current_balance
            cur_date += timedelta(days=1)
            
    def get_amount_safe_to_pay(self) -> float:
        """
        The largest amount payable on request_date before any spending changes,
        such that balance never falls below minimum_balance_to_keep.
        """
        min_future_balance = min(self.daily_balances.values())
        safe_margin = min_future_balance - self.profile.minimum_balance_to_keep
        
        if safe_margin <= 0:
            return 0.0
            
        return round(min(self.request.requested_amount, safe_margin), 4)
        
    def get_earliest_date_for_full_payment(self) -> Optional[date]:
        """
        The earliest date at which paying the full requested_amount as one lump sum
        keeps the balance safe from that date through end of forecast.
        A payment on date D reduces balance[D..end] by requested_amount.
        """
        cur_date = self.request.request_date
        end_date = cur_date + timedelta(days=self.forecast_days)
        
        while cur_date <= end_date:
            # Check: if we pay on cur_date, does balance stay >= min_keep from cur_date to end?
            safe = True
            check_date = cur_date
            while check_date <= end_date:
                if self.daily_balances[check_date] - self.request.requested_amount < self.profile.minimum_balance_to_keep:
                    safe = False
                    break
                check_date += timedelta(days=1)
                
            if safe:
                return cur_date
                
            cur_date += timedelta(days=1)
            
        return None
        
    def check_plan_safety(self, payment_schedule: List[Tuple[date, float]]) -> Tuple[bool, float]:
        """
        Given a list of (date, amount) payments, check if the plan is safe.
        Returns (is_safe, minimum_balance_breach_amount)
        If is_safe is True, breach_amount is 0.0.
        If is_safe is False, breach_amount is the maximum amount by which the balance fell below the minimum.
        """
        # copy daily balances
        sim_balances = dict(self.daily_balances)
        
        for p_date, p_amt in payment_schedule:
            # apply payment to all days from p_date onwards
            if p_date < self.request.request_date or p_date > self.request.request_date + timedelta(days=self.forecast_days):
                continue
                
            d = p_date
            end_date = self.request.request_date + timedelta(days=self.forecast_days)
            while d <= end_date:
                sim_balances[d] -= p_amt
                d += timedelta(days=1)
                
        min_bal = min(sim_balances.values())
        if min_bal < self.profile.minimum_balance_to_keep:
            return False, round(self.profile.minimum_balance_to_keep - min_bal, 4)
            
        return True, 0.0
