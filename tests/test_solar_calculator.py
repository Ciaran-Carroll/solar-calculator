"""
Tests for the Solar Panel Calculator (multi-face version).

Run with:
    python -m unittest test_solar_calculator -v
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from unittest.mock import patch

from solar_calculator import (
    PanelArrangement,
    PanelSpec,
    ProjectInputs,
    RoofFace,
    apply_setbacks,
    calculate_face_layout,
    calculate_offline_yield,
    calculate_payback_years,
    calculate_project,
    calculate_seai_grant,
    calculate_sloped_dimensions,
    estimate_annual_savings,
    fit_panels,
    orientation_factor,
    pitch_factor,
    project_results_to_dict,
    save_results_json,
)


# =============================================================================
# GEOMETRY TESTS (unchanged from v0.2)
# =============================================================================

class TestSlopedDimensions(unittest.TestCase):
    def test_flat_roof_unchanged(self):
        w, d = calculate_sloped_dimensions(8.0, 5.0, 0.0)
        self.assertAlmostEqual(w, 8.0)
        self.assertAlmostEqual(d, 5.0)

    def test_thirty_five_degree_pitch(self):
        w, d = calculate_sloped_dimensions(8.0, 5.0, 35.0)
        self.assertAlmostEqual(d, 5.0 / math.cos(math.radians(35.0)), places=4)
        self.assertAlmostEqual(w, 8.0)

    def test_sixty_degree_pitch(self):
        _, d = calculate_sloped_dimensions(8.0, 5.0, 60.0)
        self.assertAlmostEqual(d, 10.0, places=2)

    def test_too_steep_raises_error(self):
        with self.assertRaises(ValueError):
            calculate_sloped_dimensions(8.0, 5.0, 80.0)

    def test_negative_pitch_rejected(self):
        with self.assertRaises(ValueError):
            calculate_sloped_dimensions(8.0, 5.0, -5.0)


class TestSetbacks(unittest.TestCase):
    def test_zero_setback_unchanged(self):
        w, d = apply_setbacks(8.0, 5.0, 0.0)
        self.assertAlmostEqual(w, 8.0)
        self.assertAlmostEqual(d, 5.0)

    def test_typical_setback(self):
        w, d = apply_setbacks(8.0, 5.0, 0.4)
        self.assertAlmostEqual(w, 7.2)
        self.assertAlmostEqual(d, 4.2)

    def test_setback_too_large_clamps_to_zero(self):
        w, d = apply_setbacks(0.5, 0.5, 1.0)
        self.assertEqual(w, 0.0)
        self.assertEqual(d, 0.0)


# =============================================================================
# LAYOUT TESTS
# =============================================================================

class TestPanelLayout(unittest.TestCase):
    def test_simple_portrait_fit(self):
        # 3 columns × 3 rows = 9 panels
        count = fit_panels(3.3, 5.1, 1.1, 1.7, PanelArrangement.PORTRAIT)
        self.assertEqual(count, 9)

    def test_simple_landscape_fit(self):
        count = fit_panels(3.3, 5.1, 1.1, 1.7, PanelArrangement.LANDSCAPE)
        self.assertEqual(count, 4)

    def test_tiny_area_zero_panels(self):
        self.assertEqual(
            fit_panels(0.5, 0.5, 1.1, 1.7, PanelArrangement.PORTRAIT), 0
        )

    def test_zero_area_zero_panels(self):
        self.assertEqual(
            fit_panels(0, 0, 1.1, 1.7, PanelArrangement.PORTRAIT), 0
        )


# =============================================================================
# YIELD TESTS
# =============================================================================

class TestOrientationFactor(unittest.TestCase):
    def test_south_is_optimal(self):
        self.assertAlmostEqual(orientation_factor(180), 1.0, places=3)

    def test_north_is_minimum(self):
        self.assertAlmostEqual(orientation_factor(0), 0.55, places=3)

    def test_symmetric_about_south(self):
        self.assertAlmostEqual(
            orientation_factor(90), orientation_factor(270), places=4
        )

    def test_normalisation(self):
        self.assertAlmostEqual(
            orientation_factor(540), orientation_factor(180), places=3
        )


class TestPitchFactor(unittest.TestCase):
    def test_optimal_pitch_is_one(self):
        self.assertAlmostEqual(pitch_factor(35), 1.0, places=3)

    def test_typical_irish_roof_near_optimal(self):
        for p in [30, 35, 40, 45]:
            self.assertGreater(pitch_factor(p), 0.97)

    def test_flat_roof_penalty(self):
        self.assertLess(pitch_factor(5), pitch_factor(35))


class TestOfflineYield(unittest.TestCase):
    def test_optimal_system(self):
        # 4 kWp at south + 35° = 4 × 900 × 1.0 × 1.0 = 3600 kWh/year
        y = calculate_offline_yield(4.0, 180, 35)
        self.assertAlmostEqual(y, 3600, delta=10)


# =============================================================================
# FINANCIAL TESTS (unchanged from v0.2)
# =============================================================================

class TestSEAIGrant(unittest.TestCase):
    def test_zero_size_zero_grant(self):
        self.assertEqual(calculate_seai_grant(0), 0)

    def test_one_kwp_700_euro(self):
        self.assertAlmostEqual(calculate_seai_grant(1.0), 700)

    def test_two_point_five_kwp(self):
        self.assertAlmostEqual(calculate_seai_grant(2.5), 1500)

    def test_four_kwp_max_grant(self):
        self.assertAlmostEqual(calculate_seai_grant(4.0), 1800)

    def test_six_kwp_capped(self):
        self.assertEqual(calculate_seai_grant(6.0), 1800)


class TestAnnualSavings(unittest.TestCase):
    def test_battery_increases_savings(self):
        no_bat = estimate_annual_savings(4000, has_battery=False)
        with_bat = estimate_annual_savings(4000, has_battery=True)
        self.assertGreater(with_bat, no_bat)


class TestPayback(unittest.TestCase):
    def test_simple_payback(self):
        self.assertAlmostEqual(calculate_payback_years(10000, 1000), 10.0)

    def test_zero_savings_returns_infinity(self):
        self.assertEqual(calculate_payback_years(10000, 0), float("inf"))


# =============================================================================
# SINGLE-FACE INTEGRATION TESTS
# =============================================================================

def _typical_face(**overrides) -> RoofFace:
    """A typical south-facing Kerry roof face."""
    defaults = dict(
        name="Test face",
        width_m=8.0,
        depth_m=5.0,
        pitch_degrees=35.0,
        orientation_deg=180.0,
    )
    defaults.update(overrides)
    return RoofFace(**defaults)


def _typical_inputs(faces=None, **overrides) -> ProjectInputs:
    """Typical project inputs (offline mode by default for deterministic tests)."""
    if faces is None:
        faces = [_typical_face()]
    defaults = dict(
        faces=faces,
        panel=PanelSpec(),
        setback_m=0.40,
        has_battery=False,
        latitude=None,
        longitude=None,
        use_pvgis=False,  # offline by default in tests
    )
    defaults.update(overrides)
    return ProjectInputs(**defaults)


class TestSingleFaceProject(unittest.TestCase):
    def test_typical_south_facing_house(self):
        inputs = _typical_inputs()
        results = calculate_project(inputs)

        self.assertEqual(len(results.face_layouts), 1)
        self.assertGreater(results.total_panels, 12)
        self.assertLess(results.total_panels, 30)
        self.assertGreater(results.total_system_size_kwp, 4)
        self.assertEqual(results.seai_grant_eur, 1800)
        self.assertEqual(results.yield_source, "offline model")

    def test_north_facing_yields_less(self):
        south = calculate_project(_typical_inputs(
            faces=[_typical_face(orientation_deg=180)],
        ))
        north = calculate_project(_typical_inputs(
            faces=[_typical_face(orientation_deg=0)],
        ))
        self.assertLess(
            north.total_annual_yield_kwh, south.total_annual_yield_kwh
        )


# =============================================================================
# MULTI-FACE INTEGRATION TESTS
# =============================================================================

class TestMultiFaceProject(unittest.TestCase):
    def test_east_west_split(self):
        """An east-west split system should produce sensible results."""
        east_face = _typical_face(name="East", orientation_deg=90)
        west_face = _typical_face(name="West", orientation_deg=270)
        inputs = _typical_inputs(faces=[east_face, west_face])
        results = calculate_project(inputs)

        # Should have two face layouts
        self.assertEqual(len(results.face_layouts), 2)

        # Combined panel count should equal sum of individual faces
        face_panel_sum = sum(f.panel_count for f in results.face_layouts)
        self.assertEqual(results.total_panels, face_panel_sum)

        # System size should be twice that of single face
        single = calculate_project(_typical_inputs(faces=[east_face]))
        self.assertAlmostEqual(
            results.total_system_size_kwp, 2 * single.total_system_size_kwp,
            places=3,
        )

    def test_two_faces_yield_more_than_one(self):
        single = calculate_project(_typical_inputs())
        double = calculate_project(_typical_inputs(faces=[
            _typical_face(name="Face 1"),
            _typical_face(name="Face 2"),
        ]))
        self.assertGreater(
            double.total_annual_yield_kwh, single.total_annual_yield_kwh
        )

    def test_grant_capped_across_faces(self):
        """Even a huge multi-face system caps grant at €1,800."""
        big_face = _typical_face(width_m=20, depth_m=10)
        inputs = _typical_inputs(faces=[big_face, big_face])
        results = calculate_project(inputs)
        self.assertEqual(results.seai_grant_eur, 1800)

    def test_mixed_orientations_each_face_calculated_separately(self):
        """Each face's yield should reflect its own orientation."""
        south = _typical_face(name="South", orientation_deg=180)
        east = _typical_face(name="East", orientation_deg=90)
        results = calculate_project(_typical_inputs(faces=[south, east]))

        south_yield = results.face_layouts[0].annual_yield_kwh
        east_yield = results.face_layouts[1].annual_yield_kwh
        # Same dimensions, different orientation -> different yields
        self.assertGreater(south_yield, east_yield)


