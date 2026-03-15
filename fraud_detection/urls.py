from django.urls import path
from . import views

urlpatterns = [
    path('control/fraud-alerts/', views.fraud_alerts, name='fraud_alerts'),
    path('control/fraud-history/', views.fraud_history, name='fraud_history'),
    # NOTE: 'reports' URL is owned by transactions/urls.py — no duplicate here
]
