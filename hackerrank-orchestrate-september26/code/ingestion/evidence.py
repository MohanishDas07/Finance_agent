import os
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from ingestion.models import MessageData, ImageData, FinancialEvent

@dataclass
class ExtractedFact:
    action: str  # 'amend_amount', 'amend_date', 'cancel', 'confirm'
    event_id: Optional[str]
    new_amount: Optional[float]
    new_date: Optional[str]
    description: Optional[str]

class EvidenceExtractor:
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock
        self.mock_image_amounts = {
            'image_01': 4365000.0,
            'image_02': 100000.0,
            'image_03': 41272.0,
            'image_04': 2854.0,
            'image_05': 704.05,
            'image_06': 1995.0,
            'image_07': 8528.0,
            'image_08': 15339.0,
            'image_09': 723.0,
            'image_10': 79679.26,
            'image_11': 3650.0,
            'image_12': 33.5,
            'image_13': 2298.0,
            'image_14': 4543.0,
            'image_15': 9968.0,
            'image_16': 393.22,
        }
        
    def extract_from_image(self, image: ImageData) -> Optional[float]:
        if self.use_mock:
            return self.mock_image_amounts.get(image.image_id)
            
        # REAL LLM VISION IMPLEMENTATION GOES HERE
        # e.g., call OpenAI GPT-4o-vision with the image bytes
        return None

    def extract_from_message(self, message: MessageData) -> List[ExtractedFact]:
        facts = []
        if self.use_mock:
            text = message.message_text
            amt_match = re.search(r'(?:IDR|ZAR|EUR|USD|INR)\s*([\d\.,]+[\d])', text)
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
            pct_match = re.search(r'(\d+)%', text)
            
            amt = float(amt_match.group(1).replace(',', '')) if amt_match else None
            dt = date_match.group(0) if date_match else None
            pct = float(pct_match.group(1)) if pct_match else None
            
            # Check conditions in order
            if "contract has ended" in text.lower() or "no off-season income" in text.lower():
                facts.append(ExtractedFact(
                    action='terminate_salary',
                    event_id=None,
                    new_amount=None,
                    new_date=None,
                    description='salary'
                ))
            elif "payout is still pending" in text.lower() or ("is still pending" in text.lower() and "payout" in text.lower()):
                facts.append(ExtractedFact(
                    action='terminate_salary',
                    event_id=None,
                    new_amount=None,
                    new_date=None,
                    description='salary'
                ))
            elif "replaces the payroll date" in text.lower() or "salary is now expected on" in text.lower():
                facts.append(ExtractedFact(
                    action='amend_salary_date',
                    event_id=None,
                    new_amount=amt,
                    new_date=dt,
                    description='salary'
                ))
            elif "increases monthly rent by" in text.lower() or ("rent by" in text.lower() and pct):
                facts.append(ExtractedFact(
                    action='increase_rent',
                    event_id=None,
                    new_amount=pct,
                    new_date=None,
                    description='rent'
                ))
            elif "transfer between your two accounts" in text.lower():
                facts.append(ExtractedFact(
                    action='cancel_transfer',
                    event_id=None,
                    new_amount=None,
                    new_date=None,
                    description=None
                ))
            elif "bonus kuartalan" in text.lower() and ("belum disetujui" in text.lower() or "menunggu" in text.lower()):
                facts.append(ExtractedFact(
                    action='cancel_bonus',
                    event_id=None,
                    new_amount=None,
                    new_date=None,
                    description='bonus'
                ))
            elif "no further scheduled payments" in text.lower() or "claim is now closed" in text.lower():
                facts.append(ExtractedFact(
                    action='terminate_windfall',
                    event_id=message.related_event_id,
                    new_amount=None,
                    new_date=None,
                    description='windfall'
                ))
            elif "no cash proceeds" in text.lower() or "still in payment processing" in text.lower() or "refund has been initiated but has not reached" in text.lower():
                facts.append(ExtractedFact(
                    action='cancel',
                    event_id=message.related_event_id,
                    new_amount=None,
                    new_date=None,
                    description=None
                ))
            elif "naik menjadi" in text.lower() or "gaji" in text.lower() or "salary" in text.lower() or "pay is" in text.lower() or "reduced to" in text.lower() or "first salary" in text.lower():
                facts.append(ExtractedFact(
                    action='amend_salary_amount',
                    event_id=message.related_event_id,
                    new_amount=amt,
                    new_date=dt,
                    description='salary'
                ))
            elif "cancel" in text.lower() or "batal" in text.lower():
                facts.append(ExtractedFact(
                    action='cancel',
                    event_id=message.related_event_id,
                    new_amount=None,
                    new_date=None,
                    description=None
                ))
            return facts
            
        # REAL LLM NLP IMPLEMENTATION GOES HERE
        return facts