# =============================================================================
# PVGIS INTEGRATION TESTS (mocked)
# =============================================================================

class TestPvgisIntegration(unittest.TestCase):
    @patch("solar_calculator.fetch_pvgis_yield")
    def test_pvgis_used_when_location_provided(self, mock_fetch):
        """When location is provided and use_pvgis=True, PVGIS is called."""
        from pvgis import PVGISResult
        mock_fetch.return_value = PVGISResult(
            annual_yield_kwh=4200.0,
            yield_per_kwp_kwh=525.0,
            monthly_yields_kwh=[],
            api_used=True,
            notes="mocked",
        )
        inputs = _typical_inputs(
            latitude=52.10, longitude=-9.36, use_pvgis=True,
        )
        results = calculate_project(inputs)
        self.assertEqual(results.yield_source, "PVGIS")
        self.assertAlmostEqual(results.total_annual_yield_kwh, 4200.0)

    @patch("solar_calculator.fetch_pvgis_yield")
    def test_falls_back_to_offline_on_pvgis_error(self, mock_fetch):
        """If PVGIS raises an error, fall back to the offline model silently."""
        from pvgis import PVGISError
        mock_fetch.side_effect = PVGISError("Network down")
        inputs = _typical_inputs(
            latitude=52.10, longitude=-9.36, use_pvgis=True,
        )
        results = calculate_project(inputs)
        self.assertEqual(results.yield_source, "offline model")
        # Should still have a sensible yield from the offline model
        self.assertGreater(results.total_annual_yield_kwh, 0)

    def test_offline_when_no_location(self):
        """Without location, always use offline model regardless of use_pvgis."""
        inputs = _typical_inputs(
            latitude=None, longitude=None, use_pvgis=True,
        )
        results = calculate_project(inputs)
        self.assertEqual(results.yield_source, "offline model")


# =============================================================================
# JSON EXPORT TESTS
# =============================================================================

class TestJsonExport(unittest.TestCase):
    def test_dict_structure(self):
        inputs = _typical_inputs()
        results = calculate_project(inputs)
        d = project_results_to_dict(inputs, results)

        # Top-level structure
        self.assertIn("inputs", d)
        self.assertIn("results", d)

        # Results contain expected fields
        self.assertIn("total_panels", d["results"])
        self.assertIn("total_system_size_kwp", d["results"])
        self.assertIn("seai_grant_eur", d["results"])
        self.assertIn("faces", d["results"])

    def test_dict_is_json_serialisable(self):
        inputs = _typical_inputs()
        results = calculate_project(inputs)
        d = project_results_to_dict(inputs, results)
        # Should not raise
        as_string = json.dumps(d)
        self.assertIsInstance(as_string, str)

    def test_save_to_file(self):
        inputs = _typical_inputs()
        results = calculate_project(inputs)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            tmp_path = f.name

        try:
            save_results_json(inputs, results, tmp_path)
            with open(tmp_path) as f:
                loaded = json.load(f)
            self.assertIn("results", loaded)
            self.assertEqual(
                loaded["results"]["total_panels"], results.total_panels
            )
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
