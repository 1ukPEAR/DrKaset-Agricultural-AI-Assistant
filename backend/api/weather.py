from fastapi import APIRouter, Query

from weather_service import DEFAULT_LOCATION, get_weather

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("")
def current_weather(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    name: str | None = None,
):
    return get_weather(
        latitude=lat,
        longitude=lon,
        location_name=name,
    )
