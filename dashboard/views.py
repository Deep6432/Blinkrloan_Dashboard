from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
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

from .models import LoanRecord
from .services import DataSyncService


def parse_datetime_safely(datetime_str):
    """Safely parse datetime string and return date object"""
    if not datetime_str:
        return None
    
    try:
        # Handle different datetime formats
        if isinstance(datetime_str, str):
            # Remove timezone info and parse
            clean_str = datetime_str.replace('Z', '').replace('+00:00', '')
            if 'T' in clean_str:
                return datetime.fromisoformat(clean_str.split('T')[0]).date()
            else:
                return datetime.strptime(clean_str.split(' ')[0], '%Y-%m-%d').date()
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
            'reloan_principal_outstanding': 0
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
    
    # Calculate principal outstanding (net_disbursal for records with no collections)
    principal_outstanding = sum(
        safe_decimal_conversion(record.get('net_disbursal')) 
        for record in records 
        if not record.get('last_received_date') and safe_decimal_conversion(record.get('total_received')) == 0
    )
    
    fresh_principal_outstanding = sum(
        safe_decimal_conversion(record.get('net_disbursal')) 
        for record in fresh_records 
        if not record.get('last_received_date') and safe_decimal_conversion(record.get('total_received')) == 0
    )
    
    reloan_principal_outstanding = sum(
        safe_decimal_conversion(record.get('net_disbursal')) 
        for record in reloan_records 
        if not record.get('last_received_date') and safe_decimal_conversion(record.get('total_received')) == 0
    )
    
    # Calculate percentages
    fresh_percentage = round((fresh_cases / total_applications) * 100, 2) if total_applications > 0 else 0
    reloan_percentage = round((reloan_cases / total_applications) * 100, 2) if total_applications > 0 else 0
    collection_rate = round((collected_amount / repayment_amount) * 100, 2) if repayment_amount > 0 else 0
    
    # Calculate collected and pending percentages of repayment
    collected_percentage = collection_rate  # Same as collection rate
    pending_percentage = round(100 - collection_rate, 2) if collection_rate > 0 else 0
    
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
        'reloan_principal_outstanding': float(reloan_principal_outstanding)
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

    # Percentages
    collected_percentage = (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
    pending_percentage = ((repayment_amount - collected_amount) / repayment_amount * 100) if repayment_amount > 0 else 0

    # Calculate fresh and reloan pending amounts
    fresh_pending_amount = (fresh_amounts['fresh_repayment'] or 0) - (fresh_amounts['fresh_collected'] or 0)
    reloan_pending_amount = (reloan_amounts['reloan_repayment'] or 0) - (reloan_amounts['reloan_collected'] or 0)
    
    # Calculate principal outstanding (net_disbursal for records with no collections)
    principal_outstanding_queryset = queryset.filter(
        last_received_date__isnull=True,
        total_received=0
    )
    principal_outstanding_amount = principal_outstanding_queryset.aggregate(
        total=Sum('net_disbursal')
    )['total'] or Decimal('0')
    
    # Calculate fresh and reloan principal outstanding amounts
    fresh_principal_outstanding = principal_outstanding_queryset.filter(reloan_status='Freash').aggregate(
        total=Sum('net_disbursal')
    )['total'] or Decimal('0')
    
    reloan_principal_outstanding = principal_outstanding_queryset.filter(reloan_status='Reloan').aggregate(
        total=Sum('net_disbursal')
    )['total'] or Decimal('0')

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
    
    # Get unique values for filters from external API data
    try:
        # Fetch data from external API to get filter options
        response = requests.get(settings.EXTERNAL_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get('pr', [])
        
        # Extract unique values from external API data
        unique_states = sorted(list(set(record.get('state', '') for record in records if record.get('state'))))
        unique_cities = sorted(list(set(record.get('city', '') for record in records if record.get('city'))))
        
        # Get unique closed statuses and filter out Active and Closed
        all_closed_statuses = list(set(record.get('closed_status', '') for record in records if record.get('closed_status')))
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
        
        raw_dpd_buckets = list(set(record.get('dpd_bucket', '') for record in records if record.get('dpd_bucket')))
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
    
    # Percentages
    collected_percentage = (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
    pending_percentage = ((repayment_amount - collected_amount) / repayment_amount * 100) if repayment_amount > 0 else 0
    
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
def api_dpd_buckets(request):
    """API endpoint for DPD bucket data"""
    queryset = LoanRecord.objects.all()
    
    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)
    
    if request.GET.get('closing_status'):
        queryset = queryset.filter(closed_status=request.GET.get('closing_status'))
    
    # Store the selected DPD bucket for highlighting
    selected_dpd = request.GET.get('dpd')
    
    if request.GET.get('state'):
        queryset = queryset.filter(state=request.GET.get('state'))
    
    if request.GET.get('city'):
        queryset = queryset.filter(city=request.GET.get('city'))
    
    # Define normalized DPD bucket mapping
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
    
    # Get all unique DPD buckets and normalize them
    all_dpd_buckets = LoanRecord.objects.values_list('dpd_bucket', flat=True).distinct()
    normalized_buckets = set()
    
    for bucket in all_dpd_buckets:
        normalized_bucket = dpd_bucket_mapping.get(bucket, bucket)
        normalized_buckets.add(normalized_bucket)
    
    # Group by DPD bucket with additional aggregations
    dpd_data = queryset.values('dpd_bucket').annotate(
        count=Count('id'),
        total_net_disbursal=Sum('net_disbursal'),
        total_repayment_amount=Sum('repayment_amount')
    ).order_by('dpd_bucket')
    
    # Create consolidated data by normalized bucket names
    consolidated_data = {}
    for item in dpd_data:
        normalized_bucket = dpd_bucket_mapping.get(item['dpd_bucket'], item['dpd_bucket'])
        if normalized_bucket not in consolidated_data:
            consolidated_data[normalized_bucket] = {
                'dpd_bucket': normalized_bucket,
                'count': 0,
                'total_net_disbursal': 0,
                'total_repayment_amount': 0
            }
        
        consolidated_data[normalized_bucket]['count'] += item['count']
        consolidated_data[normalized_bucket]['total_net_disbursal'] += float(item['total_net_disbursal'] or 0)
        consolidated_data[normalized_bucket]['total_repayment_amount'] += float(item['total_repayment_amount'] or 0)
    
    # Create final result with proper ordering
    bucket_order = ['0 days DPD', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 91-120', 'No DPD']
    result = []
    
    for bucket in bucket_order:
        if bucket in normalized_buckets:
            bucket_data = consolidated_data.get(bucket, {
                'dpd_bucket': bucket,
                'count': 0,
                'total_net_disbursal': 0,
                'total_repayment_amount': 0
            })
            bucket_data['is_selected'] = (bucket == selected_dpd)
            result.append(bucket_data)
    
    return JsonResponse({
        'data': result
    })


@require_http_methods(["GET"])
def api_state_repayment(request):
    """API endpoint for state-wise repayment data"""
    queryset = LoanRecord.objects.all()
    
    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)
    
    # Group by state
    state_data = queryset.values('state').annotate(
        repayment_amount=Sum('total_received')
    ).order_by('-repayment_amount')
    
    return JsonResponse({
        'data': list(state_data)
    })


@require_http_methods(["GET"])
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

        return JsonResponse({'data': kpi_data})
    except Exception as e:
        logger.error(f"Error fetching KPI data: {e}")
        return JsonResponse({'error': 'Failed to fetch data'}, status=500)

@require_http_methods(["GET"])
def api_city_collected(request):
    """API endpoint for top 10 cities by collection percentage"""
    queryset = LoanRecord.objects.all()

    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)

    if request.GET.get('closing_status'):
        queryset = queryset.filter(closed_status=request.GET.get('closing_status'))

    if request.GET.get('dpd'):
        queryset = queryset.filter(dpd_bucket=request.GET.get('dpd'))

    if request.GET.get('state'):
        queryset = queryset.filter(state=request.GET.get('state'))

    if request.GET.get('city'):
        queryset = queryset.filter(city=request.GET.get('city'))

    # Group by city and calculate collection metrics
    city_data = queryset.values('city').annotate(
        collected_amount=Sum('total_received'),
        repayment_amount=Sum('repayment_amount'),
        total_applications=Count('id')
    )

    # Group data by normalized city names
    normalized_city_data = {}
    for item in city_data:
        normalized_city = normalize_city_name(item['city'])
        
        if normalized_city not in normalized_city_data:
            normalized_city_data[normalized_city] = {
                'city': normalized_city,
                'collected_amount': 0,
                'repayment_amount': 0,
                'total_applications': 0
            }
        
        normalized_city_data[normalized_city]['collected_amount'] += item['collected_amount'] or 0
        normalized_city_data[normalized_city]['repayment_amount'] += item['repayment_amount'] or 0
        normalized_city_data[normalized_city]['total_applications'] += item['total_applications']

    result = []
    for city_info in normalized_city_data.values():
        # Only include cities with minimum 20 loans and repayment amounts > 0 to avoid division by zero
        if (city_info['total_applications'] >= 20 and 
            city_info['repayment_amount'] and 
            city_info['repayment_amount'] > 0):
            collection_percentage = (city_info['collected_amount'] / city_info['repayment_amount']) * 100

            result.append({
                'city': city_info['city'],
                'collected_amount': float(city_info['collected_amount']),
                'repayment_amount': float(city_info['repayment_amount']),
                'collection_percentage': float(collection_percentage),
                'total_applications': city_info['total_applications']
            })

    # Sort by collection percentage (highest first) and take top 10
    result.sort(key=lambda x: x['collection_percentage'], reverse=True)
    result = result[:10]

    return JsonResponse({
        'data': result
    })


@require_http_methods(["GET"])
def api_city_uncollected(request):
    """API endpoint for top 10 cities by collection percentage (worst performers)"""
    queryset = LoanRecord.objects.all()

    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)

    if request.GET.get('closing_status'):
        queryset = queryset.filter(closed_status=request.GET.get('closing_status'))

    if request.GET.get('dpd'):
        queryset = queryset.filter(dpd_bucket=request.GET.get('dpd'))

    if request.GET.get('state'):
        queryset = queryset.filter(state=request.GET.get('state'))

    if request.GET.get('city'):
        queryset = queryset.filter(city=request.GET.get('city'))

    # Group by city and calculate collection metrics
    city_data = queryset.values('city').annotate(
        collected_amount=Sum('total_received'),
        repayment_amount=Sum('repayment_amount'),
        total_applications=Count('id')
    )

    # Group data by normalized city names
    normalized_city_data = {}
    for item in city_data:
        normalized_city = normalize_city_name(item['city'])
        
        if normalized_city not in normalized_city_data:
            normalized_city_data[normalized_city] = {
                'city': normalized_city,
                'collected_amount': 0,
                'repayment_amount': 0,
                'total_applications': 0
            }
        
        normalized_city_data[normalized_city]['collected_amount'] += item['collected_amount'] or 0
        normalized_city_data[normalized_city]['repayment_amount'] += item['repayment_amount'] or 0
        normalized_city_data[normalized_city]['total_applications'] += item['total_applications']

    # Calculate collection percentage for all cities
    result = []
    for city_info in normalized_city_data.values():
        # Only include cities with minimum 20 loans and repayment amounts > 0 to avoid division by zero
        if (city_info['total_applications'] >= 20 and 
            city_info['repayment_amount'] and 
            city_info['repayment_amount'] > 0):
            uncollected_amount = city_info['repayment_amount'] - city_info['collected_amount']
            collection_percentage = (city_info['collected_amount'] / city_info['repayment_amount']) * 100

            result.append({
                'city': city_info['city'],
                'collected_amount': float(city_info['collected_amount']),
                'repayment_amount': float(city_info['repayment_amount']),
                'uncollected_amount': float(uncollected_amount),
                'collection_percentage': float(collection_percentage),
                'total_applications': city_info['total_applications']
            })

    # Sort by collection percentage (lowest first - worst performers) and take top 10
    result.sort(key=lambda x: x['collection_percentage'], reverse=False)
    result = result[:10]

    return JsonResponse({
        'data': result
    })


