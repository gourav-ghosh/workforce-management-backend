# Generated for mobile-number login migration.

import django.contrib.auth.validators
from django.db import migrations, models


def populate_mobile_number(apps, schema_editor):
    """Populate mobile_number for existing users from their worker profile."""
    User = apps.get_model("accounts", "User")
    WorkerProfile = apps.get_model("workers", "WorkerProfile")
    for profile in WorkerProfile.objects.select_related("user").all():
        user = profile.user
        if not user.mobile_number and profile.phone_number:
            user.mobile_number = profile.phone_number
            user.save(update_fields=["mobile_number"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("workers", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                blank=True,
                help_text="Optional. Retained for Django compatibility; not used for login.",
                max_length=150,
                null=True,
                validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                verbose_name="username",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="mobile_number",
            field=models.CharField(
                db_index=True,
                default="",
                help_text="Used as the login identifier instead of username.",
                max_length=20,
                unique=True,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(populate_mobile_number, reverse_noop),
    ]
