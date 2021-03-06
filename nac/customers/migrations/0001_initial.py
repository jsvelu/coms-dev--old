# Generated by Django 2.2.7 on 2019-12-29 10:47

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AcquisitionSource',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('egm_value', models.IntegerField(choices=[(1, 'Walkin'), (2, 'Telephone'), (3, 'Internet Lead'), (4, 'Manufacturer Lead')], default=3, verbose_name=' eGM value')),
            ],
            options={
                'db_table': 'acquisition_source',
            },
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('egm_customer_id', models.IntegerField(blank=True, null=True)),
                ('first_name', models.CharField(blank=True, max_length=100, null=True)),
                ('last_name', models.CharField(blank=True, max_length=100, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone1', models.CharField(blank=True, max_length=20, null=True)),
                ('phone2', models.CharField(blank=True, max_length=20, null=True)),
                ('phone_delivery', models.CharField(blank=True, max_length=20, null=True)),
                ('phone_invoice', models.CharField(blank=True, max_length=20, null=True)),
                ('partner_name', models.CharField(blank=True, max_length=100, null=True)),
                ('lead_type', models.IntegerField(choices=[(1, 'Lead'), (2, 'Customer'), (3, 'e-GoodManners')])),
                ('model_type', models.IntegerField(blank=True, choices=[(1, 'Family Caravans'), (2, 'Luxury Caravans'), (3, 'Offroad Caravans'), (4, 'Caravans over 19 foot'), (5, 'Caravans under 19 foot')], null=True)),
                ('creation_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('tow_vehicle', models.CharField(blank=True, max_length=200, null=True)),
                ('mailing_list', models.BooleanField(default=False)),
                ('is_up_to_date_with_egm', models.BooleanField(default=False)),
                ('acquisition_source', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='customers.AcquisitionSource')),
            ],
            options={
                'db_table': 'customer',
                'permissions': (('list_customer', 'List Customers'), ('broadcast_email', 'Broadcast Email to Leads'), ('manage_self_and_dealership_leads_only', 'Can only manage leads that are assigned to self, or to dealerships where this user is principal'), ('broadcast_email_self_and_dealership_leads_only', 'Can only broadcast emails to leads that are assigned to self, or to dealerships where this user is principal')),
            },
        ),
        migrations.CreateModel(
            name='CustomerStatus',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.IntegerField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50)),
            ],
            options={
                'db_table': 'customer_status',
            },
        ),
        migrations.CreateModel(
            name='SourceOfAwareness',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'db_table': 'source_of_awareness',
            },
        ),
        migrations.CreateModel(
            name='CustomerStatusHistory',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('status_assignment_time', models.DateTimeField()),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='customers.Customer')),
            ],
            options={
                'db_table': 'customer_status_history',
            },
        ),
    ]
