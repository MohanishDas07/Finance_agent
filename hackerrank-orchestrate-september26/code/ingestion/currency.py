from datetime import date
from typing import Dict, List, Optional
from ingestion.models import FinancialEvent, ExchangeRate

class CurrencyNormalizer:
    def __init__(self, exchange_rates: List[ExchangeRate]):
        # index by (date, from_currency, to_currency)
        self.rates: Dict[tuple[date, str, str], float] = {}
        for r in exchange_rates:
            self.rates[(r.rate_date, r.from_currency, r.to_currency)] = r.rate

    def get_rate(self, dt: date, from_curr: str, to_curr: str) -> float:
        if from_curr == to_curr:
            return 1.0
        # If we can't find exact date, fallback to nearest earlier date (for robustness, though task says fixed dated conversion rates are provided)
        # Assuming the dataset always provides the exact rate needed for the settlement date.
        rate = self.rates.get((dt, from_curr, to_curr))
        if rate is not None:
            return rate
            
        raise ValueError(f"Exchange rate not found for {from_curr}->{to_curr} on {dt}")

    def normalize_event(self, event: FinancialEvent, target_currency: str) -> FinancialEvent:
        """ Returns a new FinancialEvent with amount normalized to target_currency """
        if event.currency == target_currency or event.amount is None:
            return event
            
        rate = self.get_rate(event.settlement_date, event.currency, target_currency)
        normalized_amount = round(event.amount * rate, 4)
        
        normalized_min = None
        if event.minimum_allowed_amount is not None:
            normalized_min = round(event.minimum_allowed_amount * rate, 4)
            
        # Return a copy with updated currency and amounts
        # Using a simple dict unpack for dataclass
        import dataclasses
        kwargs = dataclasses.asdict(event)
        kwargs['amount'] = normalized_amount
        kwargs['currency'] = target_currency
        kwargs['minimum_allowed_amount'] = normalized_min
        
        return FinancialEvent(**kwargs)
