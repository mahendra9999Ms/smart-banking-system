from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fraud_detection', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='fraudrecord',
            name='risk_score',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='fraudrecord',
            name='explanation',
            field=models.TextField(blank=True, default=''),
        ),
    ]
