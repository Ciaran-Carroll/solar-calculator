"""
Tests for the PVGIS integration module.

Demonstrates the standard Python pattern for testing code that makes HTTP
calls: mock the network layer so tests are fast, deterministic, and don't
depend on external services.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch, MagicMock

from pvgis import (
    PVGISError,
    _compass_to_pvgis_aspect,
    _parse_pvgis_response,
    fetch_pvgis_yield,
)


# Sample PVGIS response shape — based on the actual API response format
SAMPLE_PVGIS_RESPONSE = {
    "outputs": {
        "monthly": {
            "fixed": [
                {"month": 1, "E_m": 120.5},
                {"month": 2, "E_m": 180.2},
                {"month": 3, "E_m": 290.8},
                {"month": 4, "E_m": 380.1},
                {"month": 5, "E_m": 450.3},
                {"month": 6, "E_m": 470.0},
                {"month": 7, "E_m": 460.5},
                {"month": 8, "E_m": 410.2},
                {"month": 9, "E_m": 320.8},
                {"month": 10, "E_m": 220.5},
                {"month": 11, "E_m": 140.0},
                {"month": 12, "E_m": 100.2},
            ]
        },
        "totals": {
            "fixed": {
                "E_y": 3543.1,
                "H(i)_y": 1234.5,
            }
        },
    },
    "inputs": {},
}


class TestCompassToPvgisAspect(unittest.TestCase):
    """Verify the compass-to-PVGIS angle conversion."""

    def test_south(self):
        """Compass 180° (south) -> PVGIS 0° (south)."""
        self.assertAlmostEqual(_compass_to_pvgis_aspect(180), 0)

    def test_east(self):
        """Compass 90° (east) -> PVGIS -90° (east)."""
        self.assertAlmostEqual(_compass_to_pvgis_aspect(90), -90)

    def test_west(self):
        """Compass 270° (west) -> PVGIS +90° (west)."""
        self.assertAlmostEqual(_compass_to_pvgis_aspect(270), 90)

    def test_north(self):
        """Compass 0° (north) -> PVGIS -180° (north)."""
        # 0 - 180 = -180 (wrapped to -180, not 180)
        result = _compass_to_pvgis_aspect(0)
        # Either -180 or 180 is acceptable; both represent due north in PVGIS
        self.assertTrue(result == -180 or result == 180)

    def test_southeast(self):
        """Compass 135° (south-east) -> PVGIS -45°."""
        self.assertAlmostEqual(_compass_to_pvgis_aspect(135), -45)

    def test_southwest(self):
        """Compass 225° (south-west) -> PVGIS +45°."""
        self.assertAlmostEqual(_compass_to_pvgis_aspect(225), 45)


class TestParsePvgisResponse(unittest.TestCase):
    """Verify we parse the JSON response correctly."""

    def test_normal_response(self):
        result = _parse_pvgis_response(SAMPLE_PVGIS_RESPONSE, 4.0)
        self.assertAlmostEqual(result.annual_yield_kwh, 3543.1)
        self.assertAlmostEqual(result.yield_per_kwp_kwh, 3543.1 / 4.0)
        self.assertEqual(len(result.monthly_yields_kwh), 12)
        self.assertTrue(result.api_used)

    def test_missing_totals_raises(self):
        bad_response = {"outputs": {}}
        with self.assertRaises(PVGISError):
            _parse_pvgis_response(bad_response, 4.0)

    def test_invalid_yield_raises(self):
        bad_response = {
            "outputs": {
                "totals": {"fixed": {"E_y": "not a number"}}
            }
        }
        with self.assertRaises(PVGISError):
            _parse_pvgis_response(bad_response, 4.0)


class TestFetchPvgisYield(unittest.TestCase):
    """Test the full fetch flow with mocked HTTP."""

    def _mock_urlopen(self, json_response: dict):
        """Build a mock response that returns the given JSON when read."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(json_response).encode("utf-8")
        # Support context manager protocol for `with urlopen(...)` syntax
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch("pvgis.urllib.request.urlopen")
    def test_successful_fetch(self, mock_urlopen):
        """A normal successful API call returns parsed yield data."""
        mock_urlopen.return_value = self._mock_urlopen(SAMPLE_PVGIS_RESPONSE)

        result = fetch_pvgis_yield(
            latitude=52.10,
            longitude=-9.36,
            system_size_kwp=4.0,
            pitch_degrees=35,
            compass_bearing=180,
        )

        self.assertAlmostEqual(result.annual_yield_kwh, 3543.1)
        self.assertTrue(result.api_used)
        # Verify the URL contains the right parameters
        called_url = mock_urlopen.call_args[0][0]
        self.assertIn("lat=52.1000", called_url)
        self.assertIn("lon=-9.3600", called_url)
        self.assertIn("peakpower=4.000", called_url)

    @patch("pvgis.urllib.request.urlopen")
    def test_network_error_raises_pvgis_error(self, mock_urlopen):
        """A network error should be wrapped in a PVGISError."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(PVGISError):
            fetch_pvgis_yield(
                latitude=52.10, longitude=-9.36,
                system_size_kwp=4.0, pitch_degrees=35, compass_bearing=180,
            )

    @patch("pvgis.urllib.request.urlopen")
    def test_invalid_json_raises_pvgis_error(self, mock_urlopen):
        """Invalid JSON should be wrapped in a PVGISError."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json {{{ "
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        with self.assertRaises(PVGISError):
            fetch_pvgis_yield(
                latitude=52.10, longitude=-9.36,
                system_size_kwp=4.0, pitch_degrees=35, compass_bearing=180,
            )


if __name__ == "__main__":
    unittest.main()
