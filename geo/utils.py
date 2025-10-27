import requests
from django.conf import settings

from .models import Location


def fetch_coordinates(address):
    base_url = "https://geocode-maps.yandex.ru/1.x"
    response = requests.get(base_url, params={
        "geocode": address,
        "apikey": settings.YANDEX_APIKEY,
        "format": "json",
    })
    response.raise_for_status()
    found_places = response.json()['response']['GeoObjectCollection']['featureMember']

    if not found_places:
        return None, None

    most_relevant = found_places[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(" ")
    return lat, lon


def get_or_create_location(address):
    normalized_address = (address or '').strip()
    if not normalized_address:
        return None

    location, created = Location.objects.get_or_create(address=normalized_address)
    if created or not location.latitude or not location.longitude:
        lat, lon = fetch_coordinates(normalized_address)
        if lat is None or lon is None:
            return None

        location.latitude = lat
        location.longitude = lon
        location.save(update_fields=['latitude', 'longitude'])

    return location
