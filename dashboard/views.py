from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator
from django.core.cache import cache
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
import logging
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)
import json
import requests

from .models import LoanRecord, MonthlyTarget
from .services import DataSyncService

CREDIT_PERSON_API_URL = getattr(
    settings,
    'CREDIT_PERSON_API_URL',
    'https://backend.blinkrloan.com/insights/v1/assigne-lead-wise-data'
)

NOT_CLOSED_PERCENT_API_URL = getattr(
    settings,
    'NOT_CLOSED_PERCENT_API_URL',
    'https://backend.blinkrloan.com/insights/v1/not-closed-percent-against-total'
)


# Decorator to add no-cache headers to API responses
def no_cache_api(view_func):
    """Decorator to prevent caching of API responses"""
    def wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    return wrapped_view


def parse_datetime_safely(datetime_str):
    """Safely parse datetime string and return date object with timezone conversion from UTC to IST"""
    if not datetime_str:
        return None
    
    try:
        # Handle different datetime formats
        if isinstance(datetime_str, str):
            # Handle timezone-aware datetime strings
            if 'T' in datetime_str:
                # Parse as datetime with timezone info
                if datetime_str.endswith('Z'):
                    # UTC timezone
                    dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                elif '+' in datetime_str or datetime_str.count('-') > 2:
                    # Has timezone info
                    dt = datetime.fromisoformat(datetime_str)
                else:
                    # No timezone info, assume UTC
                    dt = datetime.fromisoformat(datetime_str + '+00:00')
                
                # Convert UTC to IST (UTC+5:30)
                ist_offset = timedelta(hours=5, minutes=30)
                ist_dt = dt + ist_offset
                return ist_dt.date()
            else:
                # Simple date string, parse as is
                return datetime.strptime(datetime_str.split(' ')[0], '%Y-%m-%d').date()
        elif hasattr(datetime_str, 'date'):
            return datetime_str.date()
        else:
            return None
    except (ValueError, AttributeError):
        return None


def safe_decimal_conversion(value):
    """Safely convert a value to Decimal, handling None, NaN, and invalid values"""
    if value is None or value == '' or str(value).lower() in ['nan', 'null', 'none']:
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal('0')

def calculate_kpi_from_records(records):
    """Calculate KPI data from a list of records"""
    total_applications = len(records)
    
    if total_applications == 0:
        return {
            'total_applications': 0,
            'sanction_amount': 0,
            'net_disbursal': 0,
            'repayment_amount': 0,
            'collected_amount': 0,
            'pending_collection': 0,
            'principal_outstanding': 0,
            'collection_rate': 0,
            'collected_percentage': 0,
            'pending_percentage': 0,
            'fresh_cases': 0,
            'reloan_cases': 0,
            'fresh_percentage': 0,
            'reloan_percentage': 0,
            'fresh_sanction_amount': 0,
            'reloan_sanction_amount': 0,
            'fresh_disbursed_amount': 0,
            'reloan_disbursed_amount': 0,
            'fresh_repayment_amount': 0,
            'reloan_repayment_amount': 0,
            'fresh_collected_amount': 0,
            'reloan_collected_amount': 0,
            'fresh_pending_amount': 0,
            'reloan_pending_amount': 0,
            'fresh_principal_outstanding': 0,
            'reloan_principal_outstanding': 0,
            # Add recovery calculation fields
            'recoverable_amount_excl_90': 0,
            'recovery_percentage_excl_90': 0,
            'fresh_recoverable_excl_90': 0,
            'fresh_recovery_percentage_excl_90': 0,
            'reloan_recoverable_excl_90': 0,
            'reloan_recovery_percentage_excl_90': 0
        }
    
    # Calculate totals with safe conversion
    sanction_amount = sum(safe_decimal_conversion(record.get('loan_amount')) for record in records)
    net_disbursal = sum(safe_decimal_conversion(record.get('net_disbursal')) for record in records)
    repayment_amount = sum(safe_decimal_conversion(record.get('repayment_amount')) for record in records)
    collected_amount = sum(safe_decimal_conversion(record.get('total_received')) for record in records)
    
    # Calculate fresh vs reloan
    fresh_cases = len([r for r in records if r.get('reloan_status') != 'Reloan'])
    reloan_cases = len([r for r in records if r.get('reloan_status') == 'Reloan'])
    
    fresh_records = [r for r in records if r.get('reloan_status') != 'Reloan']
    reloan_records = [r for r in records if r.get('reloan_status') == 'Reloan']
    
    fresh_sanction_amount = sum(safe_decimal_conversion(record.get('loan_amount')) for record in fresh_records)
    reloan_sanction_amount = sum(safe_decimal_conversion(record.get('loan_amount')) for record in reloan_records)
    
    fresh_disbursed_amount = sum(safe_decimal_conversion(record.get('net_disbursal')) for record in fresh_records)
    reloan_disbursed_amount = sum(safe_decimal_conversion(record.get('net_disbursal')) for record in reloan_records)
    
    fresh_repayment_amount = sum(safe_decimal_conversion(record.get('repayment_amount')) for record in fresh_records)
    reloan_repayment_amount = sum(safe_decimal_conversion(record.get('repayment_amount')) for record in reloan_records)
    
    fresh_collected_amount = sum(safe_decimal_conversion(record.get('total_received')) for record in fresh_records)
    reloan_collected_amount = sum(safe_decimal_conversion(record.get('total_received')) for record in reloan_records)
    
    pending_collection = repayment_amount - collected_amount
    fresh_pending_amount = fresh_repayment_amount - fresh_collected_amount
    reloan_pending_amount = reloan_repayment_amount - reloan_collected_amount
    
    # Calculate principal outstanding (SUM(net_disbursal) - SUM(total_received) WHERE closed_status = 'Not Closed')
    not_closed_records = [r for r in records if r.get('closed_status') == 'Not Closed']
    not_closed_fresh_records = [r for r in fresh_records if r.get('closed_status') == 'Not Closed']
    not_closed_reloan_records = [r for r in reloan_records if r.get('closed_status') == 'Not Closed']
    
    principal_outstanding = sum(safe_decimal_conversion(r.get('net_disbursal')) for r in not_closed_records) - sum(safe_decimal_conversion(r.get('total_received')) for r in not_closed_records)
    
    fresh_principal_outstanding = sum(safe_decimal_conversion(r.get('net_disbursal')) for r in not_closed_fresh_records) - sum(safe_decimal_conversion(r.get('total_received')) for r in not_closed_fresh_records)
    
    reloan_principal_outstanding = sum(safe_decimal_conversion(r.get('net_disbursal')) for r in not_closed_reloan_records) - sum(safe_decimal_conversion(r.get('total_received')) for r in not_closed_reloan_records)
    
    # Calculate percentages
    fresh_percentage = round((fresh_cases / total_applications) * 100, 2) if total_applications > 0 else 0
    reloan_percentage = round((reloan_cases / total_applications) * 100, 2) if total_applications > 0 else 0
    collection_rate = round((collected_amount / repayment_amount) * 100, 2) if repayment_amount > 0 else 0
    
    # Calculate collected and pending percentages of repayment
    collected_percentage = collection_rate  # Same as collection rate
    pending_percentage = round(100 - collection_rate, 2) if collection_rate > 0 else 0
    
    # Calculate Principal Outstanding Excluding 90+ Days DPD (Recovery %)
    # Filter records where overdue_days <= 90
    records_excl_90_dpd = [r for r in records if int(r.get('overdue_days', 0)) <= 90]
    
    # Calculate for all records (excl 90+)
    sanction_amount_excl_90 = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in records_excl_90_dpd)
    amount_received_excl_90 = sum(safe_decimal_conversion(r.get('total_received', 0)) for r in records_excl_90_dpd)
    interest_amount_excl_90 = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in records_excl_90_dpd)
    
    recoverable_amount_excl_90 = amount_received_excl_90 - interest_amount_excl_90
    recovery_percentage_excl_90 = float((recoverable_amount_excl_90 / sanction_amount_excl_90) * 100) if sanction_amount_excl_90 > 0 else 0
    
    # Calculate for Fresh loans (excl 90+)
    fresh_records_excl_90 = [r for r in records_excl_90_dpd if r.get('reloan_status') != 'Reloan']
    fresh_sanction_excl_90 = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in fresh_records_excl_90)
    fresh_received_excl_90 = sum(safe_decimal_conversion(r.get('total_received', 0)) for r in fresh_records_excl_90)
    fresh_interest_excl_90 = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in fresh_records_excl_90)
    
    fresh_recoverable_excl_90 = fresh_received_excl_90 - fresh_interest_excl_90
    fresh_recovery_percentage_excl_90 = float((fresh_recoverable_excl_90 / fresh_sanction_excl_90) * 100) if fresh_sanction_excl_90 > 0 else 0
    
    # Calculate for Reloan loans (excl 90+)
    reloan_records_excl_90 = [r for r in records_excl_90_dpd if r.get('reloan_status') == 'Reloan']
    reloan_sanction_excl_90 = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in reloan_records_excl_90)
    reloan_received_excl_90 = sum(safe_decimal_conversion(r.get('total_received', 0)) for r in reloan_records_excl_90)
    reloan_interest_excl_90 = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in reloan_records_excl_90)
    
    reloan_recoverable_excl_90 = reloan_received_excl_90 - reloan_interest_excl_90
    reloan_recovery_percentage_excl_90 = float((reloan_recoverable_excl_90 / reloan_sanction_excl_90) * 100) if reloan_sanction_excl_90 > 0 else 0
    
    return {
        'total_applications': total_applications,
        'sanction_amount': float(sanction_amount),
        'net_disbursal': float(net_disbursal),
        'repayment_amount': float(repayment_amount),
        'collected_amount': float(collected_amount),
        'pending_collection': float(pending_collection),
        'principal_outstanding': float(principal_outstanding),
        'collection_rate': collection_rate,
        'collected_percentage': collected_percentage,
        'pending_percentage': pending_percentage,
        'fresh_cases': fresh_cases,
        'reloan_cases': reloan_cases,
        'fresh_percentage': fresh_percentage,
        'reloan_percentage': reloan_percentage,
        'fresh_sanction_amount': float(fresh_sanction_amount),
        'reloan_sanction_amount': float(reloan_sanction_amount),
        'fresh_disbursed_amount': float(fresh_disbursed_amount),
        'reloan_disbursed_amount': float(reloan_disbursed_amount),
        'fresh_repayment_amount': float(fresh_repayment_amount),
        'reloan_repayment_amount': float(reloan_repayment_amount),
        'fresh_collected_amount': float(fresh_collected_amount),
        'reloan_collected_amount': float(reloan_collected_amount),
        'fresh_pending_amount': float(fresh_pending_amount),
        'reloan_pending_amount': float(reloan_pending_amount),
        'fresh_principal_outstanding': float(fresh_principal_outstanding),
        'reloan_principal_outstanding': float(reloan_principal_outstanding),
        # Add recovery calculation fields
        'recoverable_amount_excl_90': float(recoverable_amount_excl_90),
        'recovery_percentage_excl_90': round(recovery_percentage_excl_90, 2),
        'fresh_recoverable_excl_90': float(fresh_recoverable_excl_90),
        'fresh_recovery_percentage_excl_90': round(fresh_recovery_percentage_excl_90, 2),
        'reloan_recoverable_excl_90': float(reloan_recoverable_excl_90),
        'reloan_recovery_percentage_excl_90': round(reloan_recovery_percentage_excl_90, 2)
    }

