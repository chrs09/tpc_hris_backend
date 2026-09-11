import math


def calculate_distance_meters(lat1, lon1, lat2, lon2):
    """
    Haversine formula to calculate distance between 2 points in meters
    """
    R = 6371000  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def is_within_radius(lat, long, store) -> bool:
    """True if (lat, long) falls within `store.allowed_radius_meters` of
    `store`'s own coordinates. `store` must have latitude/longitude/
    allowed_radius_meters attributes (i.e. a Store model instance)."""
    if store.latitude is None or store.longitude is None:
        return False
    distance = calculate_distance_meters(lat, long, store.latitude, store.longitude)
    return distance <= store.allowed_radius_meters


def find_nearest_store(stores, lat, long, hub_only: bool = False, within_radius_only: bool = True):
    """Given an already-fetched list of Store rows, returns
    (nearest_store_or_None, distance_meters_or_inf) -- the closest store to
    (lat, long), optionally restricted to hubs (`hub_only`) and optionally
    requiring the match to fall within that store's own geofence radius
    (`within_radius_only`, the default -- matches the "closest registered
    store" behavior used at check-in/checkout). Skips stores with
    missing/zero coordinates. Centralizes the "loop all stores, find
    nearest" pattern that used to be copy-pasted at every trip checkpoint
    (start, check-in, check-out, complete)."""
    nearest = None
    nearest_distance = float("inf")

    for store in stores:
        if hub_only and not store.is_hub:
            continue
        if (
            store.latitude is None
            or store.longitude is None
            or (store.latitude == 0 and store.longitude == 0)
        ):
            continue

        distance = calculate_distance_meters(lat, long, store.latitude, store.longitude)

        if within_radius_only and distance > store.allowed_radius_meters:
            continue

        if distance < nearest_distance:
            nearest_distance = distance
            nearest = store

    return nearest, nearest_distance
