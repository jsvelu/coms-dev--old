# Generated by Django 2.2.7 on 2019-12-29 10:47

import ckeditor_uploader.fields
from django.db import migrations, models
import django.db.models.deletion
import newage.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ArchiveFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('name', models.TextField()),
                ('file', models.FileField(upload_to=newage.models.archive_file_path)),
                ('gen_time', models.DateTimeField()),
                ('type', models.IntegerField(choices=[(1, 'Bill of Materials Ostendo'), (2, 'Bill of Materials CSV')])),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='Postcode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(blank=True, max_length=4, null=True)),
            ],
            options={
                'db_table': 'postcode',
            },
        ),
        migrations.CreateModel(
            name='Settings',
            fields=[
                ('id', models.IntegerField(choices=[(1, 'Settings is a single record')], default=1, primary_key=True, serialize=False)),
                ('home_page_banner_html', ckeditor_uploader.fields.RichTextUploadingField(blank=True, help_text='HTML banner that is displayed at the top of the home page', null=True)),
                ('showroom_splash', models.ImageField(blank=True, help_text='Image that is displayed on the showroom order entry page', null=True, upload_to='settings')),
                ('schedule_lockdown_month', models.DateField(blank=True, null=True)),
                ('schedule_lockdown_number', models.IntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Settings',
                'verbose_name_plural': 'Settings',
                'permissions': (('view_commons', 'Access the Common Lookup API'),),
            },
        ),
        migrations.CreateModel(
            name='State',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=50, null=True, unique=True)),
                ('code', models.CharField(blank=True, max_length=5, null=True, unique=True)),
            ],
            options={
                'db_table': 'state',
            },
        ),
        migrations.CreateModel(
            name='Suburb',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('post_code', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='newage.Postcode')),
            ],
            options={
                'db_table': 'suburb',
                'unique_together': {('name', 'post_code')},
            },
        ),
        migrations.AddField(
            model_name='postcode',
            name='state',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='newage.State'),
        ),
        migrations.CreateModel(
            name='Address',
            fields=[
                ('deleted', models.DateTimeField(blank=True, default=None, editable=False, null=True)),
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('address', models.CharField(blank=True, max_length=255, null=True)),
                ('address2', models.CharField(blank=True, max_length=255, null=True)),
                ('suburb', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='newage.Suburb')),
            ],
            options={
                'db_table': 'address',
            },
        ),
        migrations.AlterUniqueTogether(
            name='postcode',
            unique_together={('number', 'state')},
        ),
    ]
