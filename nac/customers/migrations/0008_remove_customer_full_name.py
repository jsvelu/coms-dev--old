# Generated by Django 2.2.7 on 2020-02-13 06:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0007_auto_20200213_1714'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customer',
            name='full_name',
        ),
    ]
