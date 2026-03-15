import random, hashlib
from decimal import Decimal
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import UserProfile
from transactions.models import Transaction
from fraud_detection.models import FraudRecord
from fraud_detection.ml_model import predict_fraud


def _hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()


@login_required
def bill_pay(request):
    profile = UserProfile.objects.get(user=request.user)
    message = None
    fraud   = False

    if request.method == "POST":
        bill_type = request.POST.get('bill_type')
        try:
            amount = Decimal(request.POST.get('amount'))
        except (ValueError, TypeError):
            return render(request, 'user/bill_pay.html',
                          {'message': 'Invalid amount entered', 'balance': profile.balance})

        if amount <= 0:
            return render(request, 'user/bill_pay.html',
                          {'message': 'Amount must be greater than zero', 'balance': profile.balance})

        if amount > profile.balance:
            return render(request, 'user/bill_pay.html',
                          {'message': 'Insufficient balance', 'balance': profile.balance})

        # ── Full fraud pipeline ──────────────────────────────────────
        ml_result = predict_fraud(amount, bill_type)
        ml_risk   = 60 if ml_result == 1 else 10
        behavioral_risk = 0
        explanation     = []

        if profile.average_transaction_amount > 0:
            avg_amount   = float(profile.average_transaction_amount)
            deviation    = (float(amount) - avg_amount) / avg_amount
            if deviation > 2:
                behavioral_risk += 40
                explanation.append("Amount significantly higher than usual behavior")

        past = Transaction.objects.filter(user=request.user, status="Success").order_by('-created_at')
        if past.exists():
            time_diff = (timezone.now() - past.first().created_at).total_seconds()
            if time_diff < 60:
                behavioral_risk += 25
                explanation.append("Multiple transactions within short time")

        current_hour = datetime.now().hour
        if not (profile.usual_transaction_hour_start <= current_hour <= profile.usual_transaction_hour_end):
            behavioral_risk += 15
            explanation.append("Transaction outside usual time window")

        risk_score = min(ml_risk + behavioral_risk, 95)

        if risk_score >= 75:
            fraud   = True
            message = "Fraud detected. Bill payment blocked."
            with db_transaction.atomic():
                FraudRecord.objects.create(
                    user=request.user, bill_type=bill_type, amount=amount,
                    risk_score=risk_score,
                    explanation=" | ".join(explanation) if explanation else "High ML risk"
                )
                Transaction.objects.create(
                    user=request.user, bill_type=bill_type,
                    amount=amount, status="Blocked - Fraud",
                    risk_score=risk_score,
                    explanation=" | ".join(explanation) if explanation else "High ML risk"
                )

            fraud_count = FraudRecord.objects.filter(user=request.user).count()
            if fraud_count >= 3:
                request.user.is_active = False
                request.user.save()
                logout(request)
                messages.error(request,
                    "Your account has been locked due to multiple suspicious transactions.")
                return redirect('login')

            return render(request, 'user/bill_pay.html',
                          {'message': message, 'fraud': fraud, 'balance': profile.balance})

        # ── Normal bill payment ──────────────────────────────────────
        with db_transaction.atomic():
            profile.balance -= amount
            profile.save()
            Transaction.objects.create(
                user=request.user, bill_type=bill_type,
                amount=amount, status="Success",
                risk_score=risk_score,
                explanation="Normal bill payment"
            )
        message = f"{bill_type} bill payment of ₹{amount} successful."

        return render(request, 'user/bill_pay.html',
                      {'message': message, 'fraud': fraud, 'balance': profile.balance})

    return render(request, 'user/bill_pay.html', {'balance': profile.balance})
