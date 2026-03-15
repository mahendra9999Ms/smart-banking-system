import hashlib, random
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.contrib import messages
from django.db.models import Count
from django.core.paginator import Paginator
from django.utils import timezone

from accounts.models import UserProfile
from .models import Transaction
from fraud_detection.ml_model import predict_fraud
from fraud_detection.models import FraudRecord


# ── helpers ──────────────────────────────────────────────────────────
def _hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()

def _run_fraud_pipeline(request, amount, transfer_type, sender_profile, past_transactions):
    """Returns (risk_score, explanation_list)."""
    ml_result = predict_fraud(amount, transfer_type)
    ml_risk   = 60 if ml_result == 1 else 10
    behavioral_risk = 0
    explanation     = []

    if sender_profile.average_transaction_amount > 0:
        avg_amount       = float(sender_profile.average_transaction_amount)
        deviation_pct    = (float(amount) - avg_amount) / avg_amount
        if deviation_pct > 2:
            behavioral_risk += 40
            explanation.append("Amount significantly higher than usual behavior")

    if past_transactions.exists():
        time_diff = (timezone.now() - past_transactions.first().created_at).total_seconds()
        if time_diff < 60:
            behavioral_risk += 25
            explanation.append("Multiple transactions within short time")

    current_hour = datetime.now().hour
    if not (sender_profile.usual_transaction_hour_start <= current_hour
            <= sender_profile.usual_transaction_hour_end):
        behavioral_risk += 15
        explanation.append("Transaction outside usual time window")

    risk_score = min(ml_risk + behavioral_risk, 95)
    return risk_score, explanation


# ── TRANSACTION HISTORY (search + filter + paginate) ─────────────────
@login_required
def transaction_history(request):
    qs = Transaction.objects.filter(user=request.user).order_by('-created_at')

    # filters
    q         = request.GET.get('q', '').strip()
    tx_type   = request.GET.get('type', '').strip()
    from_date = request.GET.get('from_date', '').strip()
    to_date   = request.GET.get('to_date', '').strip()

    if q:
        qs = qs.filter(bill_type__icontains=q)
    if tx_type:
        qs = qs.filter(status=tx_type)
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)

    page = Paginator(qs, 15).get_page(request.GET.get('page'))
    return render(request, 'user/transactions.html', {
        'transactions': page,
        'q': q, 'type': tx_type, 'from_date': from_date, 'to_date': to_date,
    })


