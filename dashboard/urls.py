from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.login_view, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/kpi-data/', views.api_kpi_data, name='api_kpi_data'),
    path('api/dpd-buckets/', views.api_dpd_buckets, name='api_dpd_buckets'),
    path('api/state-repayment/', views.api_state_repayment, name='api_state_repayment'),
    path('api/time-series/', views.api_time_series, name='api_time_series'),
    path('api/city-collected/', views.api_city_collected, name='api_city_collected'),
    path('api/city-uncollected/', views.api_city_uncollected, name='api_city_uncollected'),
    path('api/dpd-bucket-details/', views.api_dpd_bucket_details, name='api_dpd_bucket_details'),
    path('api/total-applications-details/', views.api_total_applications_details, name='api_total_applications_details'),
    path('api/cities-by-state/', views.api_cities_by_state, name='api_cities_by_state'),
    path('api/sync-data/', views.sync_data, name='sync_data'),
    # Fraud Summary API endpoints
    path('api/fraud/kpi-data/', views.api_fraud_kpi_data, name='api_fraud_kpi_data'),
    path('api/fraud/dpd-buckets/', views.api_fraud_dpd_buckets, name='api_fraud_dpd_buckets'),
    path('api/fraud/state-repayment/', views.api_fraud_state_repayment, name='api_fraud_state_repayment'),
    path('api/fraud/time-series/', views.api_fraud_time_series, name='api_fraud_time_series'),
    path('api/fraud/city-collected/', views.api_fraud_city_collected, name='api_fraud_city_collected'),
    path('api/fraud/city-uncollected/', views.api_fraud_city_uncollected, name='api_fraud_city_uncollected'),
    path('api/fraud/total-applications-details/', views.api_fraud_total_applications_details, name='api_fraud_total_applications_details'),
    path('api/fraud/pending-cases-by-amount/', views.api_fraud_pending_cases_by_amount, name='api_fraud_pending_cases_by_amount'),
    # Loan Count Wise API endpoint
    path('api/loan-count-wise/', views.api_loan_count_wise, name='api_loan_count_wise'),
]
