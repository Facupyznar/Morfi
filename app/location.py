import math

from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim


geolocator = Nominatim(user_agent="morfi-location")


def parse_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("Las coordenadas recibidas no son válidas.")


def geocode_address(address):
    normalized = (address or "").strip()
    if not normalized:
        raise ValueError("La dirección es obligatoria.")

    try:
        result = geolocator.geocode(
            normalized,
            exactly_one=True,
            language="es",
            country_codes="ar",
            addressdetails=True,
        )
    except GeocoderServiceError as ex:
        raise ValueError("No se pudo validar la dirección en este momento.") from ex

    if not result:
        raise ValueError("No pudimos encontrar esa dirección.")

    return {
        "address": result.address or normalized,
        "latitude": float(result.latitude),
        "longitude": float(result.longitude),
    }


def resolve_location_payload(address, latitude=None, longitude=None):
    normalized_address = (address or "").strip()
    lat_value = parse_float(latitude)
    lng_value = parse_float(longitude)

    if lat_value is not None and lng_value is not None:
        if not normalized_address:
            raise ValueError("La dirección es obligatoria.")
        return {
            "address": normalized_address,
            "latitude": lat_value,
            "longitude": lng_value,
        }

    return geocode_address(normalized_address)


def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371.0
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c