# ── SEND MONEY ────────────────────────────────────────────────────────
@login_required
def send_money(request):
    if not request.user.is_active:
        return render(request, 'user/send_money.html',
                      {'error': 'Your account is blocked due to multiple fraud attempts.'})

    if request.method == "POST":
        bank_name               = request.POST.get('bank_name')
        receiver_account_number = request.POST.get('receiver')
        try:
            amount = Decimal(request.POST.get('amount'))
        except Exception:
            return render(request, 'user/send_money.html', {'error': 'Invalid amount'})

        sender_profile    = UserProfile.objects.get(user=request.user)
        if amount > sender_profile.balance:
            return render(request, 'user/send_money.html', {'error': 'Insufficient balance'})

        transfer_type     = "External Transfer" if bank_name != "internal" else "Transfer"
        past_transactions = Transaction.objects.filter(user=request.user, status="Success").order_by('-created_at')

        risk_score, explanation = _run_fraud_pipeline(
            request, amount, transfer_type, sender_profile, past_transactions)

        if risk_score >= 75:
            FraudRecord.objects.create(
                user=request.user, bill_type=transfer_type, amount=amount,
                risk_score=risk_score,
                explanation=" | ".join(explanation) if explanation else "High ML risk"
            )
            Transaction.objects.create(
                user=request.user, bill_type="Attempted transfer",
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
            return render(request, 'user/send_money.html',
                          {'error': 'Fraud detected. Transfer blocked.'})

        # Generate OTP (hashed + expiry)
        otp     = str(random.randint(100000, 999999))
        expiry  = (timezone.now() + timezone.timedelta(minutes=5)).isoformat()
        request.session['otp_hash']   = _hash_otp(otp)
        request.session['otp_expiry'] = expiry
        request.session['otp_plain']  = otp     # shown to user only in demo

        if bank_name != "internal":
            request.session['transfer_data'] = {
                'external': True, 'bank_name': bank_name,
                'receiver_account': receiver_account_number,
                'amount': str(amount), 'risk_score': risk_score,
            }
        else:
            try:
                receiver_profile = UserProfile.objects.get(account_number=receiver_account_number)
            except UserProfile.DoesNotExist:
                return render(request, 'user/send_money.html', {'error': 'Invalid Account Number'})
            request.session['transfer_data'] = {
                'external': False,
                'receiver_id': receiver_profile.user.id,
                'amount': str(amount), 'risk_score': risk_score,
            }
        return redirect('verify_otp')

    return render(request, 'user/send_money.html')


# ── VERIFY OTP ────────────────────────────────────────────────────────
@login_required
def verify_otp(request):
    otp_hash   = request.session.get('otp_hash')
    otp_expiry = request.session.get('otp_expiry')
    if not otp_hash:
        return redirect('send_money')

    if request.method == "POST":
        entered_otp   = request.POST.get('otp', '')
        transfer_data = request.session.get('transfer_data')

        # Expiry check
        from django.utils.dateparse import parse_datetime
        expiry_dt = parse_datetime(otp_expiry)
        if expiry_dt and timezone.now() > expiry_dt:
            for k in ('otp_hash', 'otp_expiry', 'otp_plain', 'transfer_data'):
                request.session.pop(k, None)
            return render(request, 'user/verify_otp.html',
                          {'error': 'OTP has expired. Please retry the transfer.',
                           'transfer': transfer_data})

        if _hash_otp(entered_otp) == otp_hash:
            sender_profile = UserProfile.objects.get(user=request.user)
            amount         = Decimal(transfer_data['amount'])
            risk_score     = transfer_data['risk_score']

            if transfer_data.get('external'):
                bank_name = transfer_data['bank_name']
                sender_profile.balance -= amount
                sender_profile.save()
                Transaction.objects.create(
                    user=request.user,
                    bill_type=f"External Transfer to {bank_name}",
                    amount=amount, status="Success",
                    risk_score=risk_score, explanation="External bank transfer simulation"
                )
                for k in ('otp_hash','otp_expiry','otp_plain','transfer_data'):
                    request.session.pop(k, None)
                return render(request, 'user/receipt.html',
                              {'type': 'External Transfer', 'bank': bank_name, 'amount': amount})

            # Internal transfer
            receiver         = User.objects.get(id=transfer_data['receiver_id'])
            receiver_profile = UserProfile.objects.get(user=receiver)
            sender_profile.balance  -= amount
            receiver_profile.balance += amount
            sender_profile.save()
            receiver_profile.save()

            Transaction.objects.create(
                user=request.user,
                bill_type=f"Sent to {receiver_profile.account_number}",
                amount=amount, status="Success",
                risk_score=risk_score, explanation="Normal transaction"
            )
            Transaction.objects.create(
                user=receiver,
                bill_type=f"Received from {sender_profile.account_number}",
                amount=amount, status="Success",
                risk_score=risk_score, explanation="Received funds"
            )

            # Adaptive learning
            past = Transaction.objects.filter(user=request.user, status="Success")
            if past.exists():
                sender_profile.average_transaction_amount = sum(t.amount for t in past) / past.count()
                sender_profile.save()

            for k in ('otp_hash','otp_expiry','otp_plain','transfer_data'):
                request.session.pop(k, None)
            return render(request, 'user/receipt.html',
                          {'type': 'Internal Transfer',
                           'receiver': receiver_profile.account_number, 'amount': amount})
        else:
            return render(request, 'user/verify_otp.html',
                          {'error': 'Invalid OTP. Please try again.',
                           'transfer': transfer_data,
                           'otp': request.session.get('otp_plain')})

    return render(request, 'user/verify_otp.html', {
        'otp': request.session.get('otp_plain'),
        'transfer': request.session.get('transfer_data'),
    })


# ── RECEIVE MONEY ─────────────────────────────────────────────────────
@login_required
def receive_money(request):
    return render(request, 'user/receive_money.html')


# ── ADMIN ALL TRANSACTIONS ────────────────────────────────────────────
@login_required
@user_passes_test(lambda u: u.is_staff)
def all_transactions(request):
    qs    = Transaction.objects.all().order_by('-created_at')
    page  = Paginator(qs, 20).get_page(request.GET.get('page'))
    return render(request, 'admin/all_transactions.html', {'transactions': page})


# ── ADMIN REPORTS ─────────────────────────────────────────────────────
@login_required
@user_passes_test(lambda u: u.is_staff)
def reports(request):
    total       = Transaction.objects.count()
    fraud_txns  = Transaction.objects.filter(status="Blocked - Fraud").count()
    high_risk   = Transaction.objects.filter(risk_score__gte=70).count()
    fraud_rate  = round((fraud_txns / total) * 100, 2) if total > 0 else 0

    monthly_fraud = (
        Transaction.objects
        .filter(status="Blocked - Fraud")
        .extra(select={'month': "strftime('%%m', created_at)"})
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    return render(request, 'admin/reports.html', {
        'total_transactions': total,
        'fraud_transactions': fraud_txns,
        'high_risk':          high_risk,
        'fraud_rate':         fraud_rate,
        'monthly_fraud':      monthly_fraud,
    })