@require_http_methods(["GET"])
def api_time_series(request):
    """API endpoint for time series data"""
    queryset = LoanRecord.objects.all()
    
    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)
    
    # Group by repayment date
    time_data = queryset.values('repayment_date').annotate(
        repayment_amount=Sum('repayment_amount'),
        collected_amount=Sum('total_received')
    ).order_by('repayment_date')
    
    # Calculate collection percentage
    result = []
    for item in time_data:
        collection_percentage = 0
        if item['repayment_amount'] and item['repayment_amount'] > 0:
            collection_percentage = (item['collected_amount'] / item['repayment_amount']) * 100
        
        result.append({
            'date': item['repayment_date'].strftime('%Y-%m-%d') if item['repayment_date'] else '',
            'repayment_amount': float(item['repayment_amount'] or 0),
            'collected_amount': float(item['collected_amount'] or 0),
            'collection_percentage': float(collection_percentage)
        })
    
    return JsonResponse({
        'data': result
    })


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
def api_dpd_bucket_details(request):
    """API endpoint for detailed DPD bucket data"""
    from django.core.paginator import Paginator, EmptyPage
    from django.db import models
    
    dpd_bucket = request.GET.get('dpd_bucket')
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    sort_by = request.GET.get('sort_by', 'overdue_days')
    sort_order = request.GET.get('sort_order', 'desc')
    
    if not dpd_bucket:
        return JsonResponse({'error': 'DPD bucket is required'}, status=400)
    
    # Start with all records
    queryset = LoanRecord.objects.all()
    
    # Apply DPD bucket filter - handle normalized bucket names
    dpd_bucket_mapping = {
        '0 days DPD': ['0'],
        'DPD 1-30': ['0-30', 'DPD 1-30'],
        'DPD 31-60': ['31-60', 'DPD 31-60'],
        'DPD 61-90': ['61-90', 'DPD 61-90'],
        'DPD 91-120': ['DPD 91-120'],
        'No DPD': ['No DPD']
    }
    
    # Get the original bucket names for the normalized bucket
    original_buckets = dpd_bucket_mapping.get(dpd_bucket, [dpd_bucket])
    queryset = queryset.filter(dpd_bucket__in=original_buckets)
    
    # Apply date range filters based on date_type
    queryset = apply_date_filter(queryset, request)
    
    # Apply other filters (same as main dashboard)
    if request.GET.get('closing_status'):
        queryset = queryset.filter(closed_status=request.GET.get('closing_status'))
    
    if request.GET.get('dpd'):
        queryset = queryset.filter(dpd_bucket=request.GET.get('dpd'))
    
    if request.GET.get('state'):
        queryset = queryset.filter(state=request.GET.get('state'))
    
    if request.GET.get('city'):
        queryset = queryset.filter(city=request.GET.get('city'))
    
    # Apply search filter
    if search:
        queryset = queryset.filter(
            models.Q(loan_no__icontains=search) | 
            models.Q(pan__icontains=search)
        )
    
    # Apply sorting
    if sort_order == 'desc':
        sort_by = f'-{sort_by}'
    queryset = queryset.order_by(sort_by)
    
    # Calculate totals before pagination
    totals = queryset.aggregate(
        total_net_disbursal=Sum('net_disbursal'),
        total_repayment_amount=Sum('repayment_amount')
    )
    
    # Apply pagination
    paginator = Paginator(queryset, per_page)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)
    
    # Format the data
    records = []
    for record in page_obj:
        records.append({
            'loan_no': record.loan_no,
            'pan': record.pan.upper() if record.pan else '',
            'disbursal_date': record.disbursal_date.strftime('%d/%m/%Y') if record.disbursal_date else '—',
            'net_disbursal': float(record.net_disbursal or 0),
            'repayment_date': record.repayment_date.strftime('%d/%m/%Y') if record.repayment_date else '—',
            'repayment_amount': float(record.repayment_amount or 0),
            'overdue_days': record.overdue_days,
            'dpd_bucket': record.dpd_bucket,
        })
    
    return JsonResponse({
        'records': records,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_records': paginator.count,
            'per_page': per_page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
        'totals': {
            'total_net_disbursal': float(totals['total_net_disbursal'] or 0),
            'total_repayment_amount': float(totals['total_repayment_amount'] or 0),
        },
        'dpd_bucket': dpd_bucket,
        'search': search,
    })


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


