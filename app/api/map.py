import requests
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/map", tags=["Map"])


@router.get("/static")
def get_static_map(
    lat: float = Query(...),
    lng: float = Query(...),
    zoom: int = Query(18),
    width: int = Query(320),
    height: int = Query(220),
):
    map_url = "https://staticmap.openstreetmap.de/staticmap.php"

    params = {
        "center": f"{lat},{lng}",
        "zoom": zoom,
        "size": f"{width}x{height}",
        "markers": f"{lat},{lng},red-pushpin",
    }

    headers = {"User-Agent": "TPC-HRIS-Attendance/1.0 (chrisianapuhin@gmail.com)"}

    try:
        response = requests.get(
            map_url,
            params=params,
            headers=headers,
            timeout=15,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch map image. Status: {response.status_code}",
            )

        content_type = response.headers.get("content-type", "")

        if "image" not in content_type:
            raise HTTPException(
                status_code=502,
                detail=f"Map service did not return image. Content-Type: {content_type}",
            )

        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400",
            },
        )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Map service unavailable: {str(e)}",
        )
