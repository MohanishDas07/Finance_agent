import os
import sys

code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, code_dir)

from ingestion.loaders import CSVLoader
from ingestion.currency import CurrencyNormalizer
from engine.ledger import build_ledger
from engine.simulate import Simulator
from engine.plans import generate_and_rank_plans
from ingestion.evidence import EvidenceExtractor, apply_evidence_to_ledger

def evaluate_samples():
    dataset_dir = os.path.join(code_dir, "..", "dataset")
    loader = CSVLoader(dataset_dir)
    
    profiles = loader.load_profiles()
    events = loader.load_events()
    rates = loader.load_exchange_rates()
    options = loader.load_payment_options()
    messages = loader.load_messages()
    images = loader.load_images()
    
    extractor = EvidenceExtractor(use_mock=True)
    events = apply_evidence_to_ledger(events, messages, images, extractor)
    
    normalizer = CurrencyNormalizer(rates)
    samples = loader.load_sample_requests()
    
    import csv
    with open(os.path.join(dataset_dir, 'sample_requests.csv'), encoding='utf-8') as f:
        ground_truth = {r['request_id']: r for r in csv.DictReader(f)}
        
    correct = 0
    total = len(samples)
    
    for req in samples:
        gt = ground_truth[req.request_id]
        
        prof = profiles[req.user_id]
        user_events = [e for e in events if e.user_id == req.user_id]
        norm_events = [normalizer.normalize_event(e, prof.home_currency) for e in user_events]
        
        ledger = build_ledger(norm_events, req.request_date, prof)
        sim = Simulator(ledger, prof, req)
        
        amt, status, method, plan, early_date, spending = generate_and_rank_plans(sim, options)
        
        gt_amt = float(gt['amount_safe_to_pay'])
        gt_status = gt['affordability_status']
        gt_method = gt['recommended_payment_method']
        gt_plan = gt['payment_plan']
        gt_early = gt['earliest_date_for_full_payment']
        gt_spending = gt['spending_changes_needed']
        
        match = True
        # amount matching (allow small float differences)
        if abs(amt - gt_amt) > 0.1: match = False
        if status != gt_status: match = False
        if method != gt_method: match = False
        # plan matching
        if plan != gt_plan: match = False
        if early_date != gt_early: match = False
        if spending != gt_spending: match = False
        
        if match:
            correct += 1
            print(f"[PASS] {req.request_id}")
        else:
            print(f"[FAIL] {req.request_id}")
            print(f"  Expected: {gt_amt}, {gt_status}, {gt_method}, {gt_plan}, {gt_early}, {gt_spending}")
            print(f"  Got:      {amt}, {status}, {method}, {plan}, {early_date}, {spending}")
            
    print(f"\nScore: {correct}/{total} ({(correct/total)*100:.1f}%)")
    
if __name__ == '__main__':
    evaluate_samples()
