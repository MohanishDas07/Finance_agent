import csv
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

# load data
def load_data():
    with open('dataset/financial_profiles.csv', encoding='utf-8') as f:
        profiles = list(csv.DictReader(f))
    with open('dataset/financial_events.csv', encoding='utf-8') as f:
        events = list(csv.DictReader(f))
    return profiles, events

profiles, events = load_data()
user_01_profile = next(p for p in profiles if p['user_id'] == 'user_01')
user_01_events = [e for e in events if e['user_id'] == 'user_01']
start_date = datetime.strptime('2024-03-03', '%Y-%m-%d').date()

print(f"Current balance: {user_01_profile['current_available_balance']}")
print(f"Min balance: {user_01_profile['minimum_balance_to_keep']}")

# Let's project recurring events for user_01
# group past debits by description
debits = [e for e in user_01_events if e['direction'] == 'debit' and e['status'] == 'settled']
groups = defaultdict(list)
for e in debits:
    groups[e['description']].append((datetime.strptime(e['event_date'], '%Y-%m-%d').date(), float(e['amount'])))

projected_events = []
for desc, items in groups.items():
    items.sort(key=lambda x: x[0])
    if len(items) >= 2:
        dates = [x[0] for x in items]
        amounts = [x[1] for x in items]
        diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
        avg_diff = sum(diffs) / len(diffs)
        
        # if avg_diff is around 30, it's monthly
        # max amount for conservative
        max_amt = max(amounts)
        
        if 25 <= avg_diff <= 35:
            # project monthly
            next_date = dates[-1] + timedelta(days=round(avg_diff))
            while next_date <= start_date + timedelta(days=90):
                if next_date >= start_date:
                    projected_events.append((next_date, desc, -max_amt))
                next_date += timedelta(days=round(avg_diff))

# also add scheduled events
scheduled = [e for e in user_01_events if e['status'] == 'scheduled']
for e in scheduled:
    dt = datetime.strptime(e['settlement_date'], '%Y-%m-%d').date()
    amt = float(e['amount']) if e['amount'] else 0
    if e['direction'] == 'debit':
        projected_events.append((dt, e['description'], -amt))
    else:
        projected_events.append((dt, e['description'], amt))
        
projected_events.sort(key=lambda x: x[0])

balance = float(user_01_profile['current_available_balance']) - 25256 # apply request
min_balance_seen = balance
projected_events.append((datetime.strptime('2024-04-15', '%Y-%m-%d').date(), 'Projected salary', 23320.0))
projected_events.append((datetime.strptime('2024-05-15', '%Y-%m-%d').date(), 'Projected salary', 23320.0))
projected_events.sort(key=lambda x: x[0])


for dt, desc, amt in projected_events:
    balance += amt
    print(f"{dt}: {desc} ({amt}) -> Balance: {balance}")
    if balance < min_balance_seen:
        min_balance_seen = balance
projected_events.append((datetime.strptime('2024-04-15', '%Y-%m-%d').date(), 'Projected salary', 23320.0))
projected_events.append((datetime.strptime('2024-05-15', '%Y-%m-%d').date(), 'Projected salary', 23320.0))
projected_events.sort(key=lambda x: x[0])

        
print(f"Min balance seen: {min_balance_seen}")
