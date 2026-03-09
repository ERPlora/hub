from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0002_remove_hubconfig_selected_blocks_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeconfig',
            name='instagram',
            field=models.URLField(blank=True, help_text='Instagram profile URL'),
        ),
        migrations.AddField(
            model_name='storeconfig',
            name='facebook',
            field=models.URLField(blank=True, help_text='Facebook page URL'),
        ),
        migrations.AddField(
            model_name='storeconfig',
            name='tiktok',
            field=models.URLField(blank=True, help_text='TikTok profile URL'),
        ),
        migrations.AddField(
            model_name='storeconfig',
            name='google_maps',
            field=models.URLField(blank=True, help_text='Google Maps link'),
        ),
        migrations.AddField(
            model_name='storeconfig',
            name='public_site_enabled',
            field=models.BooleanField(default=False, help_text='Enable public landing page at /public/'),
        ),
    ]
