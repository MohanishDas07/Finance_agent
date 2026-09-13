import os, sys, csv
code_dir = 'code'
sys.path.insert(0, code_dir)

from ingestion.loaders import CSVLoader
from ingestion.currency import CurrencyNormalizer
from engine.ledger import build_ledger
from engine.simulate import Simulator
from engine.plans import generate_and_rank_plans
from ingestion.evidence import EvidenceExtractor, apply_evidence_to_ledger

dataset_dir = 'dataset'
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

with open(os.path.join(dataset_dir, 'sample_requests.csv'), encoding='utf-8') as f:
    ground_truth = {r['request_id']: r for r in csv.DictReader(f)}

for req in samples:
    gt = ground_truth[req.request_id]
    prof = profiles[req.user_id]
    user_events = [e for e in events if e.user_id == req.user_id]
    norm_events = [normalizer.normalize_event(e, prof.home_currency) for e in user_events]
    ledger = build_ledger(norm_events, req.request_date, prof)
    sim = Simulator(ledger, prof, req)
    amt, status, method, plan, early_date, spending = generate_and_rank_plans(sim, options)
    diff_amt = round(amt - float(gt['amount_safe_to_pay']), 2)
    m_status = status == gt['affordability_status']
    m_method = method == gt['recommended_payment_method']
    m_plan = plan == gt['payment_plan']
    m_early = early_date == gt['earliest_date_for_full_payment']
    m_spending = spending == gt['spending_changes_needed']
    m_amt = abs(diff_amt) <= 0.1
    print(f"{req.request_id} | amt_match={m_amt} (GT={gt['amount_safe_to_pay']}, Ours={amt}, diff={diff_amt}) | status={m_status} | method={m_method} | plan={m_plan} | early={m_early} | spending={m_spending}")
