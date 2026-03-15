from django.urls import path
from . import views

urlpatterns = [
    path('transactions/', views.transaction_history, name='transactions'),
    path('send-money/', views.send_money, name='send_money'),
    path('receive-money/', views.receive_money, name='receive_money'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),

    # Admin
    path('control/transactions/', views.all_transactions, name='all_transactions'),
    path('control/reports/', views.reports, name='reports'),  # NEW
]