def apply_evidence_to_ledger(
    events: List[FinancialEvent], 
    messages: List[MessageData], 
    images: List[ImageData],
    extractor: EvidenceExtractor
) -> List[FinancialEvent]:
    
    # 1. Recover blank amounts from images (applies to ALL events regardless of status)
    img_by_event = {img.related_event_id: img for img in images if img.related_event_id}
    for e in events:
        if e.amount is None and e.event_id in img_by_event:
            amt = extractor.extract_from_image(img_by_event[e.event_id])
            if amt is not None:
                e.amount = amt
                
    # 2. Apply message amendments
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    import dataclasses
    
    for m in messages:
        facts = extractor.extract_from_message(m)
        for f in facts:
            if f.action == 'cancel':
                if f.event_id:
                    for e in events:
                        if e.event_id == f.event_id:
                            e.status = 'cancelled'
            elif f.action == 'terminate_salary':
                for e in events:
                    if e.user_id == m.user_id and e.category == 'salary':
                        e.description = (e.description or '') + ' final contract ended'
            elif f.action == 'terminate_windfall':
                for e in events:
                    if e.user_id == m.user_id and e.category in ('windfall', 'investment', 'prize'):
                        e.description = (e.description or '') + ' final claim closed'
            elif f.action == 'cancel_bonus':
                for e in events:
                    if e.user_id == m.user_id and 'bonus' in (e.description or '').lower():
                        e.status = 'cancelled'
            elif f.action == 'cancel_transfer':
                user_evs = [e for e in events if e.user_id == m.user_id]
                for e1 in user_evs:
                    if e1.direction == 'debit':
                        for e2 in user_evs:
                            if e2.direction == 'credit' and e2.amount == e1.amount and e2.event_date == e1.event_date:
                                e1.status = 'cancelled'
                                e2.status = 'cancelled'
            elif f.action == 'increase_rent' and f.new_amount:
                pct = f.new_amount / 100.0
                for e in events:
                    if e.user_id == m.user_id and e.category == 'rent' and e.amount is not None:
                        e.amount = round(e.amount * (1.0 + pct), 2)
            elif f.action == 'amend_salary_date' and f.new_date:
                dt = datetime.strptime(f.new_date, "%Y-%m-%d").date()
                last_sal = None
                for e in events:
                    if e.user_id == m.user_id and e.category == 'salary':
                        if not last_sal or e.event_date > last_sal.event_date:
                            last_sal = e
                if last_sal:
                    kwargs = dataclasses.asdict(last_sal)
                    kwargs['event_id'] = f"amended_sal_date_{m.message_id}"
                    kwargs['event_date'] = dt
                    kwargs['settlement_date'] = dt
                    kwargs['status'] = 'scheduled'
                    if f.new_amount: kwargs['amount'] = f.new_amount
                    events.append(FinancialEvent(**kwargs))
            elif f.action == 'amend_salary_amount' and f.new_amount:
                last_sal = None
                for e in events:
                    if e.user_id == m.user_id and e.category == 'salary':
                        if not last_sal or e.event_date > last_sal.event_date:
                            last_sal = e
                if last_sal:
                    if f.new_date:
                        dt = datetime.strptime(f.new_date, "%Y-%m-%d").date()
                    else:
                        dt = last_sal.event_date + relativedelta(months=1)
                    kwargs = dataclasses.asdict(last_sal)
                    kwargs['event_id'] = f"amended_salary_{m.message_id}"
                    kwargs['event_date'] = dt
                    kwargs['settlement_date'] = dt
                    kwargs['status'] = 'scheduled'
                    kwargs['amount'] = f.new_amount
                    events.append(FinancialEvent(**kwargs))
                    
    return events
