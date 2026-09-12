import csv
from datetime import datetime
from typing import Dict, List, Optional
from ingestion.models import (
    FinancialProfile, RequestData, FinancialEvent, ExchangeRate, 
    PaymentOption, MessageData, ImageData
)

def _parse_date(d: str):
    if not d: return None
    if " " in d:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    return datetime.strptime(d, "%Y-%m-%d").date()

def _parse_float(f: str) -> Optional[float]:
    return float(f) if f else None

def _parse_int(i: str) -> Optional[int]:
    return int(i) if i else None

def _parse_bool(b: str) -> bool:
    return b.lower() == 'true'

def _parse_list(l: str) -> List[str]:
    return l.split('|') if l else []

class CSVLoader:
    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir

    def load_profiles(self) -> Dict[str, FinancialProfile]:
        profiles = {}
        with open(f"{self.dataset_dir}/financial_profiles.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                profiles[row['user_id']] = FinancialProfile(
                    user_id=row['user_id'],
                    home_currency=row['home_currency'],
                    current_available_balance=_parse_float(row['current_available_balance']) or 0.0,
                    minimum_balance_to_keep=_parse_float(row['minimum_balance_to_keep']) or 0.0,
                    financial_priorities=_parse_list(row['financial_priorities']),
                    expense_categories_to_protect=_parse_list(row['expense_categories_to_protect']),
                    expense_categories_user_is_willing_to_reduce=_parse_list(row['expense_categories_user_is_willing_to_reduce']),
                    expense_categories_user_is_willing_to_stop=_parse_list(row['expense_categories_user_is_willing_to_stop']),
                    payment_methods_user_will_consider=_parse_list(row['payment_methods_user_will_consider']),
                    max_installment_months=_parse_int(row['max_installment_months'])
                )
        return profiles

    def load_requests(self) -> List[RequestData]:
        requests = []
        with open(f"{self.dataset_dir}/requests.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                requests.append(RequestData(
                    request_id=row['request_id'],
                    user_id=row['user_id'],
                    request_date=datetime.strptime(row['request_date'], "%Y-%m-%d").date(),
                    request_type=row['request_type'],
                    requested_amount=_parse_float(row['requested_amount']) or 0.0,
                    desired_completion_date=datetime.strptime(row['desired_completion_date'], "%Y-%m-%d").date(),
                    allows_partial_payment=_parse_bool(row['allows_partial_payment']),
                    request_text=row['request_text']
                ))
        return requests

    def load_messages(self) -> List[MessageData]:
        messages = []
        with open(f"{self.dataset_dir}/messages.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                messages.append(MessageData(
                    message_id=row['message_id'],
                    user_id=row['user_id'],
                    request_id=row['request_id'],
                    related_event_id=row['related_event_id'],
                    sent_at=row['sent_at'],
                    source_type=row['source_type'],
                    message_text=row['message_text']
                ))
        return messages

    def load_images(self) -> List[ImageData]:
        images = []
        with open(f"{self.dataset_dir}/images.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                images.append(ImageData(
                    image_id=row['image_id'],
                    user_id=row['user_id'],
                    request_id=row['request_id'],
                    related_event_id=row['related_event_id']
                ))
        return images

    def load_sample_requests(self) -> List[RequestData]:
        requests = []
        with open(f"{self.dataset_dir}/sample_requests.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                requests.append(RequestData(
                    request_id=row['request_id'],
                    user_id=row['user_id'],
                    request_date=datetime.strptime(row['request_date'], "%Y-%m-%d").date(),
                    request_type=row['request_type'],
                    requested_amount=_parse_float(row['requested_amount']) or 0.0,
                    desired_completion_date=datetime.strptime(row['desired_completion_date'], "%Y-%m-%d").date(),
                    allows_partial_payment=_parse_bool(row['allows_partial_payment']),
                    request_text=row['request_text']
                ))
        return requests

    def load_events(self) -> List[FinancialEvent]:
        events = []
        with open(f"{self.dataset_dir}/financial_events.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                events.append(FinancialEvent(
                    event_id=row['event_id'],
                    user_id=row['user_id'],
                    event_type=row['event_type'],
                    description=row['description'],
                    category=row['category'],
                    direction=row['direction'],
                    amount=_parse_float(row['amount']),
                    currency=row['currency'],
                    event_date=_parse_date(row['event_date']),
                    settlement_date=_parse_date(row['settlement_date']),
                    status=row['status'],
                    linked_event_id=row['linked_event_id'] if row['linked_event_id'] else None,
                    flexibility=row['flexibility'],
                    minimum_allowed_amount=_parse_float(row['minimum_allowed_amount'])
                ))
        return events

    def load_exchange_rates(self) -> List[ExchangeRate]:
        rates = []
        with open(f"{self.dataset_dir}/exchange_rates.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rates.append(ExchangeRate(
                    rate_date=datetime.strptime(row['rate_date'], "%Y-%m-%d").date(),
                    from_currency=row['from_currency'],
                    to_currency=row['to_currency'],
                    rate=_parse_float(row['rate']) or 1.0
                ))
        return rates

    def load_payment_options(self) -> List[PaymentOption]:
        options = []
        with open(f"{self.dataset_dir}/request_payment_options.csv", newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                options.append(PaymentOption(
                    payment_option_id=row['payment_option_id'],
                    request_id=row['request_id'],
                    payment_method=row['payment_method'],
                    payment_amount=_parse_float(row['payment_amount']) or 0.0,
                    number_of_payments=_parse_int(row['number_of_payments']) or 1,
                    first_payment_date=datetime.strptime(row['first_payment_date'], "%Y-%m-%d").date(),
                    payment_frequency_days=_parse_int(row['payment_frequency_days']),
                    financing_fee=_parse_float(row['financing_fee']) or 0.0,
                    total_payable_amount=_parse_float(row['total_payable_amount']) or 0.0
                ))
        return options
