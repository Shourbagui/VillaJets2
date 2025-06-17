from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('flights', '0004_alter_flightrequest_destination_airport_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='airport',
            name='country',
        ),
        migrations.AddField(
            model_name='airport',
            name='country_code',
            field=models.CharField(blank=True, max_length=2, null=True),
        ),
        migrations.AddField(
            model_name='airport',
            name='country_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='airport',
            name='elevation_ft',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='airport',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='airport',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='airport',
            name='type',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='airport',
            name='city',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='airport',
            name='iata_code',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AlterField(
            model_name='airport',
            name='name',
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name='flightrequest',
            name='destination_country',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='flightrequest',
            name='origin_country',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='airport',
            unique_together={('name', 'city', 'country_code')},
        ),
    ] 