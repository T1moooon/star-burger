from django.db import models
from django.utils import timezone


class Location(models.Model):
    address = models.CharField('Адрес', max_length=255, unique=True)
    latitude = models.DecimalField(
        'Широта',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    longitude = models.DecimalField(
        'Долгота',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    date_of_request = models.DateTimeField(
        'Дата запроса',
        default=timezone.now
    )

    def __str__(self):
        return self.address
