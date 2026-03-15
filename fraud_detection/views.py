from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import FraudRecord
from transactions.models import Transaction


def is_admin(user):
    return user.is_staff


@login_required
@user_passes_test(is_admin)
def fraud_alerts(request):
    records = FraudRecord.objects.order_by('-detected_at')[:10]
    return render(request, 'admin/fraud_alerts.html', {'records': records})


@login_required
@user_passes_test(is_admin)
def fraud_history(request):
    records = FraudRecord.objects.all().order_by('-detected_at')
    return render(request, 'admin/fraud_history.html', {'records': records})


@login_required
@user_passes_test(is_admin)
def reports(request):
    total = Transaction.objects.count()
    success = Transaction.objects.filter(status="Success").count()
    fraud = FraudRecord.objects.count()

    return render(request, 'admin/reports.html', {
        'total': total,
        'success': success,
        'fraud': fraud
    })
