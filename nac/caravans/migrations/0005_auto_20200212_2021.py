# Generated by Django 2.2.7 on 2020-02-12 09:21

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('caravans', '0004_auto_20200204_1428'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductionUnit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('production_unit', models.CharField(max_length=50, unique=True)),
                ('unit_details', models.CharField(max_length=500)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.AddField(
            model_name='series',
            name='production_unit1',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='caravans.ProductionUnit'),
            preserve_default=False,
        ),
    ]