# Helper function to apply date filters based on date_type
def apply_date_filter(queryset, request):
    """Apply date range filters based on date_type parameter"""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    date_type = request.GET.get('date_type', 'repayment_date')
    
    if date_from and date_to:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            
            # Filter based on the selected date type with proper date range
            if date_type == 'disbursal_date':
                queryset = queryset.filter(
                    disbursal_date__gte=date_from_obj,
                    disbursal_date__lt=date_to_obj + timedelta(days=1)
                )
            else:  # default to repayment_date
                queryset = queryset.filter(
                    repayment_date__gte=date_from_obj,
                    repayment_date__lt=date_to_obj + timedelta(days=1)
                )
        except ValueError:
            pass
    
    return queryset

# Helper function to apply filters to fraud records
def normalize_city_name(city_name):
    """Normalize city names - group all Delhi and Mumbai districts under their respective main cities"""
    if not city_name:
        return city_name
    
    city_name = str(city_name).strip()
    
    # Check if city contains Delhi (case insensitive)
    if 'delhi' in city_name.lower():
        return 'Delhi'
    
    # Check if city contains Mumbai (case insensitive)
    if 'mumbai' in city_name.lower():
        return 'Mumbai'
    
    return city_name

def apply_fraud_filters(records, request):
    """Apply filters to fraud records based on request parameters"""
    if request.GET.get('date_from') and request.GET.get('date_to'):
        try:
            date_from = datetime.strptime(request.GET.get('date_from'), '%Y-%m-%d').date()
            date_to = datetime.strptime(request.GET.get('date_to'), '%Y-%m-%d').date()
            date_type = request.GET.get('date_type', 'repayment_date')
            
            # Filter based on the selected date type with proper date casting
            if date_type == 'disbursal_date':
                filtered_records = []
                for r in records:
                    if r.get('disbursal_date'):
                        parsed_date = parse_datetime_safely(r['disbursal_date'])
                        if parsed_date and date_from <= parsed_date <= date_to:
                            filtered_records.append(r)
                records = filtered_records
            else:  # default to repayment_date
                filtered_records = []
                for r in records:
                    if r.get('repayment_date'):
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
    
    if request.GET.get('state'):
        records = [r for r in records if r.get('state') == request.GET.get('state')]
    
    if request.GET.get('city'):
        records = [r for r in records if r.get('city') == request.GET.get('city')]
    
    return records

