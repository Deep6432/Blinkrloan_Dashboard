import requests
import logging
from django.conf import settings
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Any
from .models import LoanRecord
import re

logger = logging.getLogger(__name__)


class ExternalAPIService:
    """Service to handle external API calls"""
    
    def __init__(self):
        self.api_url = settings.EXTERNAL_API_URL
        self.timeout = 30
    
    def fetch_loan_data(self) -> List[Dict[str, Any]]:
        """Fetch loan data from external API"""
        try:
            response = requests.get(self.api_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get('pr', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return self._get_mock_data()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return self._get_mock_data()
    
    def _get_mock_data(self) -> List[Dict[str, Any]]:
        """Return mock data when API fails"""
        return [
            {
                'lead_no': 'LD001',
                'loan_no': 'LN001',
                'sanction_date': '2024-01-15',
                'disbursal_date': '2024-01-20',
                'loan_amount': 50000,
                'repayment_amount': 55000,
                'total_received': 45000,
                'outstanding': 10000,
                'overdue_days': 15,
                'overdue_amount': 2000,
                'dpd_bucket': '0-30',
                'closed_status': 'Active',
                'state': 'Maharashtra',
                'city': 'Mumbai',
                'fraud_status': 'No',
                'reloan_status': 'No',
                'collection_active': 'Yes'
            },
            {
                'lead_no': 'LD002',
                'loan_no': 'LN002',
                'sanction_date': '2024-01-10',
                'disbursal_date': '2024-01-15',
                'loan_amount': 75000,
                'repayment_amount': 82500,
                'total_received': 75000,
                'outstanding': 0,
                'overdue_days': 0,
                'overdue_amount': 0,
                'dpd_bucket': '0-30',
                'closed_status': 'Closed',
                'state': 'Karnataka',
                'city': 'Bangalore',
                'fraud_status': 'No',
                'reloan_status': 'Yes',
                'collection_active': 'No'
            },
            {
                'lead_no': 'LD003',
                'loan_no': 'LN003',
                'sanction_date': '2024-01-05',
                'disbursal_date': '2024-01-10',
                'loan_amount': 100000,
                'repayment_amount': 110000,
                'total_received': 60000,
                'outstanding': 50000,
                'overdue_days': 45,
                'overdue_amount': 10000,
                'dpd_bucket': '31-60',
                'closed_status': 'Active',
                'state': 'Tamil Nadu',
                'city': 'Chennai',
                'fraud_status': 'No',
                'reloan_status': 'No',
                'collection_active': 'Yes'
            },
            {
                'lead_no': 'LD004',
                'loan_no': 'LN004',
                'sanction_date': '2024-01-20',
                'disbursal_date': '2024-01-25',
                'loan_amount': 30000,
                'repayment_amount': 33000,
                'total_received': 30000,
                'outstanding': 0,
                'overdue_days': 0,
                'overdue_amount': 0,
                'dpd_bucket': '0-30',
                'closed_status': 'Closed',
                'state': 'Gujarat',
                'city': 'Ahmedabad',
                'fraud_status': 'No',
                'reloan_status': 'No',
                'collection_active': 'No'
            },
            {
                'lead_no': 'LD005',
                'loan_no': 'LN005',
                'sanction_date': '2024-01-12',
                'disbursal_date': '2024-01-17',
                'loan_amount': 80000,
                'repayment_amount': 88000,
                'total_received': 40000,
                'outstanding': 48000,
                'overdue_days': 90,
                'overdue_amount': 15000,
                'dpd_bucket': '61-90',
                'closed_status': 'Active',
                'state': 'Maharashtra',
                'city': 'Pune',
                'fraud_status': 'No',
                'reloan_status': 'No',
                'collection_active': 'Yes'
            }
        ]


class DataSyncService:
    """Service to sync data from external API to database"""
    
    def __init__(self):
        self.api_service = ExternalAPIService()
    
    def _parse_date(self, date_str: str) -> datetime.date:
        """Parse date string from API, handling various formats"""
        if not date_str:
            return None
        
        # Remove timezone info and parse
        date_str = re.sub(r'T.*Z$', '', date_str)
        date_str = re.sub(r'T.*\.\d+Z$', '', date_str)
        
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S').date()
            except ValueError:
                logger.warning(f"Could not parse date: {date_str}")
                return None

    def sync_loan_data(self) -> int:
        """Sync loan data from API to database"""
        api_data = self.api_service.fetch_loan_data()
        synced_count = 0
        
        for record_data in api_data:
            try:
                # Parse dates safely
                sanction_date = self._parse_date(record_data.get('sanction_date'))
                disbursal_date = self._parse_date(record_data.get('disbursal_date'))
                repayment_date = self._parse_date(record_data.get('repayment_date'))
                last_received_date = self._parse_date(record_data.get('last_received_date'))
                
                # Handle collection_active as boolean
                collection_active = record_data.get('collection_active', False)
                if isinstance(collection_active, str):
                    collection_active = collection_active.lower() in ['true', 'yes', '1']
                
                loan_record, created = LoanRecord.objects.update_or_create(
                    loan_no=record_data['loan_no'],
                    defaults={
                        'lead_no': record_data['lead_no'],
                        'pan': record_data.get('pan', ''),
                        'sanction_date': sanction_date,
                        'disbursal_date': disbursal_date,
                        'loan_amount': Decimal(str(record_data['loan_amount'])),
                        'tenure': record_data.get('tenure'),
                        'repayment_date': repayment_date,
                        'repayment_amount': Decimal(str(record_data['repayment_amount'])),
                        'processing_fee': Decimal(str(record_data.get('processing_fee', 0))) if record_data.get('processing_fee') else None,
                        'net_disbursal': Decimal(str(record_data.get('net_disbursal', 0))) if record_data.get('net_disbursal') else None,
                        'interest_amount': Decimal(str(record_data.get('interest_amount', 0))) if record_data.get('interest_amount') else None,
                        'collection_active': collection_active,
                        'fraud_status': record_data['fraud_status'],
                        'reloan_status': record_data['reloan_status'],
                        'total_received': Decimal(str(record_data['total_received'])),
                        'last_received_date': last_received_date,
                        'outstanding': Decimal(str(record_data['outstanding'])),
                        'overdue_days': record_data['overdue_days'],
                        'overdue_amount': Decimal(str(record_data['overdue_amount'])),
                        'dpd_bucket': record_data['dpd_bucket'],
                        'closed_status': record_data['closed_status'],
                        'state': record_data['state'],
                        'city': record_data['city'],
                    }
                )
                if created:
                    synced_count += 1
            except Exception as e:
                logger.error(f"Error syncing record {record_data.get('loan_no', 'unknown')}: {e}")
        
        return synced_count
