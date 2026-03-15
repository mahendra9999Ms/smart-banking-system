from django.contrib.auth.models import User
from django.db import models


class FraudRecord(models.Model):
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    bill_type   = models.CharField(max_length=50)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    risk_score  = models.IntegerField(default=0)
    explanation = models.TextField(blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username
