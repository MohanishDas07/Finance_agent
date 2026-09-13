import os
import sys
import csv
from datetime import datetime

code_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, code_dir)

from ingestion.loaders import CSVLoader
from ingestion.currency import CurrencyNormalizer
from engine.ledger import build_ledger
from engine.simulate import Simulator
from engine.plans import generate_and_rank_plans
from ingestion.evidence import EvidenceExtractor, apply_evidence_to_ledger
from engine.decision import generate_decision_explanation

def format_amt_safe(val: float) -> str:
    val_round = round(val, 2)
    if val_round.is_integer():
        return str(int(val_round))
    else:
        return str(val_round)

def main():
    repo_root = os.path.dirname(code_dir)
    dataset_dir = os.path.join(repo_root, 'dataset')
    
    loader = CSVLoader(dataset_dir)
    profiles = loader.load_profiles()
    requests = loader.load_requests()
    events = loader.load_events()
    rates = loader.load_exchange_rates()
    options = loader.load_payment_options()
    messages = loader.load_messages()
    images = loader.load_images()
    
    events_dict = {e.event_id: e for e in events}
    extractor = EvidenceExtractor(use_mock=True)
    normalizer = CurrencyNormalizer(rates)
    
    output_rows = []
    
    for req in requests:
        user_id = req.user_id
        profile = profiles[user_id]
        
        user_events = [e for e in events if e.user_id == user_id]
        norm_events = []
        for e in user_events:
            if e.currency != profile.home_currency and e.amount is not None:
                try:
                    norm_events.append(normalizer.normalize_event(e, profile.home_currency))
                except Exception:
                    norm_events.append(e)
            else:
                norm_events.append(e)
                
        amended_events = apply_evidence_to_ledger(norm_events, messages, images, extractor)
        ledger = build_ledger(amended_events, req.request_date, profile)
        simulator = Simulator(ledger, profile, req)
        
        amt, status, method, plan, early_date, spending = generate_and_rank_plans(simulator, options)
        
        # Ensure 0 <= amount_safe_to_pay <= requested_amount
        amt_safe = min(req.requested_amount, max(0.0, amt))
        amt_str = format_amt_safe(amt_safe)
        early_date_str = early_date if early_date else ''
        
        explanation = generate_decision_explanation(
            profile=profile,
            request=req,
            status=status,
            method=method,
            plan=plan,
            earliest_date=early_date_str,
            spending=spending,
            amount_safe=amt_safe,
            events_dict=events_dict
        )
        
        output_rows.append({
            'request_id': req.request_id,
            'amount_safe_to_pay': amt_str,
            'affordability_status': status,
            'recommended_payment_method': method,
            'payment_plan': plan,
            'earliest_date_for_full_payment': early_date_str,
            'spending_changes_needed': spending,
            'decision_explanation': explanation
        })
        
    fieldnames = [
        'request_id', 
        'amount_safe_to_pay', 
        'affordability_status', 
        'recommended_payment_method', 
        'payment_plan', 
        'earliest_date_for_full_payment', 
        'spending_changes_needed', 
        'decision_explanation'
    ]
    
    # Write to root output.csv as required by hackathon submission spec
    root_out_path = os.path.join(repo_root, 'output.csv')
    with open(root_out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
        
    # Also write to dataset/output.csv for local convenience
    dataset_out_path = os.path.join(dataset_dir, 'output.csv')
    with open(dataset_out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
        
    print(f"Successfully generated predictions for {len(output_rows)} requests.")
    print(f"  Root submission file: {root_out_path}")
    print(f"  Dataset copy:         {dataset_out_path}")

if __name__ == '__main__':
    main()
