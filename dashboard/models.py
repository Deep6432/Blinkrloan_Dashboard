from django.db import models
from django.core.validators import MinValueValidator


class MonthlyTarget(models.Model):
    """Model to store monthly sanction target"""
    
    month = models.IntegerField()  # 1-12 for Jan-Dec
    year = models.IntegerField()
    target_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['month', 'year']
        ordering = ['-year', '-month']
        verbose_name = 'Monthly Target'
        verbose_name_plural = 'Monthly Targets'

    def __str__(self):
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        return f"{month_names[self.month]} {self.year} - ₹{self.target_amount:,.2f}"

    @classmethod
    def get_current_month_target(cls):
        """Get target for current month"""
        from datetime import datetime
        now = datetime.now()
        try:
            target = cls.objects.get(month=now.month, year=now.year)
            return target.target_amount
        except cls.DoesNotExist:
            return 0

    @classmethod
    def set_current_month_target(cls, amount):
        """Set target for current month"""
        from datetime import datetime
        from decimal import Decimal
        
        now = datetime.now()
        target, created = cls.objects.get_or_create(
            month=now.month,
            year=now.year,
            defaults={'target_amount': Decimal(str(amount))}
        )
        if not created:
            target.target_amount = Decimal(str(amount))
            target.save()
        return target


class LoanRecord(models.Model):
    """Model to store loan portfolio data"""
    
    lead_no = models.CharField(max_length=50, unique=True)
    loan_no = models.CharField(max_length=50, unique=True)
    pan = models.CharField(max_length=20, blank=True, null=True)
    sanction_date = models.DateField()
    disbursal_date = models.DateField()
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    tenure = models.IntegerField(blank=True, null=True)
    repayment_date = models.DateField(blank=True, null=True)
    repayment_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    processing_fee = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    net_disbursal = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    interest_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    collection_active = models.BooleanField(default=False)
    fraud_status = models.CharField(max_length=20)
    reloan_status = models.CharField(max_length=20)
    total_received = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    last_received_date = models.DateField(blank=True, null=True)
    outstanding = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    overdue_days = models.IntegerField(validators=[MinValueValidator(0)])
    overdue_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    dpd_bucket = models.CharField(max_length=20)
    closed_status = models.CharField(max_length=20)
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-disbursal_date']
        verbose_name = 'Loan Record'
        verbose_name_plural = 'Loan Records'
        indexes = [
            models.Index(fields=['repayment_date']),
            models.Index(fields=['dpd_bucket']),
            models.Index(fields=['closed_status']),
            models.Index(fields=['state']),
            models.Index(fields=['city']),
            models.Index(fields=['repayment_date', 'dpd_bucket']),
            models.Index(fields=['repayment_date', 'closed_status']),
            models.Index(fields=['repayment_date', 'state']),
            models.Index(fields=['repayment_date', 'city']),
        ]

    def __str__(self):
        return f"{self.loan_no} - {self.state}"

    @property
    def collection_percentage(self):
        """Calculate collection percentage"""
        if self.loan_amount > 0:
            return (self.total_received / self.loan_amount) * 100
        return 0

    @property
    def pending_amount(self):
        """Calculate pending amount"""
        return self.loan_amount - self.total_received

    @property
    def is_overdue(self):
        """Check if loan is overdue"""
        return self.overdue_days > 0
