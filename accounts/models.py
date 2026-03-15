from django.contrib.auth.models import User
from django.db import models
import random


def generate_account_number():
    return "ASB" + str(random.randint(100000000, 999999999))


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account_number = models.CharField(max_length=12, unique=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Personal Details
    full_name  = models.CharField(max_length=100, blank=True, default='')
    email      = models.EmailField(blank=True, default='')
    phone      = models.CharField(max_length=15, blank=True, default='')

    # Behavioral Profile Fields
    average_transaction_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usual_transaction_hour_start = models.IntegerField(default=9)
    usual_transaction_hour_end   = models.IntegerField(default=18)

    def save(self, *args, **kwargs):
        if not self.account_number:
            self.account_number = generate_account_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username


class AuditLog(models.Model):
    actor     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_actions')
    action    = models.CharField(max_length=255)
    target    = models.CharField(max_length=255, blank=True)
    details   = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.actor} - {self.action} at {self.timestamp}"
