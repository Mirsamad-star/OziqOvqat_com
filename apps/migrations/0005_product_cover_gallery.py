from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0004_alter_category_options_alter_product_options_and_more"),
    ]
    operations = [
        migrations.AddField(
            model_name="product",
            name="cover_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="product",
            name="gallery_urls",
            field=models.TextField(blank=True, default="", help_text="Qo‘shimcha rasm URL lari (har qatorda bitta)"),
        ),
    ]
