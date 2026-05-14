"""
Solar Panel Calculator for Irish Domestic Roofs
================================================

A command-line tool that estimates how many solar PV panels can fit across
one or more roof faces, the resulting system size in kWp, the expected
annual energy yield (using PVGIS satellite data when available, falling back
to a calibrated model when offline), and the financial picture including
the SEAI grant.

Designed for first-pass desktop assessments of the kind a project engineer
at an Irish solar installer would do during an initial customer call,
before any site visit.

Author: Ciaran Carroll
Version: 0.3.0
Data sources verified: 2026-05
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pvgis import PVGISError, fetch_pvgis_yield


# =============================================================================
# CONSTANTS
# =============================================================================

# Panel defaults (modern monocrystalline domestic panel, 2026 market)
DEFAULT_PANEL_WIDTH_M = 1.10
DEFAULT_PANEL_HEIGHT_M = 1.70
DEFAULT_PANEL_WATTS = 400

# Installation defaults
DEFAULT_SETBACK_M = 0.40

# Solar yield baseline (offline fallback) — Source: PVGIS averages, 2026-05
IRISH_BASELINE_YIELD_KWH_PER_KWP = 900
OPTIMAL_PITCH_DEGREES = 35

# Default location for PVGIS lookup (centre of Ireland — used if no location given)
DEFAULT_LATITUDE = 53.4
DEFAULT_LONGITUDE = -7.9

# Financial figures (Source: SEAI, verified 2026-05)
SEAI_GRANT_FIRST_2KWP_PER_KWP = 700
SEAI_GRANT_NEXT_2KWP_PER_KWP = 200
SEAI_GRANT_CAP_KWP = 4
SEAI_GRANT_MAX_EUR = 1800

TYPICAL_COST_PER_KWP_EUR = 1500
TYPICAL_GRID_IMPORT_RATE_EUR_KWH = 0.30
TYPICAL_EXPORT_TARIFF_EUR_KWH = 0.20
SELF_CONSUMPTION_NO_BATTERY = 0.35
SELF_CONSUMPTION_WITH_BATTERY = 0.80


# =============================================================================
# ENUMS
# =============================================================================

class PanelArrangement(Enum):
    """How the panels are oriented relative to the roof."""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RoofFace:
    """A single face of a roof (one orientation, one pitch)."""
    name: str                  # human-readable label, e.g. "South face", "Front"
    width_m: float             # ridge-direction dimension (plan view)
    depth_m: float             # eave-to-ridge dimension (plan view)
    pitch_degrees: float
    orientation_deg: float     # compass bearing (180 = south)


@dataclass
class PanelSpec:
    """Specifications of the solar panel being installed."""
    width_m: float = DEFAULT_PANEL_WIDTH_M
    height_m: float = DEFAULT_PANEL_HEIGHT_M
    watts: int = DEFAULT_PANEL_WATTS


@dataclass
class ProjectInputs:
    """All inputs for a project: faces, panels, location, and options."""
    faces: list[RoofFace]
    panel: PanelSpec
    setback_m: float = DEFAULT_SETBACK_M
    has_battery: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    use_pvgis: bool = True


@dataclass
class FaceLayout:
    """Layout result for one face."""
    face_name: str
    sloped_width_m: float
    sloped_depth_m: float
    usable_width_m: float
    usable_depth_m: float
    portrait_panels: int
    landscape_panels: int
    chosen_arrangement: PanelArrangement
    panel_count: int
    system_size_kwp: float
    orientation_factor: float
    pitch_factor: float
    annual_yield_kwh: float


@dataclass
class ProjectResults:
    """Aggregated results across all faces, plus financials."""
    face_layouts: list[FaceLayout]
    total_panels: int
    total_system_size_kwp: float
    total_annual_yield_kwh: float
    yield_source: str            # "PVGIS" or "offline model"
    seai_grant_eur: float
    estimated_cost_eur: float
    net_cost_eur: float
    annual_savings_eur: float
    simple_payback_years: float


# =============================================================================
# GEOMETRY
# =============================================================================

def calculate_sloped_dimensions(
    width_m: float, depth_m: float, pitch_degrees: float
) -> tuple[float, float]:
    """Convert plan dimensions to sloped surface dimensions."""
    if pitch_degrees >= 80:
        raise ValueError(
            f"Pitch of {pitch_degrees}° is too steep for a roof"
        )
    if pitch_degrees < 0:
        raise ValueError(f"Pitch cannot be negative: {pitch_degrees}°")

    pitch_rad = math.radians(pitch_degrees)
    return width_m, depth_m / math.cos(pitch_rad)


def apply_setbacks(
    sloped_width: float, sloped_depth: float, setback_m: float
) -> tuple[float, float]:
    """Reduce dimensions by 2 × setback (one on each side)."""
    return (
        max(0.0, sloped_width - 2 * setback_m),
        max(0.0, sloped_depth - 2 * setback_m),
    )


# =============================================================================
# LAYOUT
# =============================================================================

def fit_panels(
    usable_width_m: float,
    usable_depth_m: float,
    panel_short_m: float,
    panel_long_m: float,
    arrangement: PanelArrangement,
) -> int:
    """Return panel count for a given arrangement on a usable area."""
    if arrangement == PanelArrangement.PORTRAIT:
        across, up_slope = panel_short_m, panel_long_m
    else:
        across, up_slope = panel_long_m, panel_short_m

    EPSILON = 1e-9
    columns = math.floor(usable_width_m / across + EPSILON) if across > 0 else 0
    rows = math.floor(usable_depth_m / up_slope + EPSILON) if up_slope > 0 else 0
    return max(0, columns * rows)


# =============================================================================
# YIELD MODELLING (offline fallback)
# =============================================================================

def orientation_factor(orientation_deg: float) -> float:
    """Yield factor based on compass bearing (1.0 = south, ~0.55 = north)."""
    bearing = orientation_deg % 360
    deviation = abs(bearing - 180)
    if deviation > 180:
        deviation = 360 - deviation
    deviation_rad = math.radians(deviation)
    return 0.55 + 0.45 * (math.cos(deviation_rad / 2) ** 2)


def pitch_factor(pitch_degrees: float) -> float:
    """Yield factor based on pitch (1.0 at 35°, dropping at extremes)."""
    deviation = abs(pitch_degrees - OPTIMAL_PITCH_DEGREES)
    factor = 1.0 - (deviation / 90) ** 2
    return max(0.5, factor)


def calculate_offline_yield(
    system_size_kwp: float, orientation_deg: float, pitch_degrees: float
) -> float:
    """Estimate yield using the hardcoded model (no internet required)."""
    o_factor = orientation_factor(orientation_deg)
    p_factor = pitch_factor(pitch_degrees)
    return (
        system_size_kwp * IRISH_BASELINE_YIELD_KWH_PER_KWP * o_factor * p_factor
    )


def get_yield_for_face(
    system_size_kwp: float,
    pitch_degrees: float,
    orientation_deg: float,
    latitude: Optional[float],
    longitude: Optional[float],
    use_pvgis: bool,
) -> tuple[float, str]:
    """
    Get the annual yield for a face, preferring PVGIS if available.

    Returns (yield_kwh, source) where source describes where the number came from.
    """
    if system_size_kwp == 0:
        return 0.0, "n/a (no panels)"

    if use_pvgis and latitude is not None and longitude is not None:
        try:
            result = fetch_pvgis_yield(
                latitude=latitude,
                longitude=longitude,
                system_size_kwp=system_size_kwp,
                pitch_degrees=pitch_degrees,
                compass_bearing=orientation_deg,
            )
            return result.annual_yield_kwh, "PVGIS"
        except PVGISError:
            # Fall through to offline model on any error
            pass

    yield_kwh = calculate_offline_yield(
        system_size_kwp, orientation_deg, pitch_degrees
    )
    return yield_kwh, "offline model"


# =============================================================================
# FINANCIALS
# =============================================================================

def calculate_seai_grant(system_size_kwp: float) -> float:
    """SEAI solar PV grant (2026 figures)."""
    capped = min(system_size_kwp, SEAI_GRANT_CAP_KWP)
    if capped <= 2:
        grant = capped * SEAI_GRANT_FIRST_2KWP_PER_KWP
    else:
        grant = (
            (2 * SEAI_GRANT_FIRST_2KWP_PER_KWP) +
            ((capped - 2) * SEAI_GRANT_NEXT_2KWP_PER_KWP)
        )
    return min(grant, SEAI_GRANT_MAX_EUR)


def estimate_annual_savings(annual_yield_kwh: float, has_battery: bool) -> float:
    """Annual benefit from self-consumption and grid export."""
    self_cons_ratio = (
        SELF_CONSUMPTION_WITH_BATTERY if has_battery
        else SELF_CONSUMPTION_NO_BATTERY
    )
    self_consumed = annual_yield_kwh * self_cons_ratio
    exported = annual_yield_kwh * (1 - self_cons_ratio)
    return (
        self_consumed * TYPICAL_GRID_IMPORT_RATE_EUR_KWH +
        exported * TYPICAL_EXPORT_TARIFF_EUR_KWH
    )


def calculate_payback_years(net_cost_eur: float, annual_savings_eur: float) -> float:
    """Simple payback (cost / annual savings)."""
    if annual_savings_eur <= 0:
        return float("inf")
    return net_cost_eur / annual_savings_eur


# =============================================================================
# FACE-LEVEL CALCULATION
# =============================================================================

def calculate_face_layout(
    face: RoofFace,
    panel: PanelSpec,
    setback_m: float,
    latitude: Optional[float],
    longitude: Optional[float],
    use_pvgis: bool,
) -> tuple[FaceLayout, str]:
    """
    Calculate everything for a single roof face.

    Returns the layout and the yield source ("PVGIS" or "offline model").
    """
    # Geometry
    sloped_w, sloped_d = calculate_sloped_dimensions(
        face.width_m, face.depth_m, face.pitch_degrees
    )
    usable_w, usable_d = apply_setbacks(sloped_w, sloped_d, setback_m)

    # Layout: try both arrangements
    portrait_count = fit_panels(
        usable_w, usable_d, panel.width_m, panel.height_m,
        PanelArrangement.PORTRAIT,
    )
    landscape_count = fit_panels(
        usable_w, usable_d, panel.width_m, panel.height_m,
        PanelArrangement.LANDSCAPE,
    )

    if portrait_count >= landscape_count:
        chosen = PanelArrangement.PORTRAIT
        panel_count = portrait_count
    else:
        chosen = PanelArrangement.LANDSCAPE
        panel_count = landscape_count

    # System size for this face
    system_size_kwp = (panel_count * panel.watts) / 1000

    # Yield (prefer PVGIS, fall back to offline)
    annual_yield, yield_source = get_yield_for_face(
        system_size_kwp,
        face.pitch_degrees,
        face.orientation_deg,
        latitude,
        longitude,
        use_pvgis,
    )

    # The orientation/pitch factors are useful diagnostics even when using PVGIS
    o_factor = orientation_factor(face.orientation_deg)
    p_factor = pitch_factor(face.pitch_degrees)

    return (
        FaceLayout(
            face_name=face.name,
            sloped_width_m=sloped_w,
            sloped_depth_m=sloped_d,
            usable_width_m=usable_w,
            usable_depth_m=usable_d,
            portrait_panels=portrait_count,
            landscape_panels=landscape_count,
            chosen_arrangement=chosen,
            panel_count=panel_count,
            system_size_kwp=system_size_kwp,
            orientation_factor=o_factor,
            pitch_factor=p_factor,
            annual_yield_kwh=annual_yield,
        ),
        yield_source,
    )


# =============================================================================
# PROJECT-LEVEL CALCULATION
# =============================================================================

def calculate_project(inputs: ProjectInputs) -> ProjectResults:
    """Run the full multi-face calculation pipeline."""
    face_layouts: list[FaceLayout] = []
    yield_sources: set[str] = set()

    for face in inputs.faces:
        layout, source = calculate_face_layout(
            face=face,
            panel=inputs.panel,
            setback_m=inputs.setback_m,
            latitude=inputs.latitude,
            longitude=inputs.longitude,
            use_pvgis=inputs.use_pvgis,
        )
        face_layouts.append(layout)
        yield_sources.add(source)

    # Aggregate
    total_panels = sum(f.panel_count for f in face_layouts)
    total_size_kwp = sum(f.system_size_kwp for f in face_layouts)
    total_yield = sum(f.annual_yield_kwh for f in face_layouts)

    # Yield source label — PVGIS preferred, mixed if it varied per face
    if yield_sources == {"PVGIS"}:
        yield_source_label = "PVGIS"
    elif yield_sources == {"offline model"}:
        yield_source_label = "offline model"
    else:
        yield_source_label = "mixed (PVGIS where available)"

    # Financials are calculated once on the total
    grant = calculate_seai_grant(total_size_kwp)
    estimated_cost = total_size_kwp * TYPICAL_COST_PER_KWP_EUR
    net_cost = max(0.0, estimated_cost - grant)
    annual_savings = estimate_annual_savings(total_yield, inputs.has_battery)
    payback = calculate_payback_years(net_cost, annual_savings)

    return ProjectResults(
        face_layouts=face_layouts,
        total_panels=total_panels,
        total_system_size_kwp=total_size_kwp,
        total_annual_yield_kwh=total_yield,
        yield_source=yield_source_label,
        seai_grant_eur=grant,
        estimated_cost_eur=estimated_cost,
        net_cost_eur=net_cost,
        annual_savings_eur=annual_savings,
        simple_payback_years=payback,
    )


# =============================================================================
# JSON EXPORT
# =============================================================================

def project_results_to_dict(
    inputs: ProjectInputs, results: ProjectResults
) -> dict:
    """Convert the full project (inputs + results) to a JSON-serialisable dict."""
    return {
        "inputs": {
            "faces": [
                {
                    "name": f.name,
                    "width_m": f.width_m,
                    "depth_m": f.depth_m,
                    "pitch_degrees": f.pitch_degrees,
                    "orientation_deg": f.orientation_deg,
                }
                for f in inputs.faces
            ],
            "panel": {
                "width_m": inputs.panel.width_m,
                "height_m": inputs.panel.height_m,
                "watts": inputs.panel.watts,
            },
            "setback_m": inputs.setback_m,
            "has_battery": inputs.has_battery,
            "latitude": inputs.latitude,
            "longitude": inputs.longitude,
        },
        "results": {
            "total_panels": results.total_panels,
            "total_system_size_kwp": round(results.total_system_size_kwp, 3),
            "total_annual_yield_kwh": round(results.total_annual_yield_kwh, 1),
            "yield_source": results.yield_source,
            "seai_grant_eur": round(results.seai_grant_eur, 0),
            "estimated_cost_eur": round(results.estimated_cost_eur, 0),
            "net_cost_eur": round(results.net_cost_eur, 0),
            "annual_savings_eur": round(results.annual_savings_eur, 0),
            "simple_payback_years": (
                round(results.simple_payback_years, 1)
                if results.simple_payback_years < 1000 else None
            ),
            "faces": [
                {
                    "name": f.face_name,
                    "panel_count": f.panel_count,
                    "system_size_kwp": round(f.system_size_kwp, 3),
                    "annual_yield_kwh": round(f.annual_yield_kwh, 1),
                    "arrangement": f.chosen_arrangement.value,
                }
                for f in results.face_layouts
            ],
        },
    }


def save_results_json(
    inputs: ProjectInputs, results: ProjectResults, path: str
) -> None:
    """Save the full project to a JSON file."""
    data = project_results_to_dict(inputs, results)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =============================================================================
# USER INTERFACE — input gathering
# =============================================================================

def prompt_float(
    prompt: str,
    default: Optional[float] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    while True:
        if default is not None:
            user_input = input(f"{prompt} [{default}]: ").strip()
            if user_input == "":
                return default
        else:
            user_input = input(f"{prompt}: ").strip()
        try:
            value = float(user_input)
            if minimum is not None and value < minimum:
                print(f"  Must be at least {minimum}. Try again.")
                continue
            if maximum is not None and value > maximum:
                print(f"  Must be at most {maximum}. Try again.")
                continue
            return value
        except ValueError:
            print("  That's not a valid number. Try again.")


def prompt_int(prompt: str, default: Optional[int] = None,
               minimum: Optional[int] = None) -> int:
    while True:
        if default is not None:
            user_input = input(f"{prompt} [{default}]: ").strip()
            if user_input == "":
                return default
        else:
            user_input = input(f"{prompt}: ").strip()
        try:
            value = int(user_input)
            if minimum is not None and value < minimum:
                print(f"  Must be at least {minimum}. Try again.")
                continue
            return value
        except ValueError:
            print("  That's not a valid integer. Try again.")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    default_str = "Y/n" if default else "y/N"
    while True:
        user_input = input(f"{prompt} [{default_str}]: ").strip().lower()
        if user_input == "":
            return default
        if user_input in ("y", "yes"):
            return True
        if user_input in ("n", "no"):
            return False
        print("  Please answer y or n.")


def prompt_string(prompt: str, default: Optional[str] = None) -> str:
    while True:
        if default is not None:
            user_input = input(f"{prompt} [{default}]: ").strip()
            if user_input == "":
                return default
            return user_input
        user_input = input(f"{prompt}: ").strip()
        if user_input != "":
            return user_input


def gather_face(face_number: int) -> RoofFace:
    """Prompt for a single roof face."""
    print()
    print(f"--- ROOF FACE {face_number} ---")
    name = prompt_string(
        f"Name for this face", default=f"Face {face_number}"
    )
    width_m = prompt_float(
        "Width along the ridge (metres, plan view)",
        minimum=1.0, maximum=50.0,
    )
    depth_m = prompt_float(
        "Depth eave-to-ridge (metres, plan view)",
        minimum=1.0, maximum=20.0,
    )
    pitch = prompt_float(
        "Pitch in degrees (typical Irish: 30-45)",
        default=35.0, minimum=0.0, maximum=70.0,
    )
    orientation = prompt_float(
        "Compass bearing of slope (180=south, 90=east, 270=west)",
        default=180.0, minimum=0.0, maximum=360.0,
    )
    return RoofFace(
        name=name,
        width_m=width_m,
        depth_m=depth_m,
        pitch_degrees=pitch,
        orientation_deg=orientation,
    )


def gather_inputs() -> ProjectInputs:
    """Collect all project inputs interactively."""
    print()
    print("=" * 70)
    print(" SOLAR PANEL CALCULATOR — Multi-Face Roof Assessment")
    print("=" * 70)
    print()

    num_faces = prompt_int(
        "How many roof faces will host panels (1, 2, ...)",
        default=1, minimum=1,
    )

    faces = [gather_face(i + 1) for i in range(num_faces)]

    print()
    print("--- PANEL SPECIFICATIONS ---")
    panel = PanelSpec(
        width_m=prompt_float(
            "Panel short edge in metres",
            default=DEFAULT_PANEL_WIDTH_M, minimum=0.5, maximum=2.0,
        ),
        height_m=prompt_float(
            "Panel long edge in metres",
            default=DEFAULT_PANEL_HEIGHT_M, minimum=0.5, maximum=2.5,
        ),
        watts=prompt_int(
            "Panel rated power in watts", default=DEFAULT_PANEL_WATTS,
        ),
    )

    print()
    print("--- INSTALLATION CONSTRAINTS ---")
    setback_m = prompt_float(
        "Edge setback in metres (typical 0.3-0.5)",
        default=DEFAULT_SETBACK_M, minimum=0.0, maximum=2.0,
    )

    print()
    print("--- LOCATION (for accurate yield via PVGIS) ---")
    use_location = prompt_yes_no(
        "Provide location for PVGIS lookup?", default=True
    )
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    use_pvgis = False
    if use_location:
        latitude = prompt_float(
            "Latitude (decimal degrees, e.g. 52.10 for Killarney)",
            minimum=-90, maximum=90,
        )
        longitude = prompt_float(
            "Longitude (decimal degrees, e.g. -9.36)",
            minimum=-180, maximum=180,
        )
        use_pvgis = True

    print()
    print("--- SYSTEM OPTIONS ---")
    has_battery = prompt_yes_no("Include a battery?", default=False)

    return ProjectInputs(
        faces=faces,
        panel=panel,
        setback_m=setback_m,
        has_battery=has_battery,
        latitude=latitude,
        longitude=longitude,
        use_pvgis=use_pvgis,
    )


# =============================================================================
# OUTPUT
# =============================================================================

def orientation_name(bearing: float) -> str:
    bearing = bearing % 360
    if bearing < 22.5 or bearing >= 337.5:
        return "North"
    elif bearing < 67.5:
        return "North-East"
    elif bearing < 112.5:
        return "East"
    elif bearing < 157.5:
        return "South-East"
    elif bearing < 202.5:
        return "South"
    elif bearing < 247.5:
        return "South-West"
    elif bearing < 292.5:
        return "West"
    return "North-West"


def present_face(face_input: RoofFace, layout: FaceLayout) -> None:
    """Print results for one face."""
    print()
    print(f"=== {layout.face_name} ===")
    print(f"  Orientation:       {orientation_name(face_input.orientation_deg)} "
          f"({face_input.orientation_deg:.0f}°)")
    print(f"  Pitch:             {face_input.pitch_degrees:.0f}°")
    print(f"  Plan area:         {face_input.width_m * face_input.depth_m:.1f} m²")
    print(f"  Sloped area:       "
          f"{layout.sloped_width_m * layout.sloped_depth_m:.1f} m²")
    print(f"  Usable area:       "
          f"{layout.usable_width_m * layout.usable_depth_m:.1f} m²")
    print(f"  Layout (best):     {layout.chosen_arrangement.value.upper()}, "
          f"{layout.panel_count} panels")
    print(f"  Portrait/landscape:{layout.portrait_panels} / "
          f"{layout.landscape_panels}")
    print(f"  System size:       {layout.system_size_kwp:.2f} kWp")
    print(f"  Annual yield:      {layout.annual_yield_kwh:,.0f} kWh")


def present_results(inputs: ProjectInputs, results: ProjectResults) -> None:
    """Print everything in a clear hierarchical format."""
    print()
    print("=" * 70)
    print(" RESULTS")
    print("=" * 70)

    # Per-face details
    for face_input, layout in zip(inputs.faces, results.face_layouts):
        present_face(face_input, layout)

    # Project totals
    print()
    print("=" * 70)
    print(" PROJECT TOTALS")
    print("=" * 70)
    print(f"  Total panels:          {results.total_panels}")
    print(f"  Total system size:     {results.total_system_size_kwp:.2f} kWp")
    print(f"  Total annual yield:    {results.total_annual_yield_kwh:,.0f} kWh")
    print(f"  Yield source:          {results.yield_source}")

    print()
    print("--- FINANCIALS (rough indicative figures only) ---")
    print(f"  Estimated cost:        €{results.estimated_cost_eur:,.0f}")
    print(f"  SEAI grant:            €{results.seai_grant_eur:,.0f}")
    print(f"  Net cost:              €{results.net_cost_eur:,.0f}")
    bat_note = "with battery" if inputs.has_battery else "no battery"
    print(f"  Annual savings:        €{results.annual_savings_eur:,.0f} ({bat_note})")
    if results.simple_payback_years < 100:
        print(f"  Simple payback:        {results.simple_payback_years:.1f} years")
    else:
        print(f"  Simple payback:        n/a (savings too low)")

    print()
    print("--- NOTES ---")
    print("  - First-pass desktop estimate, not a quotation.")
    print("  - Assumes no shading from chimneys, trees, or neighbouring buildings.")
    print("  - SEAI grant figures and tariffs verified 2026-05.")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    inputs = gather_inputs()
    results = calculate_project(inputs)
    present_results(inputs, results)

    # Optional: save to JSON
    print()
    if prompt_yes_no("Save results to a JSON file?", default=False):
        path = prompt_string("Output filename", default="solar_results.json")
        save_results_json(inputs, results, path)
        print(f"Saved to {path}")
    print()


if __name__ == "__main__":
    main()
