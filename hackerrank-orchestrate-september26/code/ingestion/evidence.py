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
            # Simple heuristic mock for the sample data
            text = message.message_text
            # Regex for amounts like IDR 42750000 or EUR 1037.52
            amt_match = re.search(r'(?:IDR|ZAR|EUR|USD|INR)\s*([\d\.,]+[\d])', text)
            # Regex for dates like 2025-08-15
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
            
            amt = float(amt_match.group(1).replace(',', '')) if amt_match else None
            dt = date_match.group(0) if date_match else None
            
            if "naik menjadi" in text or "gaji" in text.lower() or "salary" in text.lower():
                # Salary amendment
                facts.append(ExtractedFact(
                    action='amend_amount',
                    event_id=message.related_event_id,
                    new_amount=amt,
                    new_date=dt,
                    description='salary'
                ))
            elif "replaces the payroll date" in text:
                facts.append(ExtractedFact(
                    action='amend_date',
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
    
    # 1. Recover blank amounts from images
    img_by_event = {img.related_event_id: img for img in images if img.related_event_id}
    for e in events:
        if e.amount is None and e.event_id in img_by_event:
            amt = extractor.extract_from_image(img_by_event[e.event_id])
            if amt is not None:
                e.amount = amt
                
    # 2. Apply message amendments
    # We apply them by directly mutating the event, or by adding/canceling
    msg_by_event = {m.related_event_id: m for m in messages if m.related_event_id}
    
    # For messages without related_event_id, they might be global profile updates (like salary)
    global_msgs = [m for m in messages if not m.related_event_id]
    
    for m in global_msgs:
        facts = extractor.extract_from_message(m)
        for f in facts:
            if f.description == 'salary' and f.action == 'amend_amount' and f.new_amount:
                # Add a dummy scheduled event for the new salary
                # We find the last salary event to copy its properties (like description, etc)
                last_salary = None
                for e in events:
                    if e.user_id == m.user_id and e.category == 'salary':
                        if not last_salary or e.event_date > last_salary.event_date:
                            last_salary = e
                            
                if last_salary and f.new_date:
                    from datetime import datetime
                    import dataclasses
                    dt = datetime.strptime(f.new_date, "%Y-%m-%d").date()
                    kwargs = dataclasses.asdict(last_salary)
                    kwargs['event_id'] = f"amended_salary_{m.message_id}"
                    kwargs['event_date'] = dt
                    kwargs['settlement_date'] = dt
                    kwargs['status'] = 'scheduled'
                    kwargs['amount'] = f.new_amount
                    events.append(FinancialEvent(**kwargs))

    for e in events:
        if e.event_id in msg_by_event:
            m = msg_by_event[e.event_id]
            facts = extractor.extract_from_message(m)
            for f in facts:
                if f.action == 'cancel':
                    e.status = 'cancelled'
                elif f.action == 'amend_amount' and f.new_amount:
                    e.amount = f.new_amount
                elif f.action == 'amend_date' and f.new_date:
                    from datetime import datetime
                    dt = datetime.strptime(f.new_date, "%Y-%m-%d").date()
                    e.event_date = dt
                    e.settlement_date = dt
                    
    return events
