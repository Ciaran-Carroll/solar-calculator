"""
Streamlit Web UI for the Solar Panel Calculator
==================================================

A web-based version of the desktop calculator. Inputs in the sidebar,
results in the main panel. Multi-face support, PVGIS integration, JSON
download, and visualisations.

Run locally with:
    streamlit run app.py

Deploy free at:
    https://share.streamlit.io
"""

from __future__ import annotations

import json
import streamlit as st

from solar_calculator import (
    PanelSpec,
    ProjectInputs,
    RoofFace,
    calculate_project,
    project_results_to_dict,
    DEFAULT_PANEL_WIDTH_M,
    DEFAULT_PANEL_HEIGHT_M,
    DEFAULT_PANEL_WATTS,
    DEFAULT_SETBACK_M,
)


# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Solar Panel Calculator",
    page_icon="☀️",
    layout="wide",
)


# =============================================================================
# HEADER
# =============================================================================

st.title("☀️ Solar Panel Calculator")
st.caption(
    "First-pass desktop assessment for Irish domestic solar PV projects. "
    "Multi-face roofs supported. Yields from PVGIS satellite data when "
    "location is provided."
)


# =============================================================================
# SIDEBAR — global inputs
# =============================================================================

with st.sidebar:
    st.header("Project Settings")

    st.subheader("📍 Location")
    use_location = st.checkbox(
        "Use location for accurate PVGIS yield",
        value=True,
        help="When enabled, fetches calibrated yield estimates from the EU's "
             "PVGIS service. When disabled, uses the offline calibrated model.",
    )
    if use_location:
        col_lat, col_lon = st.columns(2)
        with col_lat:
            latitude = st.number_input(
                "Latitude", value=52.10, min_value=-90.0, max_value=90.0,
                step=0.01, format="%.4f",
            )
        with col_lon:
            longitude = st.number_input(
                "Longitude", value=-9.36, min_value=-180.0, max_value=180.0,
                step=0.01, format="%.4f",
            )
    else:
        latitude = None
        longitude = None

    st.subheader("☀️ Panel Specifications")
    panel_width = st.number_input(
        "Panel short edge (m)",
        value=DEFAULT_PANEL_WIDTH_M,
        min_value=0.5, max_value=2.0, step=0.01,
    )
    panel_height = st.number_input(
        "Panel long edge (m)",
        value=DEFAULT_PANEL_HEIGHT_M,
        min_value=0.5, max_value=2.5, step=0.01,
    )
    panel_watts = st.number_input(
        "Rated power (W)", value=DEFAULT_PANEL_WATTS,
        min_value=100, max_value=700, step=10,
    )

    st.subheader("🔧 Installation")
    setback_m = st.number_input(
        "Edge setback (m)", value=DEFAULT_SETBACK_M,
        min_value=0.0, max_value=2.0, step=0.05,
        help="Clearance from each roof edge. Standard 0.3-0.5m.",
    )

    st.subheader("🔋 System Options")
    has_battery = st.checkbox(
        "Include a battery",
        value=False,
        help="A battery raises the self-consumption ratio from ~35% to ~80%, "
             "increasing annual savings significantly.",
    )

    st.divider()
    st.caption(
        "Data sources verified 2026-05. Grant amounts and tariffs subject to "
        "change — verify on [seai.ie](https://www.seai.ie)."
    )


# =============================================================================
# MAIN AREA — roof faces and results
# =============================================================================

st.header("Roof Faces")

# Initialise faces in session state on first load
if "faces" not in st.session_state:
    st.session_state.faces = [
        {
            "name": "Main face",
            "width_m": 8.0,
            "depth_m": 5.0,
            "pitch_degrees": 35.0,
            "orientation_deg": 180.0,
        }
    ]

# Buttons to add/remove faces
col_add, col_remove, _ = st.columns([1, 1, 4])
with col_add:
    if st.button("➕ Add face"):
        face_count = len(st.session_state.faces) + 1
        st.session_state.faces.append({
            "name": f"Face {face_count}",
            "width_m": 8.0,
            "depth_m": 5.0,
            "pitch_degrees": 35.0,
            "orientation_deg": 90.0,  # default to east for the second face
        })
with col_remove:
    if (
        st.button("➖ Remove last face")
        and len(st.session_state.faces) > 1
    ):
        st.session_state.faces.pop()