def get_kpi_data(queryset):
    """Calculate KPI data for a given queryset"""
    total_applications = queryset.count()
    
    if total_applications == 0:
        return {
            'total_applications': 0,
            'fresh_cases': 0,
            'fresh_percentage': 0,
            'reloan_cases': 0,
            'reloan_percentage': 0,
            'fresh_sanction_amount': 0,
            'reloan_sanction_amount': 0,
            'fresh_disbursed_amount': 0,
            'reloan_disbursed_amount': 0,
            'fresh_repayment_amount': 0,
            'reloan_repayment_amount': 0,
            'fresh_collected_amount': 0,
            'reloan_collected_amount': 0,
            'fresh_pending_amount': 0,
            'reloan_pending_amount': 0,
            'principal_outstanding_amount': 0,
            'fresh_principal_outstanding': 0,
            'reloan_principal_outstanding': 0,
            'sanction_amount': 0,
            'disbursed_amount': 0,
            'repayment_amount': 0,
            'actual_repayment_amount': 0,
            'repayment_with_penalty': 0,
            'earning': 0,
            'penalty': 0,
            'collected_amount': 0,
            'collected_percentage': 0,
            'pending_collection': 0,
            'pending_percentage': 0,
        }
    
    # Calculate fresh and reloan cases
    fresh_queryset = queryset.filter(reloan_status='Freash')  # Note: "Freash" is the actual value in data
    reloan_queryset = queryset.filter(reloan_status='Reloan')
    
    fresh_cases = fresh_queryset.count()
    reloan_cases = reloan_queryset.count()
    
    # Calculate percentages
    fresh_percentage = (fresh_cases / total_applications * 100) if total_applications > 0 else 0
    reloan_percentage = (reloan_cases / total_applications * 100) if total_applications > 0 else 0
    
    # Calculate fresh and reloan amounts
    fresh_amounts = fresh_queryset.aggregate(
        fresh_sanction=Sum('loan_amount'),
        fresh_disbursed=Sum('net_disbursal'),
        fresh_repayment=Sum('repayment_amount'),
        fresh_collected=Sum('total_received'),
    )
    
    reloan_amounts = reloan_queryset.aggregate(
        reloan_sanction=Sum('loan_amount'),
        reloan_disbursed=Sum('net_disbursal'),
        reloan_repayment=Sum('repayment_amount'),
        reloan_collected=Sum('total_received'),
    )
    
    # Aggregate calculations
    aggregates = queryset.aggregate(
        total_sanction=Sum('loan_amount'),  # loan_amount is the sanction amount
        total_disbursed=Sum('net_disbursal'),  # net_disbursal is the actual disbursed amount
        total_repayment=Sum('repayment_amount'),
        total_received=Sum('total_received'),
    )

    sanction_amount = aggregates['total_sanction'] or Decimal('0')
    disbursed_amount = aggregates['total_disbursed'] or Decimal('0')
    repayment_amount = aggregates['total_repayment'] or Decimal('0')
    actual_repayment_amount = aggregates['total_received'] or Decimal('0')

    # Derived calculations
    repayment_with_penalty = repayment_amount
    earning = actual_repayment_amount - sanction_amount
    penalty = repayment_with_penalty - sanction_amount
    collected_amount = actual_repayment_amount
    pending_collection = repayment_amount - collected_amount

    # Percentages (rounded to 2 decimal places)
    collected_percentage = round((collected_amount / repayment_amount * 100), 2) if repayment_amount > 0 else 0
    pending_percentage = round(((repayment_amount - collected_amount) / repayment_amount * 100), 2) if repayment_amount > 0 else 0

    # Calculate fresh and reloan pending amounts
    fresh_pending_amount = (fresh_amounts['fresh_repayment'] or 0) - (fresh_amounts['fresh_collected'] or 0)
    reloan_pending_amount = (reloan_amounts['reloan_repayment'] or 0) - (reloan_amounts['reloan_collected'] or 0)
    
    # Calculate principal outstanding (SUM(net_disbursal) - SUM(total_received) WHERE closed_status = 'Not Closed')
    not_closed_queryset = queryset.filter(closed_status='Not Closed')
    
    not_closed_totals = not_closed_queryset.aggregate(
        total_disbursal=Sum('net_disbursal'),
        total_received=Sum('total_received')
    )
    principal_outstanding_amount = (not_closed_totals['total_disbursal'] or Decimal('0')) - (not_closed_totals['total_received'] or Decimal('0'))
    
    # Calculate fresh and reloan principal outstanding amounts (only Not Closed records)
    fresh_not_closed = not_closed_queryset.filter(reloan_status='Freash').aggregate(
        total_disbursal=Sum('net_disbursal'),
        total_received=Sum('total_received')
    )
    fresh_principal_outstanding = (fresh_not_closed['total_disbursal'] or Decimal('0')) - (fresh_not_closed['total_received'] or Decimal('0'))
    
    reloan_not_closed = not_closed_queryset.filter(reloan_status='Reloan').aggregate(
        total_disbursal=Sum('net_disbursal'),
        total_received=Sum('total_received')
    )
    reloan_principal_outstanding = (reloan_not_closed['total_disbursal'] or Decimal('0')) - (reloan_not_closed['total_received'] or Decimal('0'))

    return {
        'total_applications': total_applications,
        'fresh_cases': fresh_cases,
        'fresh_percentage': float(fresh_percentage),
        'reloan_cases': reloan_cases,
        'reloan_percentage': float(reloan_percentage),
        'fresh_sanction_amount': float(fresh_amounts['fresh_sanction'] or 0),
        'reloan_sanction_amount': float(reloan_amounts['reloan_sanction'] or 0),
        'fresh_disbursed_amount': float(fresh_amounts['fresh_disbursed'] or 0),
        'reloan_disbursed_amount': float(reloan_amounts['reloan_disbursed'] or 0),
        'fresh_repayment_amount': float(fresh_amounts['fresh_repayment'] or 0),
        'reloan_repayment_amount': float(reloan_amounts['reloan_repayment'] or 0),
        'fresh_collected_amount': float(fresh_amounts['fresh_collected'] or 0),
        'reloan_collected_amount': float(reloan_amounts['reloan_collected'] or 0),
        'fresh_pending_amount': float(fresh_pending_amount),
        'reloan_pending_amount': float(reloan_pending_amount),
        'principal_outstanding_amount': float(principal_outstanding_amount),
        'fresh_principal_outstanding': float(fresh_principal_outstanding),
        'reloan_principal_outstanding': float(reloan_principal_outstanding),
        'sanction_amount': float(sanction_amount),
        'disbursed_amount': float(disbursed_amount),
        'repayment_amount': float(repayment_amount),
        'actual_repayment_amount': float(actual_repayment_amount),
        'repayment_with_penalty': float(repayment_with_penalty),
        'earning': float(earning),
        'penalty': float(penalty),
        'collected_amount': float(collected_amount),
        'collected_percentage': float(collected_percentage),
        'pending_collection': float(pending_collection),
        'pending_percentage': float(pending_percentage),
    }


