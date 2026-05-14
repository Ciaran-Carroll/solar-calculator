"""
PVGIS API integration
=====================

Wraps the EU's PVGIS service (re.jrc.ec.europa.eu) to fetch accurate solar
yield estimates based on satellite-derived irradiance data.

Why PVGIS?
- Free, no API key needed
- Calibrated against 15+ years of satellite data
- The de-facto standard tool for European solar engineers
- Much more accurate than our hardcoded baseline model

Why have a fallback?
- The API might be unreachable (no internet, firewall, downtime)
- Estimates without an internet connection are still useful
- We want our calculator to degrade gracefully, not crash

Documentation: https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


# PVGIS API endpoint (v5.2, the current stable version)
PVGIS_API_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"

# Default system loss percentage (covers wiring, inverter, soiling, mismatch, etc.)
# 14% is the PVGIS default for residential systems.
DEFAULT_SYSTEM_LOSS_PERCENT = 14

# Network timeout for API calls — a customer call shouldn't hang waiting for PVGIS
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass
class PVGISResult:
    """Result from a PVGIS API query."""
    annual_yield_kwh: float           # E_y from PVGIS — total annual energy
    yield_per_kwp_kwh: float          # specific yield in kWh per kWp per year
    monthly_yields_kwh: list[float]   # 12 values, one per month (Jan-Dec)
    api_used: bool                    # True if we got real data, False if fallback
    notes: str                        # any warnings or info


def _compass_to_pvgis_aspect(compass_bearing: float) -> float:
    """
    Convert compass bearing to PVGIS aspect convention.

    Compass bearing: 0 = North, 90 = East, 180 = South, 270 = West.
    PVGIS aspect: 0 = South, -90 = East, +90 = West, 180 or -180 = North.

    The conversion is a 180° shift then sign flip for east/west.
    """
    # Normalise to 0-360
    bearing = compass_bearing % 360
    # Shift so south (180) becomes 0
    aspect = bearing - 180
    # PVGIS uses -180 to +180, so wrap if needed
    if aspect > 180:
        aspect -= 360
    elif aspect <= -180:
        aspect += 360
    return aspect


def fetch_pvgis_yield(
    latitude: float,
    longitude: float,
    system_size_kwp: float,
    pitch_degrees: float,
    compass_bearing: float,
    loss_percent: float = DEFAULT_SYSTEM_LOSS_PERCENT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PVGISResult:
    """
    Fetch annual yield estimate from the PVGIS API.

    On any error (network down, API error, timeout, malformed response), raises
    PVGISError with a descriptive message. Caller should handle this and fall
    back to the hardcoded model if appropriate.

    Args:
        latitude: decimal degrees, positive = north
        longitude: decimal degrees, positive = east
        system_size_kwp: peak power in kWp
        pitch_degrees: roof pitch (0 = horizontal, 90 = vertical)
        compass_bearing: 0 = North, 90 = East, 180 = South, 270 = West
        loss_percent: total system loss %, default 14
        timeout: network timeout in seconds

    Returns:
        PVGISResult with yield data
    """
    aspect = _compass_to_pvgis_aspect(compass_bearing)

    # PVGIS doesn't accept aspect for systems mounted at 0° (it's irrelevant)
    # but does require pitch. Make sure pitch is at least slightly positive.
    pvgis_angle = max(0.1, pitch_degrees)

    params = {
        "lat": f"{latitude:.4f}",
        "lon": f"{longitude:.4f}",
        "peakpower": f"{system_size_kwp:.3f}",
        "loss": f"{loss_percent:.1f}",
        "angle": f"{pvgis_angle:.1f}",
        "aspect": f"{aspect:.1f}",
        "outputformat": "json",
    }

    query_string = urllib.parse.urlencode(params)
    url = f"{PVGIS_API_URL}?{query_string}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw_data = response.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise PVGISError(f"PVGIS API unreachable: {e}") from e
    except TimeoutError as e:
        raise PVGISError(f"PVGIS API timed out after {timeout}s") from e

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        raise PVGISError(f"PVGIS returned invalid JSON: {e}") from e

    return _parse_pvgis_response(data, system_size_kwp)


def _parse_pvgis_response(
    data: dict, system_size_kwp: float
) -> PVGISResult:
    """Extract yield numbers from the PVGIS JSON response."""
    try:
        outputs = data["outputs"]
        totals = outputs["totals"]["fixed"]
        annual_yield = float(totals["E_y"])
        monthly = outputs.get("monthly", {}).get("fixed", [])
        monthly_yields = [float(m["E_m"]) for m in monthly] if monthly else []
    except (KeyError, ValueError, TypeError) as e:
        raise PVGISError(f"Unexpected PVGIS response structure: {e}") from e

    yield_per_kwp = annual_yield / system_size_kwp if system_size_kwp > 0 else 0

    return PVGISResult(
        annual_yield_kwh=annual_yield,
        yield_per_kwp_kwh=yield_per_kwp,
        monthly_yields_kwh=monthly_yields,
        api_used=True,
        notes="Yield from PVGIS satellite-derived data",
    )


class PVGISError(Exception):
    """Raised when the PVGIS API call fails for any reason."""
    pass
