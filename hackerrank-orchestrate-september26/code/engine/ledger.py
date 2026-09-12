from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import statistics

from ingestion.models import FinancialEvent, RequestData, FinancialProfile

def resolve_event_chains(events: List[FinancialEvent]) -> List[FinancialEvent]:
    """
    Resolve linked_event_id chains. A later event supersedes an earlier one.
    Returns the set of leaf events (final state).
    """
    # Create mapping of linked_event_id -> event (child)
    # The parent is event.linked_event_id
    superseded_by: Dict[str, str] = {}
    event_dict = {e.event_id: e for e in events}
    
    for e in events:
        if e.linked_event_id:
            superseded_by[e.linked_event_id] = e.event_id
            
    # Keep only events that are not superseded by anything
    final_events = []
    for e in events:
        if e.event_id not in superseded_by:
            final_events.append(e)
            
    return final_events

def _find_cadence(dates):
    """
    Given a sorted list of dates, try to find a consistent cadence.
    Returns (cadence_days, cadence_months, filtered_dates) or (None, None, None).
    """
    if len(dates) < 2:
        return None, None, None
    
    from dateutil.relativedelta import relativedelta
    
    diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
    avg_diff = sum(diffs) / len(diffs)
    
    # Try 1: strict consistency check
    if (max(diffs) - min(diffs)) <= 5:
        if 25 <= avg_diff <= 35:
            return None, 1, dates
        else:
            return round(avg_diff), None, dates
            
    # Try 1b: Semi-monthly check (e.g. 9, 22, 9, 22) -> avg around 15
    if 13 <= avg_diff <= 17 and len(diffs) >= 3:
        # Check if pairs of diffs sum to ~30
        is_semi = True
        for i in range(len(diffs)-1):
            if not (25 <= diffs[i] + diffs[i+1] <= 35):
                # If a pair doesn't sum to ~30, maybe they are just 14-day biweekly
                if not (12 <= diffs[i] <= 16):
                    is_semi = False
        if is_semi:
            return 15, None, dates # approx 15 days
            
    # Try 2: Find the most common interval range and filter to only those
    monthly_count = sum(1 for d in diffs if 25 <= d <= 35)
    # Also consider exact multiples of months as monthly (e.g. 91 is ~3 months)
    for d in diffs:
        if d > 35 and d % 30 <= 5 or d % 30 >= 25:
            if 55 <= d <= 65 or 85 <= d <= 95:
                monthly_count += 1
                
    if monthly_count >= 2 and monthly_count >= len(diffs) * 0.5:
        filtered_dates = [dates[0]]
        for i in range(1, len(dates)):
            diff = (dates[i] - filtered_dates[-1]).days
            if 25 <= diff <= 35:
                filtered_dates.append(dates[i])
            elif 55 <= diff <= 65 or 85 <= diff <= 95:
                # Big gap - but it's a multiple of months, so we can keep it as part of the monthly pattern
                # The next date just jumps forward.
                filtered_dates.append(dates[i])
            elif diff > 35:
                # Irregular big gap - reset
                if len(filtered_dates) < 3:
                    filtered_dates = [dates[i]]
                    
        if len(filtered_dates) >= 3:
            return None, 1, filtered_dates
    
    # Try 3: Find best consistent subsequence
    from collections import Counter
    rounded_diffs = [round(d / 3) * 3 for d in diffs]
    most_common = Counter(rounded_diffs).most_common(1)
    if most_common:
        target = most_common[0][0]
        target_count = most_common[0][1]
        if target_count >= 2:
            filtered_dates = [dates[0]]
            for i in range(1, len(dates)):
                diff = (dates[i] - filtered_dates[-1]).days
                if abs(diff - target) <= 3:
                    filtered_dates.append(dates[i])
                elif diff > target + 5:
                    if len(filtered_dates) < 3:
                        filtered_dates = [dates[i]]
                        
            if len(filtered_dates) >= 3:
                filtered_diffs = [(filtered_dates[i] - filtered_dates[i-1]).days for i in range(1, len(filtered_dates))]
                if (max(filtered_diffs) - min(filtered_diffs)) <= 5:
                    avg = sum(filtered_diffs) / len(filtered_diffs)
                    if 25 <= avg <= 35:
                        return None, 1, filtered_dates
                    else:
                        return round(avg), None, filtered_dates
    
    return None, None, None


