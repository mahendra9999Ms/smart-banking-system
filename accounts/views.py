import hashlib, random
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum
from django.core.paginator import Paginator
from decimal import Decimal

from .models import UserProfile, AuditLog
from transactions.models import Transaction
from fraud_detection.models import FraudRecord


# ── helpers ──────────────────────────────────────────────────────────
def is_admin(user):
    return user.is_staff

def log_action(actor, action, target='', details=''):
    AuditLog.objects.create(actor=actor, action=action, target=target, details=details)


# ── AUTH ──────────────────────────────────────────────────────────────
def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            return redirect('admin_dashboard' if user.is_staff else 'user_dashboard')
        else:
            error = "Your account is blocked by admin" if (user and not user.is_active) \
                    else "Invalid username or password"
            return render(request, 'login.html', {'error': error})
    return render(request, 'login.html')


def register_view(request):
    """Self-registration for new users."""
    if request.user.is_authenticated:
        return redirect('user_dashboard')
    message = None
    if request.method == "POST":
        username  = request.POST.get('username', '').strip()
        password  = request.POST.get('password', '')
        confirm   = request.POST.get('confirm_password', '')
        full_name = request.POST.get('full_name', '').strip()
        email     = request.POST.get('email', '').strip()
        phone     = request.POST.get('phone', '').strip()

        if not username or not password:
            message = "Username and password are required."
        elif password != confirm:
            message = "Passwords do not match."
        elif User.objects.filter(username=username).exists():
            message = "Username already taken."
        else:
            user = User.objects.create_user(username=username, password=password)
            profile = UserProfile.objects.get(user=user)
            profile.full_name = full_name
            profile.email     = email
            profile.phone     = phone
            profile.save()
            messages.success(request, "Account created! Please log in.")
            return redirect('login')
    return render(request, 'register.html', {'message': message})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


# ── USER DASHBOARD ────────────────────────────────────────────────────
@login_required
def user_dashboard(request):
    if request.user.is_staff:
        return redirect('admin_dashboard')
    profile = UserProfile.objects.get(user=request.user)
    return render(request, 'user/dashboard.html', {
        'balance': profile.balance,
        'account_number': profile.account_number
    })


# ── USER PROFILE + PASSWORD CHANGE ───────────────────────────────────
@login_required
def profile(request):
    profile = UserProfile.objects.get(user=request.user)
    msg = None
    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'update_profile':
            profile.full_name = request.POST.get('full_name', '').strip()
            profile.email     = request.POST.get('email', '').strip()
            profile.phone     = request.POST.get('phone', '').strip()
            profile.save()
            msg = "Profile updated successfully."
        elif action == 'change_password':
            old_pw  = request.POST.get('old_password', '')
            new_pw  = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            if not request.user.check_password(old_pw):
                msg = "Current password is incorrect."
            elif new_pw != confirm:
                msg = "New passwords do not match."
            elif len(new_pw) < 6:
                msg = "Password must be at least 6 characters."
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                msg = "Password changed successfully."
    return render(request, 'user/profile.html', {'profile': profile, 'msg': msg})


# ── ADMIN DASHBOARD ───────────────────────────────────────────────────
@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    total_balance = UserProfile.objects.aggregate(Sum('balance'))['balance__sum'] or 0
    context = {
        'total_transactions': Transaction.objects.count(),
        'fraud_count':        FraudRecord.objects.count(),
        'user_count':         User.objects.filter(is_staff=False).count(),
        'total_balance':      total_balance,
    }
    return render(request, 'admin/dashboard.html', context)


# ── MANAGE USERS (Block/Unblock + Paginate) ───────────────────────────
@login_required
@user_passes_test(is_admin)
def manage_users(request):
    if request.method == "POST":
        user_id = request.POST.get('user_id')
        action  = request.POST.get('action')
        user    = get_object_or_404(User, id=user_id)
        if action == "block":
            user.is_active = False
            log_action(request.user, "Block User", user.username)
        elif action == "unblock":
            user.is_active = True
            log_action(request.user, "Unblock User", user.username)
        user.save()
        return redirect('manage_users')

    qs   = User.objects.filter(is_superuser=False).order_by('username')
    page = Paginator(qs, 10).get_page(request.GET.get('page'))
    return render(request, 'admin/manage_users.html', {'users': page})