# Render the face inputs as a tab per face
face_tabs = st.tabs([f["name"] for f in st.session_state.faces])
for i, tab in enumerate(face_tabs):
    with tab:
        face = st.session_state.faces[i]
        col1, col2 = st.columns(2)
        with col1:
            face["name"] = st.text_input(
                "Name", value=face["name"], key=f"name_{i}",
            )
            face["width_m"] = st.number_input(
                "Width along ridge (m, plan view)",
                value=face["width_m"],
                min_value=1.0, max_value=50.0, step=0.1,
                key=f"width_{i}",
            )
            face["depth_m"] = st.number_input(
                "Depth eave-to-ridge (m, plan view)",
                value=face["depth_m"],
                min_value=1.0, max_value=20.0, step=0.1,
                key=f"depth_{i}",
            )
        with col2:
            face["pitch_degrees"] = st.number_input(
                "Pitch (degrees)",
                value=face["pitch_degrees"],
                min_value=0.0, max_value=70.0, step=1.0,
                key=f"pitch_{i}",
            )
            face["orientation_deg"] = st.number_input(
                "Compass bearing (180=S, 90=E, 270=W)",
                value=face["orientation_deg"],
                min_value=0.0, max_value=360.0, step=5.0,
                key=f"orient_{i}",
            )
            # Show orientation as a compass name for clarity
            from solar_calculator import orientation_name
            st.caption(
                f"Orientation: **{orientation_name(face['orientation_deg'])}**"
            )


# =============================================================================
# CALCULATE
# =============================================================================

st.divider()

# Build inputs from session state and run the calculation
roof_faces = [
    RoofFace(
        name=f["name"],
        width_m=f["width_m"],
        depth_m=f["depth_m"],
        pitch_degrees=f["pitch_degrees"],
        orientation_deg=f["orientation_deg"],
    )
    for f in st.session_state.faces
]

inputs = ProjectInputs(
    faces=roof_faces,
    panel=PanelSpec(
        width_m=panel_width, height_m=panel_height, watts=int(panel_watts)
    ),
    setback_m=setback_m,
    has_battery=has_battery,
    latitude=latitude,
    longitude=longitude,
    use_pvgis=use_location,
)

# Calculation can take a moment when calling PVGIS (network round-trip)
with st.spinner("Calculating yield..."):
    try:
        results = calculate_project(inputs)
    except ValueError as e:
        st.error(f"Invalid input: {e}")
        st.stop()


# =============================================================================
# RESULTS
# =============================================================================

st.header("📊 Results")

# Top-line metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Total panels", f"{results.total_panels}",
)
col2.metric(
    "System size", f"{results.total_system_size_kwp:.2f} kWp",
)
col3.metric(
    "Annual yield", f"{results.total_annual_yield_kwh:,.0f} kWh",
)
col4.metric(
    "Annual savings", f"€{results.annual_savings_eur:,.0f}",
    delta="with battery" if has_battery else "no battery",
    delta_color="off",
)

# Yield source label
st.caption(f"Yield estimate based on **{results.yield_source}**.")

st.divider()

# Two columns: financials, per-face breakdown
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💰 Financials")
    st.markdown(
        f"""
| | |
|---|---|
| Estimated cost | €{results.estimated_cost_eur:,.0f} |
| SEAI grant | €{results.seai_grant_eur:,.0f} |
| **Net cost** | **€{results.net_cost_eur:,.0f}** |
| Annual savings | €{results.annual_savings_eur:,.0f} |
| Simple payback | {
    f"{results.simple_payback_years:.1f} years"
    if results.simple_payback_years < 100 else "n/a"
} |
"""
    )
    st.caption(
        "Estimates only. Cost assumes ~€1,500/kWp installed. Savings assume "
        "€0.30/kWh imports and €0.20/kWh export tariff."
    )

with col_right:
    st.subheader("🏠 Per-Face Breakdown")
    if len(results.face_layouts) == 1:
        st.caption("Single roof face.")
    face_data = [
        {
            "Face": f.face_name,
            "Panels": f.panel_count,
            "kWp": round(f.system_size_kwp, 2),
            "kWh/year": round(f.annual_yield_kwh, 0),
            "Layout": f.chosen_arrangement.value,
        }
        for f in results.face_layouts
    ]
    st.dataframe(face_data, hide_index=True, use_container_width=True)

# Yield bar chart per face (if multiple faces)
if len(results.face_layouts) > 1:
    st.subheader("⚡ Yield Comparison by Face")
    yield_by_face = {
        f.face_name: f.annual_yield_kwh for f in results.face_layouts
    }
    st.bar_chart(yield_by_face, y_label="Annual yield (kWh)")


# =============================================================================
# DOWNLOAD JSON
# =============================================================================

st.divider()
st.subheader("📥 Export")

results_dict = project_results_to_dict(inputs, results)
json_str = json.dumps(results_dict, indent=2)

st.download_button(
    label="Download results as JSON",
    data=json_str,
    file_name="solar_calculator_results.json",
    mime="application/json",
    help="Save the full project — inputs and outputs — for record-keeping.",
)

with st.expander("View raw JSON"):
    st.code(json_str, language="json")


# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption(
    "🛠️ Built by **Ciarán Carroll** — "
    "[GitHub](https://github.com/Ciaran-Carroll) · "
    "Based on PVGIS data ([source](https://re.jrc.ec.europa.eu/pvg_tools/en/)). "
    "Not a substitute for a professional site survey."
)
