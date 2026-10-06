"""
Synthetic, anonymised telemetry shaped like the documented worked examples.

Coordinates sit on an arbitrary synthetic grid; identifiers, network names,
and MAC addresses are invented. Timestamps are UTC with `tz_name = "UTC"`,
so local time equals UTC.
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

ORIGIN = (10.0, 20.0)


def offset(point: Tuple[float, float], north_m: float, east_m: float) -> Tuple[float, float]:
    """Move a (lat, lon) point by meters north and east."""
    lat, lon = point
    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * math.cos(math.radians(lat)))
    return (round(lat + dlat, 6), round(lon + dlon, 6))


def row(
    *,
    school: str,
    device: str,
    when: datetime,
    point: Tuple[float, float],
    accuracy: float,
    bssid: Optional[str],
    ssid: Optional[str],
    govt: Tuple[float, float],
    school_name: str,
) -> Dict:
    return {
        "school_id_giga": school,
        "school_name": school_name,
        "device_id": device,
        "created_timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detected_latitude": point[0],
        "detected_longitude": point[1],
        "detected_location_accuracy": accuracy,
        "detected_wifi_bssid": bssid,
        "detected_wifi_ssid": ssid,
        "govt_latitude": govt[0],
        "govt_longitude": govt[1],
        "tz_name": "UTC",
        "local_created_timestamp": when,
        "local_date": when.date(),
        "local_hour": when.hour,
        "local_day_of_week": when.strftime("%A"),
        "is_weekday": when.weekday() < 5,
        "is_operational_hours": 8 <= when.hour <= 19,
    }


def frame(rows: List[Dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows)
    out["local_created_timestamp"] = pd.to_datetime(out["local_created_timestamp"])
    return out


# ---------------------------------------------------------------------------
# Example A: one fixed router, short window, pin about 15 km away
# ---------------------------------------------------------------------------
A_SITE = ORIGIN
A_GOVT = offset(ORIGIN, 0, 15_000)
A_NAME = "Shkolla e Bashkuar Alfa Beta"


def example_a() -> pd.DataFrame:
    site = A_SITE
    common = dict(
        school="SCH_A",
        device="DEV_A",
        bssid="28:00:00:00:00:0a",
        ssid="Home-4FF2-5G",
        govt=A_GOVT,
        school_name=A_NAME,
    )
    d1, d2, d3 = datetime(2026, 7, 21), datetime(2026, 7, 22), datetime(2026, 8, 7)
    return frame(
        [
            row(when=d1.replace(hour=12, minute=33, second=57), point=offset(site, 360, 170), accuracy=60.0, **common),
            row(when=d1.replace(hour=12, minute=38, second=11), point=site, accuracy=42.6, **common),
            row(when=d1.replace(hour=12, minute=38, second=56), point=site, accuracy=42.6, **common),
            row(when=d2.replace(hour=13, minute=14, second=13), point=offset(site, 3, -1), accuracy=31.6, **common),
            row(when=d2.replace(hour=13, minute=49, second=48), point=offset(site, 3, -1), accuracy=31.6, **common),
            row(when=d3.replace(hour=17, minute=57, second=33), point=offset(site, 26, 0), accuracy=33.7, **common),
            row(when=d3.replace(hour=17, minute=59, second=25), point=offset(site, 26, 0), accuracy=33.7, **common),
        ]
    )


# ---------------------------------------------------------------------------
# Example B: mostly no associated network, one off-site day, pin about 17 km away
# ---------------------------------------------------------------------------
B_SITE = offset(ORIGIN, 50_000, 0)
B_GOVT = offset(B_SITE, 9_500, -13_700)
B_APARTMENT = offset(B_SITE, -73_000, 47_000)
B_NAME = "Shkolla 9-vjeçare Gamma"
B_SCHOOL_BSSID = "e2:00:00:00:00:0b"


def example_b() -> pd.DataFrame:
    rows = []
    common = dict(school="SCH_B", device="DEV_B", govt=B_GOVT, school_name=B_NAME)
    start = datetime(2026, 6, 22)
    site_fix = (B_SITE, 135.6)
    for day in range(40):
        when = start + timedelta(days=day)
        if when.weekday() >= 5:
            continue
        if day == 22:
            for minute in (27, 33):
                rows.append(
                    row(when=when.replace(hour=12, minute=minute), point=B_APARTMENT,
                        accuracy=52.4, bssid="04:00:00:00:00:0b", ssid="APT_X", **common)
                )
            continue
        point, acc = site_fix
        if day % 7 == 0:
            point, acc = offset(B_SITE, 30, -8), 122.4
        rows.append(row(when=when.replace(hour=9, minute=0), point=point, accuracy=acc,
                        bssid=None, ssid=None, **common))
        rows.append(row(when=when.replace(hour=12, minute=10), point=point, accuracy=acc,
                        bssid=None, ssid=None, **common))
        if day % 3 == 0:
            rows.append(row(when=when.replace(hour=14, minute=5), point=point, accuracy=acc,
                            bssid=B_SCHOOL_BSSID, ssid="Shkolla Gamma", **common))
            rows.append(row(when=when.replace(hour=15, minute=40), point=point, accuracy=acc,
                            bssid=B_SCHOOL_BSSID, ssid="Shkolla Gamma", **common))
    return frame(rows)


# ---------------------------------------------------------------------------
# Example C: commuter laptop over a school holiday, with carried fixes
# ---------------------------------------------------------------------------
C_GOVT = offset(ORIGIN, -50_000, 0)
C_SCHOOL = offset(C_GOVT, 65, 300)
C_HOME = offset(C_SCHOOL, -1_620, 2_760)
C_NAME = "Shkolla 9-vjeçare Delta Epsilon"
C_SCHOOL_BSSID = "e8:00:00:00:00:0c"
C_HOME_BSSID = "50:00:00:00:00:0c"
C_PHONE_BSSID = "6a:00:00:00:00:0c"


def example_c() -> pd.DataFrame:
    rows = []
    common = dict(school="SCH_C", device="DEV_C", govt=C_GOVT, school_name=C_NAME)
    start = datetime(2026, 6, 1)
    for day in range(70):
        when = start + timedelta(days=day)
        in_term = day < 28
        home_fix = (offset(C_HOME, (day % 5) * 4, (day % 3) * 3), 18.0 + day % 6)
        school_fix = (offset(C_SCHOOL, (day % 4) * 3, -(day % 3) * 2), 15.0 + day % 3)

        if in_term and when.weekday() < 5:
            rows.append(row(when=when.replace(hour=0, minute=10), point=home_fix[0],
                            accuracy=home_fix[1], bssid=C_HOME_BSSID, ssid="HomeNet", **common))
            rows.append(row(when=when.replace(hour=8, minute=40), point=home_fix[0],
                            accuracy=home_fix[1], bssid=C_SCHOOL_BSSID,
                            ssid="Shkolla Delta Epsilon 2.4G", **common))
            rows.append(row(when=when.replace(hour=10, minute=5), point=school_fix[0],
                            accuracy=school_fix[1], bssid=C_SCHOOL_BSSID,
                            ssid="Shkolla Delta Epsilon 2.4G", **common))
            rows.append(row(when=when.replace(hour=11, minute=30), point=school_fix[0],
                            accuracy=school_fix[1], bssid=C_SCHOOL_BSSID,
                            ssid="Shkolla Delta Epsilon 2.4G", **common))
            rows.append(row(when=when.replace(hour=16, minute=20), point=school_fix[0],
                            accuracy=school_fix[1], bssid=C_HOME_BSSID, ssid="HomeNet", **common))
            rows.append(row(when=when.replace(hour=18, minute=45), point=offset(home_fix[0], 5, 5),
                            accuracy=home_fix[1], bssid=C_HOME_BSSID, ssid="HomeNet", **common))
        else:
            for hour in (10, 13, 17):
                rows.append(row(when=when.replace(hour=hour, minute=15),
                                point=offset(home_fix[0], hour % 4, 0), accuracy=home_fix[1],
                                bssid=C_HOME_BSSID, ssid="HomeNet", **common))
        if day in (8, 45):
            rows.append(row(when=when.replace(hour=16, minute=30), point=offset(C_HOME, 20, 0),
                            accuracy=20.0, bssid=C_PHONE_BSSID, ssid="iPhone", **common))
    return frame(rows)
