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
from ingestion.evidence import apply_evidence_to_ledger
def main():
    dataset_dir = os.path.join(os.path.dirname(code_dir), 'dataset')
    loader = CSVLoader(dataset_dir)
    profiles = loader.load_profiles()
    requests = loader.load_requests()
    events = loader.load_events()
    rates = loader.load_exchange_rates()
    options = loader.load_payment_options()
    messages = loader.load_messages()
    images = loader.load_images()
    normalizer = CurrencyNormalizer(rates)
    output_rows = []
    for req in requests:
        user_id = req.user_id
        profile = profiles[user_id]
        user_events = [e for e in events if e.user_id == user_id]
        norm_events = []
        for e in user_events:
            if e.currency != profile.home_currency and e.amount is not None:
                try: norm_events.append(normalizer.normalize_event(e, profile.home_currency))
                except: norm_events.append(e)
            else: norm_events.append(e)
        from ingestion.evidence import EvidenceExtractor
        extractor = EvidenceExtractor(use_mock=True)
        amended_events = apply_evidence_to_ledger(norm_events, messages, images, extractor)
        ledger = build_ledger(amended_events, req.request_date, profile)
        simulator = Simulator(ledger, profile, req)
        amt, status, method, plan, early_date, spending = generate_and_rank_plans(simulator, options)
        explanation = f'Based on 90-day simulation starting {req.request_date}, min balance reaches limit. {status}.'
        early_date_str = early_date if early_date else ''
        output_rows.append({
            'request_id': req.request_id,
            'amount_safe_to_pay': str(round(amt, 2)),
            'affordability_status': status,
            'recommended_payment_method': method,
            'payment_plan': plan,
            'earliest_date_for_full_payment': early_date_str,
            'spending_changes_needed': spending,
            'decision_explanation': explanation
        })
    out_path = os.path.join(dataset_dir, 'output.csv')
    fieldnames = ['request_id', 'amount_safe_to_pay', 'affordability_status', 'recommended_payment_method', 'payment_plan', 'earliest_date_for_full_payment', 'spending_changes_needed', 'decision_explanation']
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f'Successfully wrote {len(output_rows)} predictions to {out_path}.')
if __name__ == '__main__':
    main()
