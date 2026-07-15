import httpx

NAGER_BASE_URL = "https://date.nager.at/api/v3"


async def fetch_ph_holidays(year: int) -> list[dict]:
    """
    Calls Nager.Date public holidays API for the Philippines.
    Returns raw list of holiday dicts, e.g.:
    {
        "date": "2026-01-01",
        "localName": "New Year's Day",
        "name": "New Year's Day",
        "countryCode": "PH",
        "fixed": true,
        "global": true,
        "counties": null,
        "types": ["Public"]
    }
    """
    url = f"{NAGER_BASE_URL}/PublicHolidays/{year}/PH"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()