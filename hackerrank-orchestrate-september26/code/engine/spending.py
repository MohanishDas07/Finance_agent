from typing import List, Tuple, Dict
from datetime import date, timedelta

from ingestion.models import FinancialEvent, FinancialProfile
from engine.simulate import Simulator

def solve_spending_changes(
    simulator: Simulator, 
    breach_amount: float, 
    payment_schedule: List[Tuple[date, float]]
) -> List[str]:
    """
    Finds up to 3 spending changes to cover the breach_amount.
    Returns a list of change strings like ["stop:event_1", "reduce_to:event_2:100"]
    or [] if no solution exists.
    """
    # 1. Gather all flexible events from the ledger
    # They must happen BEFORE or ON the dates where the balance breaches, but 
    # to simplify, any reduction in a recurring event's amount raises the balance curve from that day forward.
    # We just need the total savings from the changes to lift the minimum balance curve above the threshold.
    
    # Actually, a single 'stop:event_1' applies to that specific event_id. 
    # If it's a recurring event, does stopping it stop ALL future occurrences?
    # "stop:<event_id>" targets a specific event_id. But our projected events have synthetic IDs!
    # Wait, the problem says "spending_changes_needed may contain up to three changes ... stop:<event_id>".
    # Since projected events don't have real IDs in the input dataset, we must target the ORIGINAL event_id that spawned the projection!
    # Wait, the problem statement says "target the event_id". 
    # If we target the original event_id, stopping it effectively stops the recurring series.
    # Let's map our ledger events back to their root event_ids.
    
    # We will look at all future events in the ledger. 
    # But wait, we can only stop/reduce things that are actually in the 90-day forecast.
    
    candidates = []
    
    for e in simulator.ledger:
        if e.direction != 'debit': continue
        if e.flexibility == 'fixed': continue
        if e.category in simulator.profile.expense_categories_to_protect: continue
        
        # original event ID. For projected events, we prefixed 'projected_{root_id}_{date}'.
        # Let's extract the root ID.
        root_id = e.event_id
        if root_id.startswith('projected_'):
            parts = root_id.split('_')
            # projected_event_123_20240405
            root_id = f"{parts[1]}_{parts[2]}"
            
        # Can we stop it?
        can_stop = False
        if e.flexibility == 'stoppable' and e.category in simulator.profile.expense_categories_user_is_willing_to_stop:
            can_stop = True
            
        # Can we reduce it?
        can_reduce = False
        if e.flexibility == 'reducible' and e.category in simulator.profile.expense_categories_user_is_willing_to_reduce:
            can_reduce = True
            
        if not can_stop and not can_reduce:
            continue
            
        # How much does this save?
        # A single occurrence saves `e.amount`. 
        # If we reduce it to minimum_allowed_amount, it saves `e.amount - e.minimum_allowed_amount`.
        # Note: If it's recurring, it might hit multiple times in 90 days. 
        # For simplicity, we just evaluate the savings of changing the SERIES.
        
        candidates.append({
            'root_id': root_id,
            'event': e,
            'can_stop': can_stop,
            'can_reduce': can_reduce,
            'amount': e.amount,
            'min_amount': e.minimum_allowed_amount if e.minimum_allowed_amount is not None else 0.0,
            'date': e.settlement_date if e.settlement_date else e.event_date
        })
        
    # Group candidates by root_id, because stopping/reducing the root_id applies to all its occurrences
    series_savings = {}
    for c in candidates:
        rid = c['root_id']
        if rid not in series_savings:
            series_savings[rid] = {
                'root_id': rid,
                'can_stop': c['can_stop'],
                'can_reduce': c['can_reduce'],
                'total_amount': 0.0,
                'total_min_amount': 0.0,
                # We need to simulate the exact daily impact.
                # A change saves money ON AND AFTER its date.
                'occurrences': []
            }
        series_savings[rid]['total_amount'] += c['amount']
        series_savings[rid]['total_min_amount'] += c['min_amount']
        series_savings[rid]['occurrences'].append((c['date'], c['amount'], c['min_amount']))
        
    # We need to find a combination of up to 3 actions (stop or reduce) that fixes the breach.
    # This is a small search space. We can brute force it.
    
    actions = []
    for rid, data in series_savings.items():
        if data['can_stop']:
            actions.append({'type': 'stop', 'root_id': rid, 'occurrences': data['occurrences']})
        if data['can_reduce'] and data['total_amount'] > data['total_min_amount']:
            actions.append({'type': 'reduce', 'root_id': rid, 'occurrences': data['occurrences']})
            
    # Brute force combinations of size 1, 2, 3
    import itertools
    
    for r in range(1, 4):
        for combo in itertools.combinations(actions, r):
            # Check for mutually exclusive (cannot stop and reduce the same root_id)
            root_ids = [act['root_id'] for act in combo]
            if len(root_ids) != len(set(root_ids)):
                continue
                
            # Simulate this combination
            # We add the savings to the daily balances and check if min_balance is met.
            sim_balances = dict(simulator.daily_balances)
            
            # First, apply the payment schedule
            for p_date, p_amt in payment_schedule:
                d = p_date
                end_date = simulator.request.request_date + timedelta(days=simulator.forecast_days)
                while d <= end_date:
                    sim_balances[d] -= p_amt
                    d += timedelta(days=1)
                    
            # Now apply the savings
            for act in combo:
                for occ_date, occ_amt, occ_min in act['occurrences']:
                    saving = occ_amt if act['type'] == 'stop' else (occ_amt - occ_min)
                    d = occ_date
                    end_date = simulator.request.request_date + timedelta(days=simulator.forecast_days)
                    while d <= end_date:
                        if d in sim_balances:
                            sim_balances[d] += saving
                        d += timedelta(days=1)
                        
            if min(sim_balances.values()) >= simulator.profile.minimum_balance_to_keep:
                # We found a valid combination!
                # Format the output strings
                changes = []
                for act in combo:
                    if act['type'] == 'stop':
                        changes.append(f"stop:{act['root_id']}")
                    else:
                        # For reduce, we must specify the new amount.
                        # We use the minimum_allowed_amount of the first occurrence
                        new_amt = act['occurrences'][0][2]
                        changes.append(f"reduce_to:{act['root_id']}:{new_amt}")
                return changes
                
    return []