# ── CREATE BANK ACCOUNT ───────────────────────────────────────────────
@login_required
@user_passes_test(lambda u: u.is_staff)
def create_user(request):
    message = None
    if request.method == "POST":
        username  = request.POST['username']
        password  = request.POST['password']
        balance   = request.POST['balance']
        full_name = request.POST.get('full_name', '').strip()
        email     = request.POST.get('email', '').strip()
        phone     = request.POST.get('phone', '').strip()
        if User.objects.filter(username=username).exists():
            message = "Username already exists!"
        else:
            user = User.objects.create_user(username=username, password=password)
            profile = UserProfile.objects.get(user=user)
            profile.balance   = balance
            profile.full_name = full_name
            profile.email     = email
            profile.phone     = phone
            profile.save()
            log_action(request.user, "Create Account", username,
                       f"Initial balance: {balance}")
            message = "Account Created Successfully"
    return render(request, 'admin/create_user.html', {'msg': message})


# ── ADMIN EDIT USER DETAILS ───────────────────────────────────────────
@login_required
@user_passes_test(lambda u: u.is_staff)
def edit_user(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    profile     = get_object_or_404(UserProfile, user=target_user)
    message     = None

    if request.method == "POST":
        action = request.POST.get('action', 'update')

        if action == 'update':
            new_username  = request.POST.get('username', '').strip()
            full_name     = request.POST.get('full_name', '').strip()
            email         = request.POST.get('email', '').strip()
            phone         = request.POST.get('phone', '').strip()

            # Username uniqueness check (allow same user to keep own name)
            if new_username and new_username != target_user.username:
                if User.objects.filter(username=new_username).exists():
                    message = "Username already taken."
                    return render(request, 'admin/edit_user.html',
                                  {'target_user': target_user, 'profile': profile, 'message': message})
                target_user.username = new_username
                target_user.save()

            profile.full_name = full_name
            profile.email     = email
            profile.phone     = phone
            profile.save()

            log_action(request.user, "Edit User Details", target_user.username,
                       f"Name={full_name}, Email={email}, Phone={phone}")
            message = "User details updated successfully."

        elif action == 'reset_password':
            new_pw  = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            if new_pw != confirm:
                message = "Passwords do not match."
            elif len(new_pw) < 6:
                message = "Password must be at least 6 characters."
            else:
                target_user.set_password(new_pw)
                target_user.save()
                log_action(request.user, "Reset Password", target_user.username)
                message = "Password reset successfully."

    return render(request, 'admin/edit_user.html',
                  {'target_user': target_user, 'profile': profile, 'message': message})


# ── ADMIN BALANCE ADJUSTMENT ──────────────────────────────────────────
@login_required
@user_passes_test(lambda u: u.is_staff)
def adjust_balance(request, user_id):
    user    = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(UserProfile, user=user)
    if request.method == "POST":
        action = request.POST.get("action")
        amount = Decimal(request.POST.get("amount"))
        if action == "credit":
            profile.balance += amount
            status = "Credited by Admin"
        elif action == "debit":
            if amount > profile.balance:
                return redirect('manage_users')
            profile.balance -= amount
            status = "Debited by Admin"
        else:
            return redirect('manage_users')
        profile.save()
        Transaction.objects.create(
            user=user, bill_type="Admin Adjustment",
            amount=amount, status=status
        )
        log_action(request.user, f"Balance {action.title()}", user.username,
                   f"Amount: {amount}")
    return redirect('manage_users')


# ── AUDIT LOG ─────────────────────────────────────────────────────────
@login_required
@user_passes_test(is_admin)
def audit_log_view(request):
    qs   = AuditLog.objects.all().order_by('-timestamp')
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    return render(request, 'admin/audit_log.html', {'logs': page})
