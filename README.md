# Solar Panel Calculator

A first-pass desktop assessment tool for Irish domestic solar PV projects. Estimates how many panels fit on a given roof, system size in kWp, expected annual yield, and the financial picture including the SEAI grant, MSS export tariff, and battery economics.

[![Live Demo](https://img.shields.io/badge/Streamlit-Live%20Demo-FF4B4B?logo=streamlit&logoColor=white)](https://your-deployment-url-here.streamlit.app)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-52%20passing-brightgreen)](#tests)

## Why this exists

When a homeowner phones a renewable energy installer to enquire about solar PV, the first task is a rough scoping call — *how many panels fit on the roof, what would the system size be, what would it generate, what would it cost, when does it pay back?* Doing this manually for every enquiry is slow. Doing it badly costs money — wrong system sizes lead to wrong quotes; wrong yield estimates lead to unhappy customers.

This tool is the back-of-the-envelope first pass. Five minutes of input gets you a defensible indicative estimate that a project engineer can use during the customer call itself, before any site visit.

## Features

- **Multi-face roofs** — model east-west splits, hipped roofs, dormers, or any combination of orientations and pitches
- **PVGIS integration** — pulls satellite-derived yield data from the EU's official PVGIS service when location is provided
- **Offline fallback** — calibrated mathematical model works without internet, for surveys in dead zones
- **SEAI grant calculation** — implements the 2026 tiered structure (€700/kWp first 2 kWp, €200/kWp next 2 kWp, capped at €1,800)
- **Battery economics** — models self-consumption ratio impact on annual savings
- **Layout optimisation** — compares portrait vs landscape panel arrangements automatically
- **JSON export** — saves all inputs and results for record-keeping or downstream tools
- **Both CLI and web UI** — command-line tool for batch use, Streamlit web app for interactive use

## Quick start

### Web UI (recommended)

```bash
git clone https://github.com/Ciaran-Carroll/solar-calculator.git
cd solar-calculator
pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

### Command-line

```bash
python src/solar_calculator.py
```

The CLI walks you through inputs interactively, then prints a summary report and offers to save results as JSON.

## How it works

The calculator runs through five layers:

1. **Geometry** — converts plan-view roof dimensions to actual sloped surface dimensions, applies edge setbacks for wind loading and access
2. **Layout** — fits panels in both portrait and landscape orientations, picks the better one
3. **Yield** — calls PVGIS API with the project's lat/lng/orientation/pitch (or falls back to a calibrated cosine-squared model based on Irish weather data)
4. **Financials** — calculates SEAI grant, estimated cost, net cost, annual savings (factoring in battery if present), and simple payback period
5. **Output** — presents results either via terminal text or web interface

### Yield modelling

When PVGIS is unavailable, yield is modelled as:

```
yield = system_size_kwp × baseline × orientation_factor × pitch_factor
```

Where:
- `baseline = 900 kWh/kWp/year` (Irish average at optimal orientation)
- `orientation_factor` uses a cosine-squared model centred on south
- `pitch_factor` uses a quadratic falloff from optimal (35°)

Reference values:
- South + 35°: factor 1.00 → ~900 kWh/kWp/year
- East/West + 35°: factor 0.78 → ~700 kWh/kWp/year
- North + 35°: factor 0.55 → ~495 kWh/kWp/year

When PVGIS is available, these factors are bypassed and the actual API response is used.

## Project structure

```
solar-calculator/
├── app.py
├── solar_calculator.py
├── pvgis.py
├── tests/
│   ├── test_solar_calculator.py
│   └── test_pvgis.py
```

## Tests

The project has 52 passing unit tests covering:

- Trigonometric edge cases (flat roofs, steep roofs, invalid pitch)
- Layout calculations (panel-fitting in both arrangements, floating-point precision)
- Yield modelling (orientation symmetry, pitch optimum, normalisation)
- SEAI grant tier logic (boundaries, caps, edge cases)
- Battery savings comparison
- Multi-face aggregation
- PVGIS API integration with mocked HTTP calls
- Compass-to-PVGIS angle conversion
- JSON serialisation round-trip

Run the test suite:

```bash
python -m unittest discover tests -v
```

## Design notes

A few things worth highlighting for anyone reading the code:

- **Module separation** — `pvgis.py` knows nothing about roofs; `solar_calculator.py` knows nothing about HTTP. Each module has a single, clear responsibility.
- **Mocked HTTP in tests** — the PVGIS tests use `unittest.mock.patch` so they're fast, deterministic, and don't depend on the real API being up. Tests should never make real network calls.
- **Graceful degradation** — if PVGIS is unreachable, the calculator falls back to the offline model silently and tells the user which source was used.
- **Data classes throughout** — `RoofFace`, `PanelSpec`, `ProjectInputs`, `ProjectResults` make the code self-documenting.
- **Floating-point epsilon** — `math.floor(3.3 / 1.1)` evaluates to 2, not 3, because floats are inexact. The fix is a small epsilon — caught by the test suite, not by manual review.

## Limitations

This is a first-pass estimating tool, not a replacement for professional design. It does not model:

- **Shading** from chimneys, dormers, trees, or neighbouring buildings (assumes a clear roof)
- **String design** — which panels go on which inverter MPPT
- **Detailed structural calculations** — assumes the roof can carry the load
- **Battery sizing optimisation** — uses a fixed self-consumption ratio
- **Hour-by-hour generation profiles** — only annual totals
- **Electricity price escalation or panel degradation** in payback calculations

For final design and quotation, always run the system through PVGIS directly, perform a site visit, and have a registered SEAI installer specify the system.

## Tech stack

- Python 3.10+ (uses modern type hint syntax)
- [Streamlit](https://streamlit.io) for the web UI
- Python standard library for everything else (`math`, `dataclasses`, `enum`, `json`, `unittest`, `urllib`)

No heavy dependencies. The whole project is intentionally minimal.

## License

MIT — see [LICENSE](LICENSE).

## Author

**Ciarán Carroll** — Project Engineer, Renewable Energy Centre (REC) Ireland.

[Portfolio](https://ciaran-carroll.github.io) · [GitHub](https://github.com/Ciaran-Carroll)
