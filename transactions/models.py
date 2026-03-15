from django.db import models
from django.contrib.auth.models import User


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('Success', 'Success'),
        ('Blocked - Fraud', 'Blocked - Fraud'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bill_type = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    risk_score = models.IntegerField(default=0)

    # 🧠 NEW FIELD — Explanation Storage
    explanation = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.bill_type}"