@login_required
def dashboard_view(request):
    """Main dashboard view - now uses external API data directly"""
    # Get filter parameters
    filters = {
        'date_from': request.GET.get('date_from'),
        'date_to': request.GET.get('date_to'),
        'date_type': request.GET.get('date_type', 'repayment_date'),  # Default to repayment_date
        'closing_status': request.GET.get('closing_status'),
        'dpd': request.GET.get('dpd'),
        'state': request.GET.get('state'),
        'city': request.GET.get('city'),
    }
    
    try:
        # Fetch data from the Collection WITH Fraud API (same as api_kpi_data)
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])

        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)

        # Calculate KPIs from filtered records
        kpis = calculate_kpi_from_records(filtered_records)
        
        # Extract unique values from FILTERED external API data for filter options
        unique_states = sorted(list(set(record.get('state', '') for record in filtered_records if record.get('state'))))
        unique_cities = sorted(list(set(record.get('city', '') for record in filtered_records if record.get('city'))))
        
        # Get unique closed statuses and filter out Active and Closed
        all_closed_statuses = list(set(record.get('closed_status', '') for record in filtered_records if record.get('closed_status')))
        unique_closed_statuses = [status for status in all_closed_statuses if status not in ['Active', 'Closed']]
        
        # Normalize DPD buckets for filter dropdown
        dpd_bucket_mapping = {
            '0': '0 days DPD',
            '0-30': 'DPD 1-30',
            'DPD 1-30': 'DPD 1-30',
            '31-60': 'DPD 31-60',
            'DPD 31-60': 'DPD 31-60',
            '61-90': 'DPD 61-90',
            'DPD 61-90': 'DPD 61-90',
            '91-120': 'DPD 91-120',
            'No DPD': 'No DPD'
        }
        
        raw_dpd_buckets = list(set(record.get('dpd_bucket', '') for record in filtered_records if record.get('dpd_bucket')))
        normalized_dpd_buckets = set()
        
        for bucket in raw_dpd_buckets:
            normalized_bucket = dpd_bucket_mapping.get(bucket, bucket)
            normalized_dpd_buckets.add(normalized_bucket)
        
        # Convert to sorted list for consistent ordering
        bucket_order = ['0 days DPD', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 91-120', 'No DPD']
        unique_dpd_buckets = [bucket for bucket in bucket_order if bucket in normalized_dpd_buckets]
        
    except Exception as e:
        logger.error(f"Error fetching data for dashboard view: {e}")
        # Fallback to empty data
        kpis = {
            'total_applications': 0,
            'sanction_amount': 0,
            'net_disbursal': 0,
            'repayment_amount': 0,
            'collected_amount': 0,
            'pending_collection': 0,
            'principal_outstanding': 0,
            'collection_rate': 0,
            'collected_percentage': 0,
            'pending_percentage': 0,
            'fresh_cases': 0,
            'reloan_cases': 0,
            'fresh_percentage': 0,
            'reloan_percentage': 0,
            'fresh_sanction_amount': 0,
            'reloan_sanction_amount': 0,
            'fresh_disbursed_amount': 0,
            'reloan_disbursed_amount': 0,
            'fresh_repayment_amount': 0,
            'reloan_repayment_amount': 0,
            'fresh_collected_amount': 0,
            'reloan_collected_amount': 0,
            'fresh_pending_amount': 0,
            'reloan_pending_amount': 0,
            'fresh_principal_outstanding': 0,
            'reloan_principal_outstanding': 0
        }
    
        # Fallback to empty filter options
        unique_states = []
        unique_cities = []
        unique_closed_statuses = []
        unique_dpd_buckets = []
    
    # Get unique values for filters from FILTERED external API data
    try:
        # Use the filtered_records that were already calculated above
        # This ensures filter options match the currently displayed data
        
        # Extract unique values from FILTERED external API data
        unique_states = sorted(list(set(record.get('state', '') for record in filtered_records if record.get('state'))))
        unique_cities = sorted(list(set(record.get('city', '') for record in filtered_records if record.get('city'))))
        
        # Get unique closed statuses and filter out Active and Closed
        all_closed_statuses = list(set(record.get('closed_status', '') for record in filtered_records if record.get('closed_status')))
        unique_closed_statuses = [status for status in all_closed_statuses if status not in ['Active', 'Closed']]
        
        # Normalize DPD buckets for filter dropdown
        dpd_bucket_mapping = {
            '0': '0 days DPD',
            '0-30': 'DPD 1-30',
            'DPD 1-30': 'DPD 1-30',
            '31-60': 'DPD 31-60',
            'DPD 31-60': 'DPD 31-60',
            '61-90': 'DPD 61-90',
            'DPD 61-90': 'DPD 61-90',
            'DPD 91-120': 'DPD 91-120',
            'No DPD': 'No DPD'
        }
        
        raw_dpd_buckets = list(set(record.get('dpd_bucket', '') for record in filtered_records if record.get('dpd_bucket')))
        normalized_dpd_buckets = set()
        
        for bucket in raw_dpd_buckets:
            normalized_bucket = dpd_bucket_mapping.get(bucket, bucket)
            normalized_dpd_buckets.add(normalized_bucket)
        
        # Convert to sorted list for consistent ordering
        bucket_order = ['0 days DPD', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 91-120', 'No DPD']
        unique_dpd_buckets = [bucket for bucket in bucket_order if bucket in normalized_dpd_buckets]
        
    except Exception as e:
        logger.error(f"Error fetching filter options from external API: {e}")
        # Fallback to empty lists
        unique_states = []
        unique_cities = []
        unique_closed_statuses = []
        unique_dpd_buckets = []
    
    context = {
        'kpis': kpis,
        'filters': filters,
        'unique_states': unique_states,
        'unique_cities': unique_cities,
        'unique_dpd_buckets': unique_dpd_buckets,
        'unique_closed_statuses': unique_closed_statuses,
    }
    
    return render(request, 'dashboard/dashboard.html', context)


def calculate_kpis(queryset):
    """Calculate KPI metrics from queryset"""
    total_applications = queryset.count()
    
    if total_applications == 0:
        return {
            'total_applications': 0,
            'sanction_amount': 0,
            'disbursed_amount': 0,
            'repayment_amount': 0,
            'actual_repayment_amount': 0,
            'repayment_with_penalty': 0,
            'earning': 0,
            'penalty': 0,
            'collected_amount': 0,
            'collected_percentage': 0,
            'pending_collection': 0,
            'pending_percentage': 0,
        }
    
    # Aggregate calculations
    aggregates = queryset.aggregate(
        total_sanction=Sum('loan_amount'),  # loan_amount is the sanction amount
        total_disbursed=Sum('net_disbursal'),  # net_disbursal is the actual disbursed amount
        total_repayment=Sum('repayment_amount'),
        total_received=Sum('total_received'),
    )
    
    sanction_amount = aggregates['total_sanction'] or Decimal('0')
    disbursed_amount = aggregates['total_disbursed'] or Decimal('0')
    repayment_amount = aggregates['total_repayment'] or Decimal('0')
    actual_repayment_amount = aggregates['total_received'] or Decimal('0')
    
    # Derived calculations
    repayment_with_penalty = repayment_amount
    earning = actual_repayment_amount - sanction_amount
    penalty = repayment_with_penalty - sanction_amount
    collected_amount = actual_repayment_amount
    pending_collection = repayment_amount - collected_amount
    
    # Percentages (rounded to 2 decimal places)
    collected_percentage = round((collected_amount / repayment_amount * 100), 2) if repayment_amount > 0 else 0
    pending_percentage = round(((repayment_amount - collected_amount) / repayment_amount * 100), 2) if repayment_amount > 0 else 0
    
    return {
        'total_applications': total_applications,
        'sanction_amount': float(sanction_amount),
        'disbursed_amount': float(disbursed_amount),
        'repayment_amount': float(repayment_amount),
        'actual_repayment_amount': float(actual_repayment_amount),
        'repayment_with_penalty': float(repayment_with_penalty),
        'earning': float(earning),
        'penalty': float(penalty),
        'collected_amount': float(collected_amount),
        'collected_percentage': float(collected_percentage),
        'pending_collection': float(pending_collection),
        'pending_percentage': float(pending_percentage),
    }


@require_http_methods(["GET"])
@no_cache_api
def api_dpd_buckets(request):
    """API endpoint for DPD bucket data from Collection WITH Fraud API"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'data': []})
        
        # Store the selected DPD bucket for highlighting
        selected_dpd = request.GET.get('dpd')
    
        # Group by DPD bucket
        bucket_data = {}
        for record in filtered_records:
            dpd_bucket = record.get('dpd_bucket', 'Unknown')
            if dpd_bucket not in bucket_data:
                bucket_data[dpd_bucket] = {
                    'dpd_bucket': dpd_bucket,
                    'count': 0,
                    'total_disbursal': Decimal('0'),
                    'total_due': Decimal('0')
                }
            
            bucket_data[dpd_bucket]['count'] += 1
            bucket_data[dpd_bucket]['total_disbursal'] += Decimal(str(record.get('net_disbursal', 0)))
            bucket_data[dpd_bucket]['total_due'] += Decimal(str(record.get('repayment_amount', 0)))
        
        # Convert to list and format
        result = []
        for bucket_info in bucket_data.values():
            dpd_bucket = bucket_info['dpd_bucket']
            result.append({
                'dpd_bucket': dpd_bucket,
                'count': bucket_info['count'],
                'total_disbursal': float(bucket_info['total_disbursal']),
                'total_due': float(bucket_info['total_due']),
                'is_selected': dpd_bucket == selected_dpd if selected_dpd else False
            })
        
        # Sort by bucket name
        result.sort(key=lambda x: x['dpd_bucket'])
        
        return JsonResponse({'data': result})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_state_repayment(request):
    """API endpoint for state-wise repayment data from Collection WITH Fraud API"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'data': []})
        
        # Group by state and calculate aggregates
        state_data = {}
        for record in filtered_records:
            state = record.get('state', 'Unknown')
            if state not in state_data:
                state_data[state] = {
                    'repayment_amount': Decimal('0'),
                    'collected_amount': Decimal('0')
                }

            repayment_amt = Decimal(str(record.get('repayment_amount', 0)))
            collected_amt = Decimal(str(record.get('total_received', 0)))

            state_data[state]['repayment_amount'] += repayment_amt
            state_data[state]['collected_amount'] += collected_amt

        # Convert to list and format
        result = []
        for state, values in state_data.items():
            repayment_total = values['repayment_amount']
            collected_total = values['collected_amount']
            pending_total = repayment_total - collected_total
            if pending_total < 0:
                pending_total = Decimal('0')

            result.append({
                'state': state,
                'repayment_amount': float(repayment_total),
                'collected_amount': float(collected_total),
                'pending_amount': float(pending_total)
            })

        # Sort by pending amount (highest first) for Pending Amount by State chart
        result.sort(key=lambda x: x['pending_amount'], reverse=True)
        
        return JsonResponse({'data': result})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_kpi_data(request):
    """API endpoint for KPI data - now uses Collection WITH Fraud API directly"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])

        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)

        # Calculate KPIs from filtered records
        kpi_data = calculate_kpi_from_records(filtered_records)

        # Calculate Principal Outstanding Excluding 90+ Days DPD (Recovery %)
        # Filter records where overdue_days <= 90
        records_excl_90_dpd = [r for r in filtered_records if int(r.get('overdue_days', 0)) <= 90]
        
        # Calculate for all records (excl 90+)
        sanction_amount_excl_90 = sum(Decimal(str(r.get('loan_amount', 0))) for r in records_excl_90_dpd)
        amount_received_excl_90 = sum(Decimal(str(r.get('total_received', 0))) for r in records_excl_90_dpd)
        interest_amount_excl_90 = sum(Decimal(str(r.get('interest_amount', 0))) for r in records_excl_90_dpd)
        
        recoverable_amount_excl_90 = amount_received_excl_90 - interest_amount_excl_90
        recovery_percentage_excl_90 = float((recoverable_amount_excl_90 / sanction_amount_excl_90) * 100) if sanction_amount_excl_90 > 0 else 0
        
        # Calculate for Fresh loans (excl 90+)
        fresh_records_excl_90 = [r for r in records_excl_90_dpd if r.get('reloan_status') != 'Reloan']
        fresh_sanction_excl_90 = sum(Decimal(str(r.get('loan_amount', 0))) for r in fresh_records_excl_90)
        fresh_received_excl_90 = sum(Decimal(str(r.get('total_received', 0))) for r in fresh_records_excl_90)
        fresh_interest_excl_90 = sum(Decimal(str(r.get('interest_amount', 0))) for r in fresh_records_excl_90)
        
        fresh_recoverable_excl_90 = fresh_received_excl_90 - fresh_interest_excl_90
        fresh_recovery_percentage_excl_90 = float((fresh_recoverable_excl_90 / fresh_sanction_excl_90) * 100) if fresh_sanction_excl_90 > 0 else 0
        
        # Calculate for Reloan loans (excl 90+)
        reloan_records_excl_90 = [r for r in records_excl_90_dpd if r.get('reloan_status') == 'Reloan']
        reloan_sanction_excl_90 = sum(Decimal(str(r.get('loan_amount', 0))) for r in reloan_records_excl_90)
        reloan_received_excl_90 = sum(Decimal(str(r.get('total_received', 0))) for r in reloan_records_excl_90)
        reloan_interest_excl_90 = sum(Decimal(str(r.get('interest_amount', 0))) for r in reloan_records_excl_90)
        
        reloan_recoverable_excl_90 = reloan_received_excl_90 - reloan_interest_excl_90
        reloan_recovery_percentage_excl_90 = float((reloan_recoverable_excl_90 / reloan_sanction_excl_90) * 100) if reloan_sanction_excl_90 > 0 else 0
        
        # Add to KPI data
        kpi_data['recoverable_amount_excl_90'] = float(recoverable_amount_excl_90)
        kpi_data['recovery_percentage_excl_90'] = round(recovery_percentage_excl_90, 2)
        kpi_data['fresh_recoverable_excl_90'] = float(fresh_recoverable_excl_90)
        kpi_data['fresh_recovery_percentage_excl_90'] = round(fresh_recovery_percentage_excl_90, 2)
        kpi_data['reloan_recoverable_excl_90'] = float(reloan_recoverable_excl_90)
        kpi_data['reloan_recovery_percentage_excl_90'] = round(reloan_recovery_percentage_excl_90, 2)

        # Extract filter options for dropdowns from FILTERED records (use actual city names, not normalized)
        unique_states = sorted(list(set(record.get('state', '') for record in filtered_records if record.get('state'))))
        unique_cities = sorted(list(set(record.get('city', '').strip() for record in filtered_records if record.get('city', '').strip())))
        all_closed_statuses = list(set(record.get('closed_status', '') for record in filtered_records if record.get('closed_status')))
        unique_closed_statuses = [status for status in all_closed_statuses if status not in ['Active', 'Closed']]
        
        # Get unique DPD buckets and normalize them from filtered records
        all_dpd_buckets = list(set(record.get('dpd_bucket', '') for record in filtered_records if record.get('dpd_bucket')))
        normalized_dpd_buckets = [normalize_dpd_bucket(bucket) for bucket in all_dpd_buckets if bucket]
        bucket_order = ['0 days DPD', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 91-120', 'DPD 121-150', 'DPD 151-180', 'DPD 181-365', 'DPD 365+', 'No DPD']
        unique_dpd_buckets = [bucket for bucket in bucket_order if bucket in normalized_dpd_buckets]

        return JsonResponse({
            'data': kpi_data,
            'filter_options': {
                'states': unique_states,
                'cities': unique_cities,
                'closing_statuses': unique_closed_statuses,
                'dpd_buckets': unique_dpd_buckets
            }
        })
    except Exception as e:
        logger.error(f"Error fetching KPI data: {e}")
        return JsonResponse({'error': 'Failed to fetch data'}, status=500)

@require_http_methods(["GET"])
@no_cache_api
def api_city_collected(request):
    """API endpoint for top 10 cities by collection percentage from Collection WITH Fraud API"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'data': []})

    # Group by city and calculate collection metrics
        city_data = {}
        for record in filtered_records:
            city = record.get('city', 'Unknown')
            normalized_city = normalize_city_name(city)
            
            if normalized_city not in city_data:
                city_data[normalized_city] = {
                'city': normalized_city,
                    'collected_amount': Decimal('0'),
                    'repayment_amount': Decimal('0'),
                'total_applications': 0
            }
        
            city_data[normalized_city]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
            city_data[normalized_city]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
            city_data[normalized_city]['total_applications'] += 1
        
        # Convert to list and calculate collection percentage
        result = []
        for city_info in city_data.values():
            # Only include cities with minimum 20 loans and repayment amounts > 0 to avoid division by zero
            if (city_info['total_applications'] >= 20 and 
                city_info['repayment_amount'] > 0):
                collection_percentage = float((city_info['collected_amount'] / city_info['repayment_amount']) * 100)

                result.append({
                    'city': city_info['city'],
                    'collected_amount': float(city_info['collected_amount']),
                    'repayment_amount': float(city_info['repayment_amount']),
                    'collection_percentage': collection_percentage,
                    'total_applications': city_info['total_applications']
                })

        # Sort by collection percentage (highest first) and take top 10
        result.sort(key=lambda x: x['collection_percentage'], reverse=True)
        result = result[:10]

        return JsonResponse({'data': result})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_city_uncollected(request):
    """API endpoint for top 10 cities by collection percentage (worst performers) from Collection WITH Fraud API"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'data': []})

    # Group by city and calculate collection metrics
        city_data = {}
        for record in filtered_records:
            city = record.get('city', 'Unknown')
            normalized_city = normalize_city_name(city)
            
            if normalized_city not in city_data:
                city_data[normalized_city] = {
                'city': normalized_city,
                    'collected_amount': Decimal('0'),
                    'repayment_amount': Decimal('0'),
                'total_applications': 0
            }
        
            city_data[normalized_city]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
            city_data[normalized_city]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
            city_data[normalized_city]['total_applications'] += 1
        
        # Convert to list and calculate collection percentage
        result = []
        for city_info in city_data.values():
            # Only include cities with minimum 20 loans and repayment amounts > 0 to avoid division by zero
            if (city_info['total_applications'] >= 20 and 
                city_info['repayment_amount'] > 0):
                collection_percentage = float((city_info['collected_amount'] / city_info['repayment_amount']) * 100)
                uncollected_amount = float(city_info['repayment_amount'] - city_info['collected_amount'])

                result.append({
                    'city': city_info['city'],
                    'collected_amount': float(city_info['collected_amount']),
                    'repayment_amount': float(city_info['repayment_amount']),
                    'uncollected_amount': uncollected_amount,
                    'collection_percentage': collection_percentage,
                    'total_applications': city_info['total_applications']
                })

        # Sort by collection percentage (lowest first - worst performers) and take top 10
        result.sort(key=lambda x: x['collection_percentage'], reverse=False)
        result = result[:10]

        return JsonResponse({'data': result})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_time_series(request):
    """API endpoint for time series data from Collection WITH Fraud API"""
    try:
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)

        if not filtered_records:
            return JsonResponse({'data': []})
    
    # Group by repayment date
        date_data = {}
        for record in filtered_records:
            repayment_date_str = record.get('repayment_date')
            if repayment_date_str:
                try:
                    # Parse datetime safely - handles both UTC and IST formats
                    repayment_date = parse_datetime_safely(repayment_date_str)
                    if repayment_date:
                        date_key = repayment_date.strftime('%Y-%m-%d')
                        
                        if date_key not in date_data:
                            date_data[date_key] = {
                                'date': date_key,
                                'repayment_amount': Decimal('0'),
                                'collected_amount': Decimal('0'),
                                'collected_cases': 0,
                                'pending_cases': 0
                            }
                        
                        date_data[date_key]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
                        date_data[date_key]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
                        
                        # Count cases - a case is collected if total_received > 0, otherwise pending
                        total_received = Decimal(str(record.get('total_received', 0)))
                        if total_received > 0:
                            date_data[date_key]['collected_cases'] += 1
                        else:
                            date_data[date_key]['pending_cases'] += 1
                except:
                    continue
        
        # Convert to list and format
        time_series_data = []
        for date_info in date_data.values():
            repayment_amount = float(date_info['repayment_amount'])
            collected_amount = float(date_info['collected_amount'])
            pending_amount = repayment_amount - collected_amount
            collection_percentage = (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
            time_series_data.append({
                'date': date_info['date'],
                'repayment_amount': repayment_amount,
                'collected_amount': collected_amount,
                'pending_amount': pending_amount,
                'collected_cases': date_info['collected_cases'],
                'pending_cases': date_info['pending_cases'],
                'collection_percentage': collection_percentage
            })
        
        # Sort by date
        time_series_data.sort(key=lambda x: x['date'])
        
        return JsonResponse({'data': time_series_data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def sync_data(request):
    """API endpoint to manually sync data from external API"""
    try:
        sync_service = DataSyncService()
        synced_count = sync_service.sync_loan_data()
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully synced {synced_count} new records',
            'synced_count': synced_count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error syncing data: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_dpd_bucket_details(request):
    """API endpoint for detailed DPD bucket data from Collection WITH Fraud API"""
    try:
        dpd_bucket = request.GET.get('dpd_bucket')
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        sort_by = request.GET.get('sort_by', 'overdue_days')
        sort_order = request.GET.get('sort_order', 'desc')
        
        if not dpd_bucket:
            return JsonResponse({'error': 'DPD bucket is required'}, status=400)
        
        # Fetch data from the Collection WITH Fraud API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('pr', [])
        
        # Apply filters to the records (date range, state, city, closing status, etc.)
        filtered_records = apply_fraud_filters(records, request)
        
        # Filter by DPD bucket
        bucket_filtered_records = [r for r in filtered_records if r.get('dpd_bucket') == dpd_bucket]
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            bucket_filtered_records = [
                r for r in bucket_filtered_records 
                if (search_lower in str(r.get('loan_no', '')).lower() or 
                    search_lower in str(r.get('pan', '')).lower())
            ]
        
        # Calculate totals
        total_net_disbursal = sum(Decimal(str(r.get('net_disbursal', 0))) for r in bucket_filtered_records)
        total_repayment_amount = sum(Decimal(str(r.get('repayment_amount', 0))) for r in bucket_filtered_records)
        
        # Sort records
        reverse = (sort_order == 'desc')
        if sort_by == 'overdue_days':
            bucket_filtered_records.sort(key=lambda x: int(x.get('overdue_days', 0)), reverse=reverse)
        elif sort_by == 'net_disbursal':
            bucket_filtered_records.sort(key=lambda x: float(x.get('net_disbursal', 0)), reverse=reverse)
        elif sort_by == 'repayment_amount':
            bucket_filtered_records.sort(key=lambda x: float(x.get('repayment_amount', 0)), reverse=reverse)
        elif sort_by == 'loan_no':
            bucket_filtered_records.sort(key=lambda x: str(x.get('loan_no', '')), reverse=reverse)
        
        # Calculate pagination
        total_records = len(bucket_filtered_records)
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_records = bucket_filtered_records[start_idx:end_idx]
        
        # Format the data
        formatted_records = []
        for record in page_records:
            disbursal_date_str = record.get('disbursal_date')
            repayment_date_str = record.get('repayment_date')
            
            # Parse and format dates
            disbursal_date_formatted = '—'
            if disbursal_date_str:
                parsed_date = parse_datetime_safely(disbursal_date_str)
                if parsed_date:
                    disbursal_date_formatted = parsed_date.strftime('%d/%m/%Y')
            
            repayment_date_formatted = '—'
            if repayment_date_str:
                parsed_date = parse_datetime_safely(repayment_date_str)
                if parsed_date:
                    repayment_date_formatted = parsed_date.strftime('%d/%m/%Y')
            
            formatted_records.append({
                'loan_no': record.get('loan_no', ''),
                'pan': str(record.get('pan', '')).upper() if record.get('pan') else '',
                'disbursal_date': disbursal_date_formatted,
                'net_disbursal': float(record.get('net_disbursal', 0)),
                'repayment_date': repayment_date_formatted,
                'repayment_amount': float(record.get('repayment_amount', 0)),
                'overdue_days': int(record.get('overdue_days', 0)),
                'dpd_bucket': record.get('dpd_bucket', ''),
            })
        
        return JsonResponse({
            'records': formatted_records,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_records': total_records,
                'per_page': per_page,
                'has_next': page < total_pages,
                'has_previous': page > 1,
            },
            'totals': {
                'total_net_disbursal': float(total_net_disbursal),
                'total_repayment_amount': float(total_repayment_amount),
            },
            'dpd_bucket': dpd_bucket,
            'search': search,
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Authentication Views
def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                # Get the next URL parameter for redirect after login
                next_url = request.GET.get('next', '/dashboard/')
                
                # Handle AJAX requests
                if request.headers.get('X-CSRFToken') or request.headers.get('Content-Type') == 'application/x-www-form-urlencoded':
                    return JsonResponse({'success': True, 'redirect_url': next_url})
                
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please fill in all fields.')
    
    return render(request, 'dashboard/login.html')


def logout_view(request):
    """Handle user logout"""
    # Clear any cached data
    cache.clear()
    
    # Logout the user
    logout(request)
    
    # Clear session data
    request.session.flush()
    
    messages.info(request, 'You have been logged out successfully.')
    return redirect('dashboard:login')


@require_http_methods(["GET"])
def api_cities_by_state(request):
    """API endpoint to get cities for a selected state based on current filters"""
    state = request.GET.get('state')
    
    if not state:
        return JsonResponse({'cities': []})
    
    try:
        # Get data from external API (same as other endpoints)
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])
        
        # Apply the same filters as other endpoints (date range, etc.) but exclude state/city filters
        filtered_records = []
        
        # Apply date range filter if provided
        if request.GET.get('date_from') and request.GET.get('date_to'):
            try:
                # Parse dates as IST dates (user input)
                date_from = datetime.strptime(request.GET.get('date_from'), '%Y-%m-%d').date()
                date_to = datetime.strptime(request.GET.get('date_to'), '%Y-%m-%d').date()
                date_type = request.GET.get('date_type', 'repayment_date')
                
                for r in records:
                    if r.get(date_type):
                        # parse_datetime_safely now converts UTC to IST
                        parsed_date = parse_datetime_safely(r[date_type])
                        if parsed_date and date_from <= parsed_date <= date_to:
                            filtered_records.append(r)
                records = filtered_records
            except (ValueError, AttributeError):
                pass
        
        # Apply other filters (excluding state and city)
        if request.GET.get('closing_status'):
            records = [r for r in records if r.get('closed_status') == request.GET.get('closing_status')]
        
        if request.GET.get('dpd'):
            records = [r for r in records if r.get('dpd_bucket') == request.GET.get('dpd')]
        
        # Filter by the selected state
        state_records = [r for r in records if r.get('state') == state]
        
        # Extract cities from the filtered records and apply normalization
        cities = set()
        for record in state_records:
            city = record.get('city')
            if city:
                normalized_city = normalize_city_name(city)
                cities.add(normalized_city)
        
        return JsonResponse({'cities': sorted(list(cities))})
    
    except Exception as e:
        logger.error(f"Error fetching cities for state {state}: {e}")
        return JsonResponse({'cities': []})

@require_http_methods(["GET"])
def api_total_applications_details(request):
    """API endpoint for detailed total applications data - now uses external API"""
    import requests
    from datetime import datetime
    
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    sort_by = request.GET.get('sort_by', 'disbursal_date')
    sort_order = request.GET.get('sort_order', 'desc')
    
    try:
        # Fetch data from external API (same as api_kpi_data)
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])
        
        # Apply filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        # Apply search filter
        if search:
            filtered_records = [
                record for record in filtered_records
                if (search.lower() in (record.get('loan_no', '') or '').lower() or
                    search.lower() in (record.get('pan', '') or '').lower())
            ]
        
        # Apply sorting
        if sort_by in filtered_records[0] if filtered_records else False:
            reverse = sort_order == 'desc'
            filtered_records.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse)
        
        # Calculate totals
        totals = {
            'total_loan_amount': sum(safe_decimal_conversion(record.get('loan_amount')) for record in filtered_records),
            'total_net_disbursal': sum(safe_decimal_conversion(record.get('net_disbursal')) for record in filtered_records),
            'total_repayment_amount': sum(safe_decimal_conversion(record.get('repayment_amount')) for record in filtered_records),
            'total_processing_fee': sum(safe_decimal_conversion(record.get('processing_fee')) for record in filtered_records),
            'total_interest_amount': sum(safe_decimal_conversion(record.get('interest_amount')) for record in filtered_records),
            'total_received': sum(safe_decimal_conversion(record.get('total_received')) for record in filtered_records)
        }
        
        # Apply pagination
        total_records = len(filtered_records)
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_records = filtered_records[start_index:end_index]
        
        # Format the data
        formatted_records = []
        for record in paginated_records:
            formatted_records.append({
                'loan_no': record.get('loan_no', '—'),
                'pan': (record.get('pan', '') or '').upper(),
                'disbursal_date': parse_datetime_safely(record.get('disbursal_date')).strftime('%d/%m/%Y') if record.get('disbursal_date') else '—',
                'loan_amount': float(safe_decimal_conversion(record.get('loan_amount'))),
                'net_disbursal': float(safe_decimal_conversion(record.get('net_disbursal'))),
                'tenure': record.get('tenure', '—'),
                'repayment_date': parse_datetime_safely(record.get('repayment_date')).strftime('%d/%m/%Y') if record.get('repayment_date') else '—',
                'repayment_amount': float(safe_decimal_conversion(record.get('repayment_amount'))),
                'processing_fee': float(safe_decimal_conversion(record.get('processing_fee'))),
                'interest_amount': float(safe_decimal_conversion(record.get('interest_amount'))),
                'last_received_date': parse_datetime_safely(record.get('last_received_date')).strftime('%d/%m/%Y') if record.get('last_received_date') else '—',
                'total_received': float(safe_decimal_conversion(record.get('total_received'))),
                'closed_status': record.get('closed_status', '—'),
            })
        
        # Calculate pagination info
        total_pages = (total_records + per_page - 1) // per_page  # Ceiling division
        has_next = page < total_pages
        has_previous = page > 1
        
        return JsonResponse({
            'records': formatted_records,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_records': total_records,
                'per_page': per_page,
                'has_next': has_next,
                'has_previous': has_previous,
            },
            'totals': {
                'total_loan_amount': float(totals['total_loan_amount']),
                'total_net_disbursal': float(totals['total_net_disbursal']),
                'total_repayment_amount': float(totals['total_repayment_amount']),
                'total_processing_fee': float(totals['total_processing_fee']),
                'total_interest_amount': float(totals['total_interest_amount']),
                'total_received': float(totals['total_received']),
            },
            'search': search,
        })
        
    except Exception as e:
        logger.error(f"Error fetching total applications details: {e}")
        return JsonResponse({
            'records': [],
            'pagination': {
                'current_page': 1,
                'total_pages': 0,
                'total_records': 0,
                'per_page': per_page,
                'has_next': False,
                'has_previous': False,
            },
            'totals': {
                'total_loan_amount': 0,
                'total_net_disbursal': 0,
                'total_repayment_amount': 0,
                'total_processing_fee': 0,
                'total_interest_amount': 0,
                'total_received': 0,
            },
            'search': search,
            'error': 'Failed to fetch data'
        }, status=500)

@require_http_methods(["GET"])
def api_fraud_total_applications_details(request):
    """API endpoint for detailed total applications data in fraud tab - uses external API with fraud filters"""
    import requests
    from datetime import datetime
    
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    sort_by = request.GET.get('sort_by', 'disbursal_date')
    sort_order = request.GET.get('sort_order', 'desc')
    
    try:
        # Fetch data from external API (same as api_kpi_data)
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])
        
        # Apply fraud filters to the records
        filtered_records = apply_fraud_filters(records, request)
        
        # Apply search filter
        if search:
            filtered_records = [
                record for record in filtered_records
                if (search.lower() in (record.get('loan_no', '') or '').lower() or
                    search.lower() in (record.get('pan', '') or '').lower())
            ]
        
        # Apply sorting
        if sort_by in filtered_records[0] if filtered_records else False:
            reverse = sort_order == 'desc'
            filtered_records.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse)
        
        # Calculate totals
        totals = {
            'total_loan_amount': sum(safe_decimal_conversion(record.get('loan_amount')) for record in filtered_records),
            'total_net_disbursal': sum(safe_decimal_conversion(record.get('net_disbursal')) for record in filtered_records),
            'total_repayment_amount': sum(safe_decimal_conversion(record.get('repayment_amount')) for record in filtered_records),
            'total_processing_fee': sum(safe_decimal_conversion(record.get('processing_fee')) for record in filtered_records),
            'total_interest_amount': sum(safe_decimal_conversion(record.get('interest_amount')) for record in filtered_records),
            'total_received': sum(safe_decimal_conversion(record.get('total_received')) for record in filtered_records)
        }
        
        # Apply pagination
        total_records = len(filtered_records)
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_records = filtered_records[start_index:end_index]
        
        # Format the data
        formatted_records = []
        for record in paginated_records:
            formatted_records.append({
                'loan_no': record.get('loan_no', '—'),
                'pan': (record.get('pan', '') or '').upper(),
                'disbursal_date': parse_datetime_safely(record.get('disbursal_date')).strftime('%d/%m/%Y') if record.get('disbursal_date') else '—',
                'loan_amount': float(safe_decimal_conversion(record.get('loan_amount'))),
                'net_disbursal': float(safe_decimal_conversion(record.get('net_disbursal'))),
                'tenure': record.get('tenure', '—'),
                'repayment_date': parse_datetime_safely(record.get('repayment_date')).strftime('%d/%m/%Y') if record.get('repayment_date') else '—',
                'repayment_amount': float(safe_decimal_conversion(record.get('repayment_amount'))),
                'processing_fee': float(safe_decimal_conversion(record.get('processing_fee'))),
                'interest_amount': float(safe_decimal_conversion(record.get('interest_amount'))),
                'last_received_date': parse_datetime_safely(record.get('last_received_date')).strftime('%d/%m/%Y') if record.get('last_received_date') else '—',
                'total_received': float(safe_decimal_conversion(record.get('total_received'))),
                'closed_status': record.get('closed_status', '—'),
            })
        
        # Calculate pagination info
        total_pages = (total_records + per_page - 1) // per_page  # Ceiling division
        has_next = page < total_pages
        has_previous = page > 1
        
        return JsonResponse({
            'records': formatted_records,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_records': total_records,
                'per_page': per_page,
                'has_next': has_next,
                'has_previous': has_previous,
            },
            'totals': {
                'total_loan_amount': float(totals['total_loan_amount']),
                'total_net_disbursal': float(totals['total_net_disbursal']),
                'total_repayment_amount': float(totals['total_repayment_amount']),
                'total_processing_fee': float(totals['total_processing_fee']),
                'total_interest_amount': float(totals['total_interest_amount']),
                'total_received': float(totals['total_received']),
            },
            'search': search,
        })
        
    except Exception as e:
        logger.error(f"Error fetching fraud total applications details: {e}")
        return JsonResponse({
            'records': [],
            'pagination': {
                'current_page': 1,
                'total_pages': 0,
                'total_records': 0,
                'per_page': per_page,
                'has_next': False,
                'has_previous': False,
            },
            'totals': {
                'total_loan_amount': 0,
                'total_net_disbursal': 0,
                'total_repayment_amount': 0,
                'total_processing_fee': 0,
                'total_interest_amount': 0,
                'total_received': 0,
            },
            'search': search,
            'error': 'Failed to fetch data'
        }, status=500)


# Helper function to apply date filters based on date_type
def apply_date_filter(queryset, request):
    """Apply date range filters based on date_type parameter with timezone awareness"""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    date_type = request.GET.get('date_type', 'repayment_date')
    
    if date_from and date_to:
        try:
            # Parse dates as IST dates
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            
            # Convert IST dates to UTC for database comparison
            # IST is UTC+5:30, so we need to subtract 5:30 to get UTC
            ist_offset = timedelta(hours=5, minutes=30)
            
            # Convert IST date range to UTC for database filtering
            date_from_utc = datetime.combine(date_from_obj, datetime.min.time()) - ist_offset
            date_to_utc = datetime.combine(date_to_obj, datetime.max.time()) - ist_offset
            
            # Filter based on the selected date type with proper timezone handling
            if date_type == 'disbursal_date':
                queryset = queryset.filter(
                    disbursal_date__gte=date_from_utc.date(),
                    disbursal_date__lt=date_to_utc.date() + timedelta(days=1)
                )
            else:  # default to repayment_date
                queryset = queryset.filter(
                    repayment_date__gte=date_from_utc.date(),
                    repayment_date__lt=date_to_utc.date() + timedelta(days=1)
                )
        except ValueError:
            pass
    
    return queryset

# Helper function to apply filters to fraud records
def normalize_city_name(city_name):
    """Normalize city names - group all Delhi, Mumbai, and Hyderabad districts under their respective main cities"""
    if not city_name:
        return city_name
    
    city_name = str(city_name).strip()
    
    # Check if city contains Delhi (case insensitive)
    if 'delhi' in city_name.lower():
        return 'Delhi'
    
    # Check if city contains Mumbai (case insensitive)
    if 'mumbai' in city_name.lower():
        return 'Mumbai'
    
    # Check if city contains Hyderabad districts (case insensitive)
    if 'medchal' in city_name.lower() or 'malkajgiri' in city_name.lower():
        return 'Hyderabad'
    
    return city_name

def normalize_dpd_bucket(bucket):
    """Normalize DPD bucket names"""
    if not bucket:
        return bucket
    
    # Define mapping for DPD buckets
    dpd_bucket_mapping = {
        '0': '0 days DPD',
        '0-30': 'DPD 1-30',
        'DPD 1-30': 'DPD 1-30',
        '31-60': 'DPD 31-60',
        'DPD 31-60': 'DPD 31-60',
        '61-90': 'DPD 61-90',
        'DPD 61-90': 'DPD 61-90',
        '91-120': 'DPD 91-120',
        'DPD 91-120': 'DPD 91-120',
        '121-150': 'DPD 121-150',
        'DPD 121-150': 'DPD 121-150',
        '151-180': 'DPD 151-180',
        'DPD 151-180': 'DPD 151-180',
        '181-365': 'DPD 181-365',
        'DPD 181-365': 'DPD 181-365',
        '365+': 'DPD 365+',
        'DPD 365+': 'DPD 365+',
        'No DPD': 'No DPD'
    }
    
    return dpd_bucket_mapping.get(bucket, bucket)

def apply_fraud_filters(records, request):
    """Apply filters to fraud records based on request parameters with timezone awareness"""
    if request.GET.get('date_from') and request.GET.get('date_to'):
        try:
            # Parse dates as IST dates (user input)
            date_from = datetime.strptime(request.GET.get('date_from'), '%Y-%m-%d').date()
            date_to = datetime.strptime(request.GET.get('date_to'), '%Y-%m-%d').date()
            date_type = request.GET.get('date_type', 'repayment_date')
            
            # Filter based on the selected date type with timezone-aware comparison
            if date_type == 'disbursal_date':
                filtered_records = []
                for r in records:
                    if r.get('disbursal_date'):
                        # parse_datetime_safely now converts UTC to IST
                        parsed_date = parse_datetime_safely(r['disbursal_date'])
                        if parsed_date and date_from <= parsed_date <= date_to:
                            filtered_records.append(r)
                records = filtered_records
            else:  # default to repayment_date
                filtered_records = []
                for r in records:
                    if r.get('repayment_date'):
                        # parse_datetime_safely now converts UTC to IST
                        parsed_date = parse_datetime_safely(r['repayment_date'])
                        if parsed_date and date_from <= parsed_date <= date_to:
                            filtered_records.append(r)
                records = filtered_records
        except (ValueError, AttributeError):
            pass
    
    if request.GET.get('closing_status'):
        records = [r for r in records if r.get('closed_status') == request.GET.get('closing_status')]
    
    if request.GET.get('dpd'):
        records = [r for r in records if r.get('dpd_bucket') == request.GET.get('dpd')]
    
    # Apply state and city filters with proper hierarchy
    state_filter = request.GET.get('state')
    city_filter = request.GET.get('city')
    
    if state_filter:
        # Filter by state first
        records = [r for r in records if r.get('state') == state_filter]
        
        if city_filter:
            # If both state and city are selected, filter by both
            # Use exact match, not normalization
            records = [r for r in records if r.get('city', '').strip() == city_filter.strip()]
    elif city_filter:
        # If only city is selected, filter by exact city name
        records = [r for r in records if r.get('city', '').strip() == city_filter.strip()]
    
    return records

# Fraud Summary API endpoints (using portfolio-collection-without-fraud API)
@no_cache_api
def api_fraud_kpi_data(request):
    """API endpoint for fraud summary KPI data"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array (now using 'cwpr' since we swapped the APIs)
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        records = apply_fraud_filters(records, request)
        
        if not records:
            return JsonResponse({
                'total_applications': 0,
                'fresh_cases': 0,
                'fresh_percentage': 0,
                'reloan_cases': 0,
                'reloan_percentage': 0,
                'fresh_sanction_amount': 0,
                'reloan_sanction_amount': 0,
                'fresh_disbursed_amount': 0,
                'reloan_disbursed_amount': 0,
                'fresh_repayment_amount': 0,
                'reloan_repayment_amount': 0,
                'fresh_collected_amount': 0,
                'reloan_collected_amount': 0,
                'fresh_pending_amount': 0,
                'reloan_pending_amount': 0,
                'principal_outstanding': 0,
                'fresh_principal_outstanding': 0,
                'reloan_principal_outstanding': 0,
                'sanction_amount': 0,
                'disbursed_amount': 0,
                'repayment_amount': 0,
                'earning': 0,
                'penalty': 0,
                'collected_amount': 0,
                'pending_collection': 0,
                'collection_rate': 0
            })
        
        # Calculate KPIs
        total_applications = len(records)
        
        # Calculate fresh and reloan cases
        fresh_records = [record for record in records if record.get('reloan_status') == 'Freash']
        reloan_records = [record for record in records if record.get('reloan_status') == 'Reloan']
        
        fresh_cases = len(fresh_records)
        reloan_cases = len(reloan_records)
        
        # Calculate percentages
        fresh_percentage = (fresh_cases / total_applications * 100) if total_applications > 0 else 0
        reloan_percentage = (reloan_cases / total_applications * 100) if total_applications > 0 else 0
        
        # Calculate fresh and reloan amounts
        fresh_sanction_amount = sum(Decimal(str(record.get('loan_amount', 0))) for record in fresh_records)
        fresh_disbursed_amount = sum(Decimal(str(record.get('net_disbursal', 0))) for record in fresh_records)
        fresh_repayment_amount = sum(Decimal(str(record.get('repayment_amount', 0))) for record in fresh_records)
        fresh_collected_amount = sum(Decimal(str(record.get('total_received', 0))) for record in fresh_records)
        
        reloan_sanction_amount = sum(Decimal(str(record.get('loan_amount', 0))) for record in reloan_records)
        reloan_disbursed_amount = sum(Decimal(str(record.get('net_disbursal', 0))) for record in reloan_records)
        reloan_repayment_amount = sum(Decimal(str(record.get('repayment_amount', 0))) for record in reloan_records)
        reloan_collected_amount = sum(Decimal(str(record.get('total_received', 0))) for record in reloan_records)
        
        # Calculate fresh and reloan pending amounts
        fresh_pending_amount = fresh_repayment_amount - fresh_collected_amount
        reloan_pending_amount = reloan_repayment_amount - reloan_collected_amount
        
        # Calculate total amounts
        sanction_amount = sum(Decimal(str(record.get('loan_amount', 0))) for record in records)
        disbursed_amount = sum(Decimal(str(record.get('net_disbursal', 0))) for record in records)
        repayment_amount = sum(Decimal(str(record.get('repayment_amount', 0))) for record in records)
        processing_fee = sum(Decimal(str(record.get('processing_fee', 0))) for record in records)
        interest_amount = sum(Decimal(str(record.get('interest_amount', 0))) for record in records)
        total_received = sum(Decimal(str(record.get('total_received', 0))) for record in records)
        
        # Calculate principal outstanding (SUM(net_disbursal) - SUM(total_received) WHERE closed_status = 'Not Closed')
        not_closed_records = [r for r in records if r.get('closed_status') == 'Not Closed']
        not_closed_fresh_records = [r for r in fresh_records if r.get('closed_status') == 'Not Closed']
        not_closed_reloan_records = [r for r in reloan_records if r.get('closed_status') == 'Not Closed']
        
        principal_outstanding_amount = sum(Decimal(str(r.get('net_disbursal', 0))) for r in not_closed_records) - sum(Decimal(str(r.get('total_received', 0))) for r in not_closed_records)
        fresh_principal_outstanding = sum(Decimal(str(r.get('net_disbursal', 0))) for r in not_closed_fresh_records) - sum(Decimal(str(r.get('total_received', 0))) for r in not_closed_fresh_records)
        reloan_principal_outstanding = sum(Decimal(str(r.get('net_disbursal', 0))) for r in not_closed_reloan_records) - sum(Decimal(str(r.get('total_received', 0))) for r in not_closed_reloan_records)
        
        earning = processing_fee + interest_amount
        penalty = Decimal('0')  # Assuming no penalty data in this API
        collected_amount = total_received
        pending_collection = repayment_amount - collected_amount
        collection_rate = round((collected_amount / repayment_amount * 100), 2) if repayment_amount > 0 else 0
        
        # Extract filter options from filtered records (use actual city names, not normalized)
        unique_states = sorted(list(set(record.get('state', '') for record in records if record.get('state'))))
        unique_cities = sorted(list(set(record.get('city', '').strip() for record in records if record.get('city', '').strip())))
        all_closed_statuses = list(set(record.get('closed_status', '') for record in records if record.get('closed_status')))
        unique_closed_statuses = [status for status in all_closed_statuses if status not in ['Active', 'Closed']]
        
        # Get unique DPD buckets and normalize them from filtered records
        all_dpd_buckets = list(set(record.get('dpd_bucket', '') for record in records if record.get('dpd_bucket')))
        normalized_dpd_buckets = [normalize_dpd_bucket(bucket) for bucket in all_dpd_buckets if bucket]
        bucket_order = ['0 days DPD', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 91-120', 'DPD 121-150', 'DPD 151-180', 'DPD 181-365', 'DPD 365+', 'No DPD']
        unique_dpd_buckets = [bucket for bucket in bucket_order if bucket in normalized_dpd_buckets]
        
        return JsonResponse({
            'total_applications': total_applications,
            'fresh_cases': fresh_cases,
            'fresh_percentage': float(fresh_percentage),
            'reloan_cases': reloan_cases,
            'reloan_percentage': float(reloan_percentage),
            'fresh_sanction_amount': float(fresh_sanction_amount),
            'reloan_sanction_amount': float(reloan_sanction_amount),
            'fresh_disbursed_amount': float(fresh_disbursed_amount),
            'reloan_disbursed_amount': float(reloan_disbursed_amount),
            'fresh_repayment_amount': float(fresh_repayment_amount),
            'reloan_repayment_amount': float(reloan_repayment_amount),
            'fresh_collected_amount': float(fresh_collected_amount),
            'reloan_collected_amount': float(reloan_collected_amount),
            'fresh_pending_amount': float(fresh_pending_amount),
            'reloan_pending_amount': float(reloan_pending_amount),
            'principal_outstanding': float(principal_outstanding_amount),
            'fresh_principal_outstanding': float(fresh_principal_outstanding),
            'reloan_principal_outstanding': float(reloan_principal_outstanding),
            'sanction_amount': float(sanction_amount),
            'disbursed_amount': float(disbursed_amount),
            'repayment_amount': float(repayment_amount),
            'earning': float(earning),
            'penalty': float(penalty),
            'collected_amount': float(collected_amount),
            'pending_collection': float(pending_collection),
            'collection_rate': float(collection_rate),
            'filter_options': {
                'states': unique_states,
                'cities': unique_cities,
                'closing_statuses': unique_closed_statuses,
                'dpd_buckets': unique_dpd_buckets
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@no_cache_api
def api_fraud_dpd_buckets(request):
    """API endpoint for fraud summary DPD bucket data from Collection WITHOUT Fraud API"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'buckets': []})
        
        # Store the selected DPD bucket for highlighting
        selected_dpd = request.GET.get('dpd')
        
        # Group by DPD bucket
        bucket_data = {}
        for record in filtered_records:
            dpd_bucket = record.get('dpd_bucket', 'Unknown')
            if dpd_bucket not in bucket_data:
                bucket_data[dpd_bucket] = {
                    'bucket': dpd_bucket,
                    'count': 0,
                    'total_disbursal': Decimal('0'),
                    'total_due': Decimal('0')
                }
            
            bucket_data[dpd_bucket]['count'] += 1
            bucket_data[dpd_bucket]['total_disbursal'] += Decimal(str(record.get('net_disbursal', 0)))
            bucket_data[dpd_bucket]['total_due'] += Decimal(str(record.get('repayment_amount', 0)))
        
        # Convert to list and format
        buckets = []
        for bucket_info in bucket_data.values():
            buckets.append({
                'bucket': bucket_info['bucket'],
                'count': bucket_info['count'],
                'total_disbursal': float(bucket_info['total_disbursal']),
                'total_due': float(bucket_info['total_due'])
            })
        
        # Sort by bucket name
        buckets.sort(key=lambda x: x['bucket'])
        
        return JsonResponse({'buckets': buckets})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_fraud_state_repayment(request):
    """API endpoint for fraud summary state-wise repayment data"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        records = apply_fraud_filters(records, request)
        
        if not records:
            return JsonResponse({'states': []})
        
        # Group by state
        state_data = {}
        for record in records:
            state = record.get('state', 'Unknown')
            if state not in state_data:
                state_data[state] = {
                    'state': state,
                    'repayment_amount': Decimal('0'),
                    'collected_amount': Decimal('0')
                }
            
            state_data[state]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
            state_data[state]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
        
        # Convert to list and format
        states = []
        for state_info in state_data.values():
            repayment_amount = float(state_info['repayment_amount'])
            collected_amount = float(state_info['collected_amount'])
            states.append({
                'state': state_info['state'],
                'repayment_amount': repayment_amount,
                'collected_amount': collected_amount,
                'collection_rate': (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
            })
        
        # Sort by repayment amount descending
        states.sort(key=lambda x: x['repayment_amount'], reverse=True)
        
        return JsonResponse({'states': states})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@no_cache_api
def api_fraud_time_series(request):
    """API endpoint for fraud summary time series data"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        records = apply_fraud_filters(records, request)

        if not records:
            return JsonResponse({'data': []})
        
        # Group by repayment date
        date_data = {}
        for record in records:
            repayment_date_str = record.get('repayment_date')
            if repayment_date_str:
                try:
                    repayment_date = datetime.fromisoformat(repayment_date_str.replace('Z', '+00:00')).date()
                    date_key = repayment_date.strftime('%Y-%m-%d')
                    
                    if date_key not in date_data:
                        date_data[date_key] = {
                            'date': date_key,
                            'repayment_amount': Decimal('0'),
                            'collected_amount': Decimal('0')
                        }
                    
                    date_data[date_key]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
                    date_data[date_key]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
                except:
                    continue
        
        # Convert to list and format
        time_series_data = []
        for date_info in date_data.values():
            repayment_amount = float(date_info['repayment_amount'])
            collected_amount = float(date_info['collected_amount'])
            time_series_data.append({
                'date': date_info['date'],
                'repayment_amount': repayment_amount,
                'collected_amount': collected_amount,
                'collection_rate': (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
            })
        
        # Sort by date
        time_series_data.sort(key=lambda x: x['date'])
        
        return JsonResponse({'data': time_series_data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_fraud_city_collected(request):
    """API endpoint for fraud summary top 10 cities by collection percentage"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        records = apply_fraud_filters(records, request)

        if not records:
            return JsonResponse({'cities': []})
        
        # Group by city and calculate collection metrics
        city_data = {}
        for record in records:
            city = record.get('city', 'Unknown')
            normalized_city = normalize_city_name(city)
            
            if normalized_city not in city_data:
                city_data[normalized_city] = {
                    'city': normalized_city,
                    'collected_amount': Decimal('0'),
                    'repayment_amount': Decimal('0'),
                    'total_applications': 0
                }
            
            city_data[normalized_city]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
            city_data[normalized_city]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
            city_data[normalized_city]['total_applications'] += 1
        
        # Convert to list and calculate collection percentage
        cities = []
        for city_info in city_data.values():
            # Only include cities with minimum 20 loans
            if city_info['total_applications'] >= 20:
                collection_percentage = 0
                if city_info['repayment_amount'] > 0:
                    collection_percentage = float((city_info['collected_amount'] / city_info['repayment_amount']) * 100)
                
                cities.append({
                    'city': city_info['city'],
                    'collected_amount': float(city_info['collected_amount']),
                    'repayment_amount': float(city_info['repayment_amount']),
                    'collection_percentage': collection_percentage,
                    'total_applications': city_info['total_applications']
                })
        
        # Sort by collection percentage descending and take top 10
        cities.sort(key=lambda x: x['collection_percentage'], reverse=True)
        cities = cities[:10]
        
        return JsonResponse({'cities': cities})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_fraud_city_uncollected(request):
    """API endpoint for fraud summary top 10 cities by collection percentage (worst performers)"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        records = apply_fraud_filters(records, request)

        if not records:
            return JsonResponse({'cities': []})
        
        # Group by city and calculate collection metrics
        city_data = {}
        for record in records:
            city = record.get('city', 'Unknown')
            normalized_city = normalize_city_name(city)
            
            if normalized_city not in city_data:
                city_data[normalized_city] = {
                    'city': normalized_city,
                    'collected_amount': Decimal('0'),
                    'repayment_amount': Decimal('0'),
                    'total_applications': 0
                }
            
            city_data[normalized_city]['collected_amount'] += Decimal(str(record.get('total_received', 0)))
            city_data[normalized_city]['repayment_amount'] += Decimal(str(record.get('repayment_amount', 0)))
            city_data[normalized_city]['total_applications'] += 1
        
        # Convert to list and calculate collection percentage
        cities = []
        for city_info in city_data.values():
            # Only include cities with minimum 20 loans and repayment amounts > 0 to avoid division by zero
            if (city_info['total_applications'] >= 20 and 
                city_info['repayment_amount'] > 0):
                collection_percentage = float((city_info['collected_amount'] / city_info['repayment_amount']) * 100)
                uncollected_amount = float(city_info['repayment_amount'] - city_info['collected_amount'])
                
                cities.append({
                    'city': city_info['city'],
                    'collected_amount': float(city_info['collected_amount']),
                    'repayment_amount': float(city_info['repayment_amount']),
                    'uncollected_amount': uncollected_amount,
                    'collection_percentage': collection_percentage,
                    'total_applications': city_info['total_applications']
                })
        
        # Sort by collection percentage ascending (worst performers first) and take top 10
        cities.sort(key=lambda x: x['collection_percentage'], reverse=False)
        cities = cities[:10]
        
        return JsonResponse({'cities': cities})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@no_cache_api
def api_credit_person_wise(request):
    """Proxy endpoint for credit person wise data."""
    start_date = request.GET.get('startDate') or request.GET.get('start_date')
    end_date = request.GET.get('endDate') or request.GET.get('end_date')

    if not start_date or not end_date:
        return JsonResponse(
            {'error': 'start_date and end_date query parameters are required.'},
            status=400
        )

    try:
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        response = requests.get(CREDIT_PERSON_API_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        return JsonResponse({
            'success': payload.get('success', True),
            'message': payload.get('message', ''),
            'data': payload.get('data', [])
        })
    except requests.RequestException as exc:
        logger.error('Error fetching credit person wise data: %s', exc, exc_info=True)
        return JsonResponse(
            {'error': 'Failed to fetch credit person data from external service.'},
            status=502
        )
    except ValueError as exc:
        logger.error('Invalid JSON from credit person API: %s', exc, exc_info=True)
        return JsonResponse(
            {'error': 'Received invalid response from external service.'},
            status=502
        )


@no_cache_api
def api_not_closed_percent(request):
    """Proxy endpoint for not closed percentage data used in Loan Count Wise tab."""
    start_date = request.GET.get('startDate') or request.GET.get('start_date')
    end_date = request.GET.get('endDate') or request.GET.get('end_date')

    if not start_date or not end_date:
        return JsonResponse(
            {'error': 'start_date and end_date query parameters are required.'},
            status=400
        )

    try:
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        response = requests.get(NOT_CLOSED_PERCENT_API_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        return JsonResponse({
            'success': payload.get('success', True),
            'message': payload.get('message', ''),
            'data': payload.get('data', [])
        })
    except requests.RequestException as exc:
        logger.error('Error fetching not closed percent data: %s', exc, exc_info=True)
        return JsonResponse(
            {'error': 'Failed to fetch not closed percent data from external service.'},
            status=502
        )
    except ValueError as exc:
        logger.error('Invalid JSON from not closed percent API: %s', exc, exc_info=True)
        return JsonResponse(
            {'error': 'Received invalid response from external service.'},
            status=502
        )


@no_cache_api
def api_fraud_pending_cases_by_amount(request):
    """API endpoint for pending cases grouped by amount bucket in Collection Without Fraud tab"""
    try:
        # Fetch data from the without-fraud API
        response = requests.get(settings.EXTERNAL_API_URL_WITHOUT_FRAUD, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract the data array
        records = data.get('cwpr', [])
        
        # Apply filters if provided
        filtered_records = apply_fraud_filters(records, request)
        
        if not filtered_records:
            return JsonResponse({'buckets': []})
        
        # Define amount buckets (in thousands)
        def get_amount_bucket(amount):
            """Categorize amount into bucket"""
            amount_float = float(amount)
            if amount_float < 5:
                return '<5k'  # Include amounts below 5k
            elif 5 <= amount_float < 10:
                return '5-10k'
            elif 10 <= amount_float < 20:
                return '10-20k'
            elif 20 <= amount_float < 30:
                return '20-30k'  # Include 20-30k range
            elif 30 <= amount_float < 40:  # 30-30k likely meant 30-40k
                return '30-40k'
            elif 40 <= amount_float < 50:
                return '40-50k'
            elif 50 <= amount_float < 60:
                return '50-60k'
            elif 60 <= amount_float < 70:
                return '60-70k'
            elif 70 <= amount_float < 80:
                return '70-80k'
            elif 80 <= amount_float < 90:
                return '80-90k'
            elif amount_float >= 90:
                return '90+k'
            else:
                return None
        
        # Group pending cases by amount bucket
        # A case is pending if repayment_amount > total_received
        bucket_data = {}
        bucket_order = ['<5k', '5-10k', '10-20k', '20-30k', '30-40k', '40-50k', '50-60k', '60-70k', '70-80k', '80-90k', '90+k']
        
        # Initialize all buckets
        for bucket in bucket_order:
            bucket_data[bucket] = {
                'bucket': bucket,
                'count': 0,  # Pending cases
                'total_count': 0,  # All cases in this bucket
                'total_pending_amount': Decimal('0'),
                'total_repayment_amount': Decimal('0'),
                'total_collected_amount': Decimal('0'),
                'pending_count': 0  # Alias for clarity when calculating percentages
            }
        
        # Calculate overall totals across all buckets
        overall_total_pending_amount = Decimal('0')
        overall_total_loans_count = 0
        
        # Process records
        for record in filtered_records:
            repayment_amount = safe_decimal_conversion(record.get('repayment_amount', 0))
            total_received = safe_decimal_conversion(record.get('total_received', 0))
            closed_status = record.get('closed_status', '')
            
            # Use repayment_amount to determine bucket (in thousands)
            repayment_for_bucket = max(repayment_amount, Decimal('0'))
            repayment_in_k = float(repayment_for_bucket) / 1000
            bucket = get_amount_bucket(repayment_in_k)
            
            if not bucket or bucket not in bucket_data:
                continue
            
            # Update totals for all loans in this bucket
            overall_total_loans_count += 1
            bucket_data[bucket]['total_count'] += 1
            bucket_data[bucket]['total_repayment_amount'] += repayment_amount
            bucket_data[bucket]['total_collected_amount'] += total_received
            
            # Calculate pending amount (only relevant for not closed cases)
            pending_amount = repayment_amount - total_received
            if pending_amount < 0:
                pending_amount = Decimal('0')
            
            if closed_status == 'Not Closed':
                bucket_data[bucket]['count'] += 1  # Pending cases (kept for backward compatibility)
                bucket_data[bucket]['pending_count'] += 1
                bucket_data[bucket]['total_pending_amount'] += pending_amount
                overall_total_pending_amount += pending_amount
        
        # Convert to list and format
        result = []
        for bucket in bucket_order:
            if bucket in bucket_data:
                bucket_info = bucket_data[bucket]
                total_count = bucket_info['total_count']
                pending_count = bucket_info['pending_count']
                total_pending_amount = bucket_info['total_pending_amount']
                total_repayment_amount = bucket_info['total_repayment_amount']
                
                percentage_of_total_loans_count = (
                    float(total_count / overall_total_loans_count * 100) if overall_total_loans_count > 0 else 0.0
                )
                pending_percentage_count = (
                    float(pending_count / total_count * 100) if total_count > 0 else 0.0
                )
                pending_percentage_amount = (
                    float(total_pending_amount / total_repayment_amount * 100)
                    if total_repayment_amount > 0 else 0.0
                )
                
                result.append({
                    'bucket': bucket_info['bucket'],
                    'count': bucket_info['count'],  # Pending cases
                    'pending_count': pending_count,
                    'total_count': total_count,
                    'total_pending_amount': float(total_pending_amount),
                    'total_repayment_amount': float(total_repayment_amount),
                    'total_collected_amount': float(bucket_info['total_collected_amount']),
                    'pending_percentage_count': pending_percentage_count,
                    'pending_percentage_amount': pending_percentage_amount
                })
        
        return JsonResponse({
            'buckets': result,
            'overall_total_pending_amount': float(overall_total_pending_amount)
        })
        
    except Exception as e:
        logger.error(f"Error fetching pending cases by amount: {e}")
        return JsonResponse({'error': str(e)}, status=500)






# Loan Count Wise API endpoint
@require_http_methods(["GET"])
def api_loan_count_wise(request):
    """API endpoint for Loan Count Wise data"""
    try:
        # Get date parameters from request
        start_date = request.GET.get('startDate', '')
        end_date = request.GET.get('endDate', '')
        
        # Validate date parameters
        if not start_date or not end_date:
            return JsonResponse({
                'error': 'Start date and end date are required',
                'count_wise': [],
                'amount_wise': []
            }, status=400)
        
        # Build API URL with date parameters
        loan_count_api_url = "https://backend.blinkrloan.com/insights/v1/dueLoanCountWise"
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        
        logger.info(f"Fetching loan count wise data with params: {params}")
        
        # Fetch data from the external API
        response = requests.get(loan_count_api_url, params=params, timeout=30)
        response.raise_for_status()
        api_data = response.json()
        
        logger.info(f"Received loan count wise data: {api_data}")
        
        # Extract count_wise and amount_wise data from the response
        count_wise = api_data.get('data', {}).get('count_wise', [])
        amount_wise = api_data.get('data', {}).get('amount_wise', [])
        
        return JsonResponse({
            'success': True,
            'message': api_data.get('message', 'Data fetched successfully'),
            'count_wise': count_wise,
            'amount_wise': amount_wise,
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching loan count wise data from external API: {e}")
        return JsonResponse({
            'error': 'Failed to fetch data from external API',
            'count_wise': [],
            'amount_wise': []
        }, status=500)
    except Exception as e:
        logger.error(f"Error in loan count wise API: {e}", exc_info=True)
        return JsonResponse({
            'error': 'Failed to fetch loan count wise data',
            'count_wise': [],
            'amount_wise': []
        }, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_disbursal_summary(request):
    """
    API endpoint to fetch disbursal summary data from external API
    Accepts startDate, endDate, state, city, reloan, and tenure query parameters
    """
    try:
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        
        if not start_date or not end_date:
            return JsonResponse({'error': 'startDate and endDate are required'}, status=400)
        
        # Validate date format
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Fetch data from external disbursal API
        disbursal_api_url = 'https://backend.blinkrloan.com/insights/v1/disbursal'
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        
        response = requests.get(disbursal_api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract result array from response
        disbursal_records = data.get('result', [])
        
        # Parse date range for filtering
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Filter records by disbursal_date to ensure date range is correct
        date_filtered_records = []
        for record in disbursal_records:
            disbursal_date_str = record.get('disbursal_date')
            if disbursal_date_str:
                parsed_date = parse_datetime_safely(disbursal_date_str)
                if parsed_date:
                    record_date = parsed_date
                    if isinstance(record_date, date) and start_date_obj <= record_date <= end_date_obj:
                        date_filtered_records.append(record)
        
        disbursal_records = date_filtered_records
        
        logger.info(f"Disbursal API returned {len(data.get('result', []))} records, after date filtering: {len(disbursal_records)} records for date range {start_date} to {end_date}")
        
        # Get unique states and cities from ALL records (for dropdown options)
        unique_states = sorted(set(r.get('state') for r in disbursal_records if r.get('state')))
        unique_cities_all = sorted(set(r.get('city') for r in disbursal_records if r.get('city')))
        
        # Apply filters
        state_filter = request.GET.get('state')
        city_filter = request.GET.get('city')
        reloan_filter = request.GET.get('reloan')
        tenure_filter = request.GET.get('tenure')
        
        filtered_records = disbursal_records.copy()
        
        # Filter by state
        if state_filter:
            filtered_records = [r for r in filtered_records if r.get('state') == state_filter]
            unique_cities_all = sorted(set(r.get('city') for r in filtered_records if r.get('city')))
        
        # Filter by city
        if city_filter:
            filtered_records = [r for r in filtered_records if r.get('city', '').strip() == city_filter.strip()]
        
        # Filter by reloan status
        if reloan_filter:
            if reloan_filter.lower() == 'true':
                filtered_records = [r for r in filtered_records if r.get('is_reloan_case', False) == True]
            elif reloan_filter.lower() == 'false':
                filtered_records = [r for r in filtered_records if r.get('is_reloan_case', False) == False]
        
        # Filter by tenure
        if tenure_filter:
            try:
                if '-' in tenure_filter:
                    min_tenure, max_tenure = map(int, tenure_filter.split('-'))
                    filtered_records = [r for r in filtered_records if min_tenure <= r.get('tenure', 0) <= max_tenure]
                else:
                    tenure_value = int(tenure_filter)
                    filtered_records = [r for r in filtered_records if r.get('tenure', 0) == tenure_value]
            except (ValueError, AttributeError):
                pass
        
        # Calculate summary statistics
        total_records = len(filtered_records)
        total_loan_amount = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in filtered_records)
        total_disbursal_amount = sum(safe_decimal_conversion(r.get('Disbursal_Amt', 0)) for r in filtered_records)
        total_repayment_amount = sum(safe_decimal_conversion(r.get('repayment_amount', 0)) for r in filtered_records)
        total_processing_fee = sum(safe_decimal_conversion(r.get('processing_fee', 0)) for r in filtered_records)
        total_interest_amount = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in filtered_records)
        
        # Count by status
        closed_count = sum(1 for r in filtered_records if r.get('is_lead_closed', False))
        open_count = total_records - closed_count
        reloan_count = sum(1 for r in filtered_records if r.get('is_reloan_case', False))
        fresh_count = total_records - reloan_count
        
        # Calculate Fresh and Reloan breakdowns
        fresh_records = [r for r in filtered_records if not r.get('is_reloan_case', False)]
        reloan_records = [r for r in filtered_records if r.get('is_reloan_case', False)]
        
        fresh_loan_amount = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in fresh_records)
        fresh_disbursal_amount = sum(safe_decimal_conversion(r.get('Disbursal_Amt', 0)) for r in fresh_records)
        fresh_repayment_amount = sum(safe_decimal_conversion(r.get('repayment_amount', 0)) for r in fresh_records)
        fresh_processing_fee = sum(safe_decimal_conversion(r.get('processing_fee', 0)) for r in fresh_records)
        fresh_interest_amount = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in fresh_records)
        
        reloan_loan_amount = sum(safe_decimal_conversion(r.get('loan_amount', 0)) for r in reloan_records)
        reloan_disbursal_amount = sum(safe_decimal_conversion(r.get('Disbursal_Amt', 0)) for r in reloan_records)
        reloan_repayment_amount = sum(safe_decimal_conversion(r.get('repayment_amount', 0)) for r in reloan_records)
        reloan_processing_fee = sum(safe_decimal_conversion(r.get('processing_fee', 0)) for r in reloan_records)
        reloan_interest_amount = sum(safe_decimal_conversion(r.get('interest_amount', 0)) for r in reloan_records)
        
        # Aggregate data by state for pie chart
        state_aggregated = {}
        for record in filtered_records:
            state = record.get('state', 'Unknown')
            if state not in state_aggregated:
                state_aggregated[state] = {
                    'count': 0,
                    'loan_amount': Decimal('0'),
                    'disbursal_amount': Decimal('0')
                }
            state_aggregated[state]['count'] += 1
            state_aggregated[state]['loan_amount'] += safe_decimal_conversion(record.get('loan_amount', 0))
            state_aggregated[state]['disbursal_amount'] += safe_decimal_conversion(record.get('Disbursal_Amt', 0))
        
        state_chart_data = []
        for state, data in sorted(state_aggregated.items(), key=lambda x: x[1]['loan_amount'], reverse=True):
            state_chart_data.append({
                'state': state,
                'count': data['count'],
                'loan_amount': float(data['loan_amount']),
                'disbursal_amount': float(data['disbursal_amount'])
            })
        
        # Aggregate data by city for pie chart
        city_aggregated = {}
        for record in filtered_records:
            city = record.get('city', 'Unknown')
            record_state = record.get('state', 'Unknown')
            
            if state_filter and record_state != state_filter:
                continue
                
            if city not in city_aggregated:
                city_aggregated[city] = {
                    'count': 0,
                    'loan_amount': Decimal('0'),
                    'disbursal_amount': Decimal('0'),
                    'state': record_state
                }
            city_aggregated[city]['count'] += 1
            city_aggregated[city]['loan_amount'] += safe_decimal_conversion(record.get('loan_amount', 0))
            city_aggregated[city]['disbursal_amount'] += safe_decimal_conversion(record.get('Disbursal_Amt', 0))
        
        city_chart_data = []
        sorted_cities = sorted(city_aggregated.items(), key=lambda x: x[1]['loan_amount'], reverse=True)[:15]
        for city, data in sorted_cities:
            city_chart_data.append({
                'city': city,
                'state': data['state'],
                'count': data['count'],
                'loan_amount': float(data['loan_amount']),
                'disbursal_amount': float(data['disbursal_amount'])
            })
        
        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        per_page = 10
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
        if page > total_pages and total_pages > 0:
            page = total_pages
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_records = filtered_records[start_idx:end_idx]
        
        return JsonResponse({
            'records': paginated_records,
            'summary': {
                'total_records': total_records,
                'total_loan_amount': float(total_loan_amount),
                'total_disbursal_amount': float(total_disbursal_amount),
                'total_repayment_amount': float(total_repayment_amount),
                'total_processing_fee': float(total_processing_fee),
                'total_interest_amount': float(total_interest_amount),
                'closed_count': closed_count,
                'open_count': open_count,
                'reloan_count': reloan_count,
                'fresh_count': fresh_count,
                'fresh_loan_amount': float(fresh_loan_amount),
                'fresh_disbursal_amount': float(fresh_disbursal_amount),
                'fresh_repayment_amount': float(fresh_repayment_amount),
                'fresh_processing_fee': float(fresh_processing_fee),
                'fresh_interest_amount': float(fresh_interest_amount),
                'reloan_loan_amount': float(reloan_loan_amount),
                'reloan_disbursal_amount': float(reloan_disbursal_amount),
                'reloan_repayment_amount': float(reloan_repayment_amount),
                'reloan_processing_fee': float(reloan_processing_fee),
                'reloan_interest_amount': float(reloan_interest_amount)
            },
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_records': total_records,
                'per_page': per_page,
                'has_next': page < total_pages,
                'has_previous': page > 1,
            },
            'filters': {
                'unique_states': unique_states,
                'unique_cities': unique_cities_all
            },
            'chart_data': {
                'state': state_chart_data,
                'city': city_chart_data
            },
            'start_date': start_date,
            'end_date': end_date
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching disbursal data from external API: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to fetch data from external API'}, status=500)
    except Exception as e:
        logger.error(f"Error processing disbursal summary: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to process data'}, status=500)


@require_http_methods(["GET", "POST"])
@csrf_exempt
@no_cache_api
def api_daily_performance_metrics(request):
    """API endpoint for Daily Performance Metrics data"""
    try:
        import calendar
        
        # Handle POST request to update monthly target
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                target_amount = data.get('monthly_target')
                if target_amount:
                    target_amount = str(target_amount).replace(',', '')  # Remove commas
                    monthly_target = MonthlyTarget.set_current_month_target(target_amount)
                    return JsonResponse({
                        'success': True,
                        'message': 'Monthly target updated successfully',
                        'target_amount': float(monthly_target.target_amount)
                    })
            except (ValueError, InvalidOperation, json.JSONDecodeError) as e:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid target amount'
                }, status=400)
        
        # Fetch data from the external API
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])
        
        # Apply filters
        filtered_records = apply_fraud_filters(records, request)
        
        # Get current date and calculate month info
        today = date.today()
        current_month = today.month
        current_year = today.year
        days_in_month = calendar.monthrange(current_year, current_month)[1]
        
        # Calculate date ranges
        month_start = date(current_year, current_month, 1)
        month_end = date(current_year, current_month, days_in_month)
        
        # Filter records for current month
        current_month_records = []
        for record in filtered_records:
            disbursal_date = parse_datetime_safely(record.get('disbursal_date'))
            if disbursal_date and month_start <= disbursal_date <= month_end:
                current_month_records.append(record)
        
        # 1. SANCTION PERFORMANCE
        # Monthly target (from database, with fallback to request parameter)
        monthly_target_param = request.GET.get('monthly_target')
        if monthly_target_param:
            try:
                # If provided in request, save to database and use it
                target_amount = str(monthly_target_param).replace(',', '')  # Remove commas
                target_obj = MonthlyTarget.set_current_month_target(target_amount)
                monthly_target = target_obj.target_amount
            except (ValueError, InvalidOperation):
                # Fallback to database value
                db_target = MonthlyTarget.get_current_month_target()
                monthly_target = Decimal(str(db_target)) if db_target and db_target > 0 else Decimal('80000000')
        else:
            # Get from database, with default fallback
            db_target = MonthlyTarget.get_current_month_target()
            monthly_target = Decimal(str(db_target)) if db_target and db_target > 0 else Decimal('80000000')  # ₹8,00,00,000 default
        
        # Today's disbursement
        today_disbursement = Decimal('0')
        for record in current_month_records:
            disbursal_date = parse_datetime_safely(record.get('disbursal_date'))
            if disbursal_date == today:
                today_disbursement += safe_decimal_conversion(record.get('loan_amount', 0))
        
        # Total achieved till today
        total_achieved = Decimal('0')
        for record in current_month_records:
            disbursal_date = parse_datetime_safely(record.get('disbursal_date'))
            if disbursal_date and disbursal_date <= today:
                total_achieved += safe_decimal_conversion(record.get('loan_amount', 0))
        
        # Calculate metrics
        achievement_percentage = float((total_achieved / monthly_target) * 100) if monthly_target > 0 else 0
        yet_to_achieve = monthly_target - total_achieved
        yet_to_achieve_percentage = float((yet_to_achieve / monthly_target) * 100) if monthly_target > 0 else 0
        
        days_completed = today.day
        remaining_days = days_in_month - days_completed
        
        # Current daily performance (average so far)
        current_daily_performance = total_achieved / days_completed if days_completed > 0 else Decimal('0')
        
        # Required daily performance to meet target
        required_daily_performance = yet_to_achieve / remaining_days if remaining_days > 0 else Decimal('0')
        
        sanction_performance = {
            'monthly_target': float(monthly_target),
            'today_disbursement': float(today_disbursement),
            'total_achieved': float(total_achieved),
            'achievement_percentage': round(achievement_percentage, 2),
            'yet_to_achieve': float(yet_to_achieve),
            'yet_to_achieve_percentage': round(yet_to_achieve_percentage, 2),
            'days_completed': days_completed,
            'remaining_days': remaining_days,
            'current_daily_performance': float(current_daily_performance),
            'required_daily_performance': float(required_daily_performance)
        }
        
        # 2. COLLECTION EFFICIENCY
        # Current month collection efficiency - filter by repayment_date in current month (till today's date)
        # Formula: (Total Collected / Total Repayment) × 100
        # Only include loans whose repayment_date is in the current month up to today
        total_repayment_amount = Decimal('0')
        total_collected_amount = Decimal('0')
        
        # Filter records for current month: loans whose repayment_date is in current month (up to today)
        current_month_collection_records = []
        for record in filtered_records:
            repayment_date = parse_datetime_safely(record.get('repayment_date'))
            if repayment_date and month_start <= repayment_date <= today:
                current_month_collection_records.append(record)
        
        # Calculate collection efficiency for current month (till date)
        for record in current_month_collection_records:
            total_repayment_amount += safe_decimal_conversion(record.get('repayment_amount', 0))
            total_collected_amount += safe_decimal_conversion(record.get('total_received', 0))
        
        current_collection_efficiency = float((total_collected_amount / total_repayment_amount) * 100) if total_repayment_amount > 0 else 0
        
        # Benchmark collection efficiency (configurable)
        benchmark_efficiency = 85  # 85% benchmark
        
        collection_efficiency = {
            'current_month_efficiency': round(current_collection_efficiency, 2),
            'benchmark_efficiency': benchmark_efficiency
        }
        
        # 3. HISTORICAL COLLECTION EFFICIENCY
        # Calculate for June to November (6 months) from collection with fraud API data
        # For each month, calculate efficiency for loans whose repayment_date was IN that specific month
        # Formula: (Total Collected in that month / Total Repayment Amount in that month) × 100
        historical_data = []
        
        # Define the months to show: June (6) to November (11) of current year
        months_to_show = [11, 10, 9, 8, 7, 6]  # November to June (descending order - most recent first)
        
        for hist_month in months_to_show:
            hist_year = current_year
            
            hist_month_start = date(hist_year, hist_month, 1)
            hist_days_in_month = calendar.monthrange(hist_year, hist_month)[1]
            hist_month_end = date(hist_year, hist_month, hist_days_in_month)
            
            # Filter records for historical month: loans whose repayment_date was IN this specific month
            hist_records = []
            for record in filtered_records:
                repayment_date = parse_datetime_safely(record.get('repayment_date'))
                if repayment_date and hist_month_start <= repayment_date <= hist_month_end:
                    hist_records.append(record)
            
            # Calculate collection efficiency for historical month
            # Sum of total_received (amount collected) for that month
            # Sum of repayment_amount (repayment amount) for that month
            hist_repayment = Decimal('0')
            hist_collected = Decimal('0')
            
            for record in hist_records:
                hist_repayment += safe_decimal_conversion(record.get('repayment_amount', 0))
                hist_collected += safe_decimal_conversion(record.get('total_received', 0))
            
            hist_efficiency = float((hist_collected / hist_repayment) * 100) if hist_repayment > 0 else 0
            
            # Set benchmark
            hist_benchmark = 85
            
            month_name = calendar.month_name[hist_month]
            historical_data.append({
                'month': f"{month_name}, {hist_year}",
                'actual': round(hist_efficiency, 2),
                'benchmark': hist_benchmark
            })
        
        return JsonResponse({
            'sanction_performance': sanction_performance,
            'collection_efficiency': collection_efficiency,
            'historical_collection_efficiency': historical_data,
            'report_date': today.strftime('%d-%b-%y'),
            'position_as_on': (today - timedelta(days=1)).strftime('%d-%b-%y')
        })
        
    except Exception as e:
        logger.error(f"Error fetching daily performance metrics: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to fetch data'}, status=500)


@require_http_methods(["GET"])
@no_cache_api
def api_aum_report(request):
    """API endpoint for AUM Report data"""
    try:
        # Check query parameters to determine which API endpoint to use
        till_prev_month = request.GET.get('till_prev_month', '').lower() == 'true'
        till_prev_date = request.GET.get('till_prev_date', '').lower() == 'true'
        
        # Determine which API endpoint to call
        if till_prev_month:
            api_url = 'https://backend.blinkrloan.com/insights/v1/aum-report-till-previous-month'
        elif till_prev_date:
            api_url = 'https://backend.blinkrloan.com/insights/v1/aum-report-till-previous-day'
        else:
            api_url = 'https://backend.blinkrloan.com/insights/v1/aum-report'
        
        logger.info(f"Fetching AUM report data from: {api_url}")
        
        # Fetch data from the external API
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        api_response = response.json()
        
        # The external API returns data in a 'data' field
        all_data = api_response.get('data', [])
        
        # Separate monthly data (is_total=False) from total data (is_total=True)
        monthly_data = [item for item in all_data if not item.get('is_total', False)]
        total_data_items = [item for item in all_data if item.get('is_total', False)]
        total_data = total_data_items[0] if total_data_items else None
        
        # Log for debugging
        logger.info(f"AUM Report - Monthly data count: {len(monthly_data)}, Total data: {total_data is not None}")
        
        return JsonResponse({
            'monthly_data': monthly_data,
            'total_data': total_data
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching AUM report data from external API: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to fetch data from external API'}, status=500)
    except Exception as e:
        logger.error(f"Error processing AUM report: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to process data'}, status=500)