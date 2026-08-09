from django.db import migrations


def forwards(apps, schema_editor):
    notification_model = apps.get_model("notification", "Notification")
    notification_model.objects.all().update(audience="both")


class Migration(migrations.Migration):
    dependencies = [
        ("notification", "0002_notification_audience_notificationpreference_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