def detect_and_project_recurrence(
    events: List[FinancialEvent], 
    start_date: date, 
    days_to_project: int = 90
) -> List[FinancialEvent]:
    """
    Detects recurring events from history and projects them 90 days forward.
    Uses category-level grouping with robust cadence detection.
    """
    valid_events = [e for e in events if e.status in ('settled', 'scheduled')]
    
    # Group by (category, direction, flexibility)
    cat_groups = defaultdict(list)
    for e in valid_events:
        key = (e.category, e.direction)
        dt = e.settlement_date if e.direction == 'credit' and e.settlement_date else e.event_date
        if not dt: dt = e.event_date
        cat_groups[key].append((dt, e))
        
    projected = []
    end_date = start_date + timedelta(days=days_to_project)
    
    for key, items in cat_groups.items():
        items.sort(key=lambda x: x[0])
        if len(items) < 2:
            continue
            
        dates = [x[0] for x in items]
        cadence_days, cadence_months, filtered_dates = _find_cadence(dates)
        
        if cadence_days or cadence_months:
            filtered_dates_set = set(filtered_dates)
            filtered_items = [items[i] for i, d in enumerate(dates) if d in filtered_dates_set]
            latest_event = filtered_items[-1][1]
            
            if latest_event.status == 'scheduled' and latest_event.amount is not None:
                projected_amt = latest_event.amount
            elif latest_event.direction == 'debit':
                projected_amt = max(i[1].amount for i in filtered_items if i[1].amount is not None)
            else:
                if latest_event.category == 'salary':
                    projected_amt = latest_event.amount
                else:
                    projected_amt = min(i[1].amount for i in filtered_items if i[1].amount is not None)
            
            from dateutil.relativedelta import relativedelta
            import dataclasses
            
            last_date = filtered_dates[-1] if filtered_dates else dates[-1]
            if cadence_months:
                next_date = last_date + relativedelta(months=1)
            else:
                next_date = last_date + timedelta(days=cadence_days)
            
            while next_date <= end_date:
                if next_date >= start_date:
                    kwargs = dataclasses.asdict(latest_event)
                    kwargs['event_id'] = f"projected_{latest_event.event_id}_{next_date.strftime('%Y%m%d')}"
                    kwargs['event_date'] = next_date
                    kwargs['settlement_date'] = next_date
                    kwargs['status'] = 'projected'
                    kwargs['amount'] = projected_amt
                    projected.append(FinancialEvent(**kwargs))
                    
                if cadence_months:
                    next_date += relativedelta(months=1)
                else:
                    next_date += timedelta(days=cadence_days)
                    
    return projected

def build_ledger(
    events: List[FinancialEvent], 
    request_date: date, 
    profile: FinancialProfile
) -> List[FinancialEvent]:
    """
    Builds the final forward-looking 90-day ledger for a user.
    """
    # 1. Resolve chains
    resolved = resolve_event_chains(events)
    
    # 2. Filter out cancelled, failed, unrealized
    valid_statuses = ('settled', 'scheduled', 'pending', 'confirmed')
    filtered = [e for e in resolved if e.status in valid_statuses]
    
    # 3. Handle pending: 
    # "Reserve pending debits. Exclude pending credits"
    # So we remove pending credits.
    filtered = [e for e in filtered if not (e.status == 'pending' and e.direction == 'credit')]
    
    # 4. Project recurrence
    projected = detect_and_project_recurrence(filtered, request_date)
    
    # Combine real and projected
    all_events = filtered + projected
    
    future_events = []
    for e in all_events:
        dt = e.settlement_date if e.direction == 'credit' and e.settlement_date else e.event_date
        if not dt: dt = e.event_date
        
        # We only deduct events that happen ON OR AFTER request_date.
        # Past pending events are already held in the available balance.
        if dt >= request_date:
            future_events.append(e)
            
    # Sort chronologically
    def get_sort_date(e):
        dt = e.settlement_date if e.direction == 'credit' and e.settlement_date else e.event_date
        if not dt: return e.event_date
        return dt
        
    future_events.sort(key=get_sort_date)
    return future_events
