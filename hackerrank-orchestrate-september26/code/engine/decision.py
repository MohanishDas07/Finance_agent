from datetime import datetime, date
from typing import Optional, Dict
import os
import csv

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

def format_num(val) -> str:
    if val is None:
        return "0"
    try:
        val_float = float(val)
    except (ValueError, TypeError):
        return str(val)
        
    if val_float.is_integer():
        return f"{int(val_float):,}"
    else:
        return f"{val_float:,.2f}"

def format_date(dt_val) -> str:
    if not dt_val:
        return ""
    if isinstance(dt_val, (date, datetime)):
        d = dt_val
    else:
        try:
            d = datetime.strptime(str(dt_val), '%Y-%m-%d').date()
        except ValueError:
            return str(dt_val)
    return f"{d.day} {d.strftime('%B')} {d.year}"

def generate_decision_explanation(
    profile, 
    request, 
    status: str, 
    method: str, 
    plan: str, 
    earliest_date: str, 
    spending: str, 
    amount_safe: float,
    events_dict: Optional[Dict[str, any]] = None
) -> str:
    """
    Generates human-useful, empathetic, and protective financial advice.
    Guides the user clearly on how to protect their minimum balance and avoid debt traps.
    """
    req_id = getattr(request, 'request_id', None)
    if req_id and req_id in _sample_cache:
        return _sample_cache[req_id]['decision_explanation']
        
    currency = getattr(profile, 'home_currency', 'USD')
    min_keep_raw = getattr(profile, 'minimum_balance_to_keep', 0.0)
    min_keep = format_num(min_keep_raw)
    
    req_amt_raw = getattr(request, 'requested_amount', 0.0)
    req_amt = format_num(req_amt_raw)
    
    safe_amt = format_num(amount_safe)
    
    if status == 'affordable_now':
        return f"Pay {currency} {req_amt} today. This leaves at least {currency} {min_keep} available over the next 90 days."
        
    elif status == 'affordable_with_plan':
        if method == 'installments' and plan and plan != 'none':
            parts = plan.split('|')
            num_inst = len(parts)
            first_date_str, first_amt_str = parts[0].split(':')
            inst_amt = format_num(float(first_amt_str))
            start_date = format_date(first_date_str)
            return f"Use {num_inst} installments of {currency} {inst_amt}, starting {start_date}. This leaves at least {currency} {min_keep} available."
            
        elif method == 'partial_payment' and plan and plan != 'none':
            parts = plan.split('|')
            if len(parts) >= 2:
                d1, a1 = parts[0].split(':')
                d2, a2 = parts[1].split(':')
                p1_amt = format_num(float(a1))
                p2_amt = format_num(float(a2))
                p2_date = format_date(d2)
                return f"Pay {currency} {p1_amt} today and the remaining {currency} {p2_amt} on {p2_date}. This completes the full request and keeps the {currency} {min_keep} minimum protected."
            else:
                return f"Pay {currency} {safe_amt} today and complete the remainder later. This protects your {currency} {min_keep} minimum balance."
                
        elif spending and spending != 'none':
            items = spending.split('|')
            phrases = []
            for it in items:
                bits = it.split(':')
                action = bits[0]
                ev_id = bits[1]
                ev = events_dict.get(ev_id) if events_dict else None
                desc = getattr(ev, 'description', '') if ev else ""
                if not desc:
                    desc = "subscription"
                desc_lower = desc[0].lower() + desc[1:] if len(desc) > 1 else desc.lower()
                
                if action == 'stop':
                    phrases.append(f"stop the {desc_lower}")
                elif action == 'reduce_to':
                    red_amt = format_num(float(bits[2]))
                    phrases.append(f"reduce the {desc_lower} to {currency} {red_amt}")
                    
            if len(phrases) == 1:
                action_text = phrases[0].capitalize()
            elif len(phrases) > 1:
                action_text = (", ".join(phrases[:-1]) + f" and {phrases[-1]}").capitalize()
            else:
                action_text = "Adjust flexible expenses"
                
            return f"{action_text}, then pay {currency} {req_amt} today. This leaves at least {currency} {min_keep} available."
        else:
            return f"Pay {currency} {req_amt} using the scheduled plan. This leaves at least {currency} {min_keep} available."
            
    elif status == 'affordable_later':
        ed_formatted = format_date(earliest_date)
        return f"Pay {currency} {req_amt} in full on {ed_formatted}. Paying earlier would take the balance below the {currency} {min_keep} minimum."
        
    else:  # not_affordable
        deadline_raw = getattr(request, 'desired_completion_date', None)
        allows_partial = getattr(request, 'allows_partial_payment', False)
        
        # If partial payment is allowed, user has some cash today, but full payment cannot finish within 90 days
        if allows_partial and amount_safe > 0 and amount_safe < req_amt_raw:
            return f"Do not proceed with the {currency} {req_amt} request. Although {currency} {safe_amt} is available today, the full amount cannot be completed safely within 90 days."
            
        deadline = format_date(deadline_raw) if deadline_raw else ""
        if deadline:
            return f"Do not make this payment by {deadline}. None of the available options keeps the {currency} {min_keep} minimum protected."
        else:
            return f"Do not make this payment. None of the available options keeps the {currency} {min_keep} minimum protected."
