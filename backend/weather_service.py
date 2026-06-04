from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


DEFAULT_LOCATION = {
    "name": "ลำลูกกา, ปทุมธานี",
    "latitude": 13.9323,
    "longitude": 100.7494,
}

REVERSE_GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
REVERSE_GEOCODE_USER_AGENT = "CSI_AI_DrKaset/1.0"

WEATHER_CODE_TH = {
    0: "ท้องฟ้าแจ่มใส",
    1: "แดดเป็นส่วนใหญ่",
    2: "มีเมฆบางส่วน",
    3: "เมฆมาก",
    45: "มีหมอก",
    48: "มีหมอกน้ำค้างแข็ง",
    51: "ฝนปรอยเล็กน้อย",
    53: "ฝนปรอยปานกลาง",
    55: "ฝนปรอยหนัก",
    61: "ฝนเล็กน้อย",
    63: "ฝนปานกลาง",
    65: "ฝนหนัก",
    80: "ฝนซู่เล็กน้อย",
    81: "ฝนซู่ปานกลาง",
    82: "ฝนซู่หนัก",
    95: "ฝนฟ้าคะนอง",
    96: "ฝนฟ้าคะนองมีลูกเห็บ",
    99: "ฝนฟ้าคะนองมีลูกเห็บหนัก",
}


def _weather_label(code: int | None) -> str:
    if code is None:
        return "ไม่ทราบสภาพอากาศ"
    return WEATHER_CODE_TH.get(code, "สภาพอากาศเปลี่ยนแปลง")


def _round_number(value: Any) -> int | None:
    return round(value) if isinstance(value, (int, float)) else None


def _icon_name(code: int | None, is_day: int | None = 1) -> str:
    if code in (61, 63, 65, 80, 81, 82, 95, 96, 99):
        return "rain"
    if code in (45, 48):
        return "fog"
    if code in (2, 3):
        return "cloud"
    if code in (51, 53, 55):
        return "drizzle"
    if is_day == 0:
        return "moon"
    return "sun"


def _clean_province_name(value: str | None) -> str | None:
    if not value:
        return None
    province = value.strip()
    for prefix in ("Province of ", "Chang Wat ", "จังหวัด"):
        if province.startswith(prefix):
            province = province[len(prefix):].strip()
    return province or None


@lru_cache(maxsize=128)
def _reverse_geocode_province(latitude: float, longitude: float) -> str | None:
    params = urlencode(
        {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "accept-language": "th,en",
            "zoom": 10,
            "addressdetails": 1,
        }
    )
    request = Request(
        f"{REVERSE_GEOCODE_URL}?{params}",
        headers={"User-Agent": REVERSE_GEOCODE_USER_AGENT},
    )
    with urlopen(request, timeout=6) as response:
        raw = json.loads(response.read().decode("utf-8"))

    address = raw.get("address", {})
    province = (
        address.get("province")
        or address.get("state")
        or address.get("region")
        or address.get("city")
        or address.get("county")
    )
    return _clean_province_name(province)


def _closest_hour_index(times: list[str], now: datetime) -> int:
    if not times:
        return 0
    best_index = 0
    best_delta = None
    for index, value in enumerate(times):
        hour = datetime.fromisoformat(value)
        delta = abs((hour - now).total_seconds())
        if best_delta is None or delta < best_delta:
            best_index = index
            best_delta = delta
    return best_index


def _daily_items(daily: dict[str, list[Any]]) -> list[dict[str, Any]]:
    days = []
    for index, day in enumerate(daily.get("time", [])[:8]):
        days.append(
            {
                "date": day,
                "weekday": datetime.fromisoformat(day).strftime("%a"),
                "temp_max": _round_number(daily.get("temperature_2m_max", [None])[index]),
                "temp_min": _round_number(daily.get("temperature_2m_min", [None])[index]),
                "precipitation_probability": daily.get("precipitation_probability_max", [None])[index],
                "weather_code": daily.get("weather_code", [None])[index],
                "condition": _weather_label(daily.get("weather_code", [None])[index]),
                "icon": _icon_name(daily.get("weather_code", [None])[index]),
            }
        )
    return days


def _hourly_items(hourly: dict[str, list[Any]], now: datetime) -> list[dict[str, Any]]:
    times = hourly.get("time", [])
    if not times:
        return []
    start = _closest_hour_index(times, now)
    selected = range(start, min(start + 12, len(times)), 2)
    return [
        {
            "time": times[index],
            "hour": datetime.fromisoformat(times[index]).strftime("%H:%M"),
            "temperature": _round_number(hourly.get("temperature_2m", [None])[index]),
            "precipitation_probability": hourly.get("precipitation_probability", [None])[index],
        }
        for index in selected
    ]


@lru_cache(maxsize=32)
def _fetch_weather_cached(latitude: float, longitude: float, location_name: str, cache_key: str) -> dict[str, Any]:
    del cache_key
    params = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Asia/Bangkok",
            "forecast_days": 8,
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,is_day",
            "hourly": "temperature_2m,precipitation_probability",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        }
    )
    with urlopen(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=8) as response:
        raw = json.loads(response.read().decode("utf-8"))

    current = raw.get("current", {})
    now = datetime.fromisoformat(current.get("time") or datetime.now().isoformat(timespec="minutes"))
    weather_code = current.get("weather_code")
    current_weather = {
        "time": current.get("time"),
        "temperature": _round_number(current.get("temperature_2m")),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": _round_number(current.get("wind_speed_10m")),
        "weather_code": weather_code,
        "condition": _weather_label(weather_code),
        "icon": _icon_name(weather_code, current.get("is_day")),
    }

    return {
        "source": "Open-Meteo",
        "location": {
            "name": location_name,
            "latitude": latitude,
            "longitude": longitude,
        },
        "current": current_weather,
        "hourly": _hourly_items(raw.get("hourly", {}), now),
        "daily": _daily_items(raw.get("daily", {})),
        "summary_for_model": build_weather_summary(current_weather, location_name),
    }


def get_weather(latitude: float | None = None, longitude: float | None = None, location_name: str | None = None) -> dict[str, Any]:
    latitude = latitude if latitude is not None else DEFAULT_LOCATION["latitude"]
    longitude = longitude if longitude is not None else DEFAULT_LOCATION["longitude"]
    if not location_name and latitude is not None and longitude is not None:
        try:
            location_name = _reverse_geocode_province(round(latitude, 4), round(longitude, 4))
        except Exception:
            location_name = None
    location_name = location_name or DEFAULT_LOCATION["name"]
    cache_key = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
    return _fetch_weather_cached(round(latitude, 4), round(longitude, 4), location_name, cache_key)


def build_weather_summary(current: dict[str, Any], location_name: str) -> str:
    return (
        f"สภาพอากาศล่าสุดที่ {location_name}: "
        f"{current.get('condition')} อุณหภูมิ {current.get('temperature')}°C "
        f"ความชื้น {current.get('humidity')}% "
        f"ฝน {current.get('precipitation')} มม. "
        f"ลม {current.get('wind_speed')} กม./ชม."
    )


def get_weather_summary_for_prompt() -> str | None:
    try:
        return get_weather().get("summary_for_model")
    except Exception:
        return None
