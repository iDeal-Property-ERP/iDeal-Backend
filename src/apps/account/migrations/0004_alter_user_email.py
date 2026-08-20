from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0003_user_avatar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, default=None, max_length=254, null=True, unique=True),
        ),
    ]
