from app.utils.timezone import convert_datetime_to_ph


def api_response(data):
    return convert_datetime_to_ph(data)
