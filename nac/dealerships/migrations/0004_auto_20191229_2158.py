# Generated by Django 2.2.7 on 2019-12-29 10:58

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dealerships', '0003_auto_20191229_2154'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dealershipuserdealership',
            name='dealership_user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='user_ref', to=settings.AUTH_USER_MODEL),
        ),
    ]
