from django.contrib import admin
from django.urls import path, include
from accounts.views import login_view, logout_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # AUTH (root)
    path('', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    # APPS
    path('', include('accounts.urls')),
    path('', include('transactions.urls')),
    path('', include('billpay.urls')),
    path('', include('fraud_detection.urls')),
]
