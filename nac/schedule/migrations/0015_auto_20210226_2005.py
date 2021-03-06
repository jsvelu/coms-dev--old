# Generated by Django 2.2.7 on 2021-02-26 09:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0014_auto_20210223_1754'),
    ]

    operations = [
        # migrations.RemoveField(
        #     model_name='ordertransport',
        #     name='actual_watertest_date',
        # ),
        # migrations.RemoveField(
        #     model_name='ordertransport',
        #     name='planned_watertest_date',
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='collection_comments',
        #     field=models.TextField(null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='collection_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='detailing_comments',
        #     field=models.TextField(null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='detailing_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='email_sent',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='plumbing_comments',
        #     field=models.TextField(null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='plumbing_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='purchase_order_raised_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='senior_designer_verfied_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='watertest_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='weigh_bridge_comments',
        #     field=models.TextField(null=True),
        # ),
        # migrations.AddField(
        #     model_name='ordertransport',
        #     name='weigh_bridge_date',
        #     field=models.DateField(blank=True, null=True),
        # ),
        # migrations.AlterField(
        #     model_name='capacity',
        #     name='production_unit',
        #     field=models.IntegerField(choices=[(1, 'Caravans'), (2, 'Pop-Top/Campers')]),
        # ),
        # migrations.AlterField(
        #     model_name='monthplanning',
        #     name='production_unit',
        #     field=models.IntegerField(choices=[(1, 'Caravans'), (2, 'Pop-Top/Campers')]),
        # ),
        migrations.CreateModel(
            name='DealerMonthPlanning',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dealership_id', models.IntegerField(blank=True, null=True)),
                ('production_month', models.DateField(help_text='The first day of the month represented by this model.')),
                ('capacity_allotted', models.IntegerField()),
                ('production_unit', models.IntegerField(choices=[(1, 'Caravans'), (2, 'Pop-Top/Campers')])),
            ],
            options={
                'unique_together': {('production_month', 'production_unit', 'dealership_id')},
            },
        ),
    ]
