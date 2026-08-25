"""Abstract base models shared across applications."""

from django.db import models


class TimeStampedModel(models.Model):
    """Adds creation/update timestamps to a model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