# Fraud Summary API endpoints (using portfolio-collection-without-fraud API)
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
        
        # Calculate principal outstanding (records with no collections)
        principal_outstanding_records = [record for record in records 
                                       if record.get('last_received_date') is None and 
                                       Decimal(str(record.get('total_received', 0))) == 0]
        
        principal_outstanding_amount = sum(Decimal(str(record.get('net_disbursal', 0))) for record in principal_outstanding_records)
        fresh_principal_outstanding = sum(Decimal(str(record.get('net_disbursal', 0))) for record in principal_outstanding_records 
                                        if record.get('reloan_status') == 'Freash')
        reloan_principal_outstanding = sum(Decimal(str(record.get('net_disbursal', 0))) for record in principal_outstanding_records 
                                         if record.get('reloan_status') == 'Reloan')
        
        # Calculate total amounts
        sanction_amount = sum(Decimal(str(record.get('loan_amount', 0))) for record in records)
        disbursed_amount = sum(Decimal(str(record.get('net_disbursal', 0))) for record in records)
        repayment_amount = sum(Decimal(str(record.get('repayment_amount', 0))) for record in records)
        processing_fee = sum(Decimal(str(record.get('processing_fee', 0))) for record in records)
        interest_amount = sum(Decimal(str(record.get('interest_amount', 0))) for record in records)
        total_received = sum(Decimal(str(record.get('total_received', 0))) for record in records)
        
        earning = processing_fee + interest_amount
        penalty = Decimal('0')  # Assuming no penalty data in this API
        collected_amount = total_received
        pending_collection = repayment_amount - collected_amount
        collection_rate = (collected_amount / repayment_amount * 100) if repayment_amount > 0 else 0
        
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
            'collection_rate': float(collection_rate)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_fraud_dpd_buckets(request):
    """API endpoint for fraud summary DPD bucket data"""
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
            return JsonResponse({'buckets': []})
        
        # Group by DPD bucket
        bucket_data = {}
        for record in records:
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


@require_http_methods(["GET"])
def api_cities_by_state(request):
    """API endpoint to get cities for a specific state"""
    state = request.GET.get('state')
    if not state:
        return JsonResponse({'cities': []})
    
    try:
        # Get unique cities for the selected state
        cities = list(LoanRecord.objects.filter(state=state).values_list('city', flat=True).distinct().order_by('city'))
        return JsonResponse({'cities': cities})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
