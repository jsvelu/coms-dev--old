# Generated by Django 2.2.7 on 2021-01-06 01:49

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='PriceAuditCapture',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('series_code', models.CharField(max_length=500, null=True)),
                ('existing_wholesale_price', models.CharField(max_length=500, null=True)),
                ('new_wholesale_price', models.CharField(max_length=500, null=True)),
                ('existing_retail_price', models.CharField(max_length=500, null=True)),
                ('new_retail_price', models.CharField(max_length=500, null=True)),
                ('price_changed_datetime', models.CharField(max_length=500, null=True)),
                ('price_changed_user', models.CharField(max_length=500, null=True)),
            ],
            options={
                'verbose_name': 'Price Audit Capture',
                'verbose_name_plural': 'Price Audit Capture',
                'db_table': 'pricechange_audit_capture',
                'ordering': ('id',),
            },
        ),
    ]
