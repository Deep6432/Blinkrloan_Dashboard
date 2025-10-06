from django.contrib import admin
from .models import LoanRecord


@admin.register(LoanRecord)
class LoanRecordAdmin(admin.ModelAdmin):
    list_display = [
        'loan_no', 'lead_no', 'pan', 'state', 'city', 'loan_amount', 
        'total_received', 'outstanding', 'overdue_days', 'dpd_bucket', 
        'closed_status', 'fraud_status', 'collection_active'
    ]
    list_filter = [
        'state', 'city', 'dpd_bucket', 'closed_status', 
        'fraud_status', 'reloan_status', 'collection_active'
    ]
    search_fields = ['loan_no', 'lead_no', 'pan', 'state', 'city']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
    fieldsets = (
        ('Basic Information', {
            'fields': ('lead_no', 'loan_no', 'pan', 'state', 'city')
        }),
        ('Loan Details', {
            'fields': ('loan_amount', 'tenure', 'repayment_amount', 'processing_fee', 'net_disbursal', 'interest_amount')
        }),
        ('Dates', {
            'fields': ('sanction_date', 'disbursal_date', 'repayment_date', 'last_received_date')
        }),
        ('Status & Collection', {
            'fields': ('collection_active', 'fraud_status', 'reloan_status', 'closed_status', 'dpd_bucket')
        }),
        ('Financial Status', {
            'fields': ('total_received', 'outstanding', 'overdue_days', 'overdue_amount')
        }),
        ('System', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
