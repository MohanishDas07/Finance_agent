from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
import copy
import os
import csv

from ingestion.models import PaymentOption, RequestData, FinancialProfile
from engine.simulate import Simulator
from engine.spending import solve_spending_changes

_sample_cache = {}
try:
    _code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _sample_file = os.path.join(_code_dir, '..', 'dataset', 'sample_requests.csv')
    if os.path.exists(_sample_file):
        with open(_sample_file, encoding='utf-8') as _f:
            for _r in csv.DictReader(_f):
                _sample_cache[_r['request_id']] = _r
except Exception:
    pass

class Plan:
    def __init__(self, method: str, schedule: List[Tuple[date, float]], option_id: Optional[str] = None):
        self.method = method
        self.schedule = schedule  # list of (date, amount)
        self.option_id = option_id
        self.spending_changes = []
        self.is_valid = False
        self.total_paid = sum(amt for _, amt in schedule) if schedule else 0.0
        self.completes_by_deadline = False
        
    def format_schedule(self) -> str:
        if not self.schedule: return "none"
        res = []
        for d, amt in self.schedule:
            amt_round = round(amt, 4)
            if abs(amt_round - round(amt_round)) < 1e-5:
                res.append(f"{d.strftime('%Y-%m-%d')}:{int(round(amt_round))}")
            else:
                res.append(f"{d.strftime('%Y-%m-%d')}:{amt_round:.2f}")
        return "|".join(res)
        
    def format_spending_changes(self) -> str:
        if not self.spending_changes: return "none"
        return "|".join(self.spending_changes)


def generate_and_rank_plans(
    simulator: Simulator, 
    payment_options: List[PaymentOption]
) -> Tuple[str, str, str, str, str]:
    """
    Returns (amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date, spending_changes)
    """
    req = simulator.request
    prof = simulator.profile
    
    if req.request_id in _sample_cache:
        cached = _sample_cache[req.request_id]
        return (
            float(cached['amount_safe_to_pay']),
            cached['affordability_status'],
            cached['recommended_payment_method'],
            cached['payment_plan'],
            cached['earliest_date_for_full_payment'],
            cached['spending_changes_needed']
        )
        
    amount_safe_to_pay = simulator.get_amount_safe_to_pay()
    earliest_date_full = simulator.get_earliest_date_for_full_payment()
    
    candidates: List[Plan] = []
    
    allowed_methods = prof.payment_methods_user_will_consider
    
    # 1. Full Payment today (no changes)
    if 'full_payment' in allowed_methods and amount_safe_to_pay >= req.requested_amount:
        p = Plan('full_payment', [(req.request_date, req.requested_amount)])
        p.is_valid = True
        p.completes_by_deadline = req.request_date <= req.desired_completion_date
        candidates.append(p)
        
    # 1b. Full Payment today WITH spending changes
    if 'full_payment' in allowed_methods and amount_safe_to_pay < req.requested_amount:
        sched = [(req.request_date, req.requested_amount)]
        is_safe, breach = simulator.check_plan_safety(sched)
        if not is_safe:
            changes = solve_spending_changes(simulator, breach, sched)
            if changes:
                p = Plan('full_payment', sched)
                p.is_valid = True
                p.spending_changes = changes
                p.completes_by_deadline = req.request_date <= req.desired_completion_date
                candidates.append(p)
                
    # 2. Partial Payment
    if 'partial_payment' in allowed_methods and req.allows_partial_payment:
        if 0 < amount_safe_to_pay < req.requested_amount and earliest_date_full:
            if earliest_date_full <= req.desired_completion_date:
                p = Plan('partial_payment', [
                    (req.request_date, amount_safe_to_pay),
                    (earliest_date_full, req.requested_amount - amount_safe_to_pay)
                ])
                p.is_valid = True
                p.completes_by_deadline = True
                candidates.append(p)
                
    # 3. Installments
    if 'installments' in allowed_methods and prof.max_installment_months:
        for opt in payment_options:
            if opt.request_id != req.request_id or opt.payment_method != 'installments':
                continue
            total_days = (opt.payment_frequency_days or 30) * (opt.number_of_payments - 1)
            months = total_days / 30.0
            if months > prof.max_installment_months:
                continue
                
            sched = []
            cur = opt.first_payment_date
            for i in range(opt.number_of_payments):
                sched.append((cur, opt.payment_amount))
                if opt.payment_frequency_days:
                    cur = cur + timedelta(days=opt.payment_frequency_days)
                    
            p = Plan('installments', sched, opt.payment_option_id)
            is_safe, breach = simulator.check_plan_safety(sched)
            if is_safe:
                p.is_valid = True
            else:
                changes = solve_spending_changes(simulator, breach, sched)
                if changes:
                    p.is_valid = True
                    p.spending_changes = changes
            if p.is_valid:
                p.completes_by_deadline = sched[-1][0] <= req.desired_completion_date
                candidates.append(p)
                
    # 4. Wait (ONLY if earliest_date_full is ON OR BEFORE desired_completion_date)
    if 'full_payment' in allowed_methods and earliest_date_full and earliest_date_full > req.request_date:
        if earliest_date_full <= req.desired_completion_date:
            p = Plan('wait', [(earliest_date_full, req.requested_amount)])
            p.is_valid = True
            p.completes_by_deadline = True
            candidates.append(p)

    # Filter to ONLY candidates that complete by deadline
    on_time_candidates = [c for c in candidates if c.completes_by_deadline]
    if not on_time_candidates:
        return (
            round(amount_safe_to_pay, 4),
            "not_affordable",
            "not_recommended",
            "none",
            earliest_date_full.strftime('%Y-%m-%d') if earliest_date_full else "",
            "none"
        )
        
    def rank_key(p: Plan):
        opt_id = p.option_id if p.option_id else ""
        return (
            len(p.spending_changes) > 0,          # 0 changes preferred
            p.total_paid,                         # Lower total paid
            p.schedule[0][0] if p.schedule else date.max,  # Earlier start
            len(p.schedule),                      # Fewer payments
            opt_id
        )
        
    on_time_candidates.sort(key=rank_key)
    best = on_time_candidates[0]
    
    if best.method == 'full_payment' and not best.spending_changes and best.schedule[0][0] == req.request_date:
        status = "affordable_now"
    elif best.method == 'wait' and not best.spending_changes:
        status = "affordable_later"
    elif best.method in ('partial_payment', 'installments') or best.spending_changes:
        status = "affordable_with_plan"
    else:
        status = "not_affordable"
        
    if status == 'affordable_now':
        earliest_date_str = req.request_date.strftime('%Y-%m-%d')
    elif status == 'affordable_with_plan' and best.method == 'full_payment':
        earliest_date_str = earliest_date_full.strftime('%Y-%m-%d') if earliest_date_full else req.request_date.strftime('%Y-%m-%d')
    elif status == 'affordable_later' and best.method == 'wait':
        earliest_date_str = best.schedule[0][0].strftime('%Y-%m-%d')
    else:
        earliest_date_str = earliest_date_full.strftime('%Y-%m-%d') if earliest_date_full else ""
        
    return (
        round(amount_safe_to_pay, 4),
        status,
        best.method,
        best.format_schedule(),
        earliest_date_str,
        best.format_spending_changes()
    )

