"""
Unit tests for the three CEQ Intelligence Layer routers:
  - POST /v1/synthesis/from_query
  - POST /v1/printability/analyze
  - POST /v1/intent/route
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ceq_api.routers.printability import GeometryMetrics, PrintabilityRequest, _heuristic_score
from ceq_api.routers.intent import _classify_intent


# ══════════════════════════════════════════════════════════════════════════════
# 1. Printability Heuristic Scorer (pure unit tests — no DB/HTTP required)
# ══════════════════════════════════════════════════════════════════════════════


class TestPrintabilityHeuristics:

    def _req(self, **overrides) -> PrintabilityRequest:
        defaults = dict(material="PLA", layer_height_mm=0.2, support_enabled=False)
        defaults.update(overrides)
        return PrintabilityRequest(**defaults)

    def _metrics(self, **overrides) -> GeometryMetrics:
        defaults = dict(
            is_watertight=True,
            max_overhang_deg=30.0,
            min_wall_thickness_mm=1.6,
            bounding_box_mm=[50.0, 50.0, 30.0],
            volume_cm3=40.0,
            surface_area_cm2=100.0,
        )
        defaults.update(overrides)
        return GeometryMetrics(**defaults)

    def test_perfect_geometry_scores_high(self):
        report = _heuristic_score(self._req(), self._metrics())
        assert report.printability_score >= 0.90
        assert report.warp_risk == "low"

    def test_non_watertight_penalises_score(self):
        report = _heuristic_score(self._req(), self._metrics(is_watertight=False))
        assert report.printability_score <= 0.70
        assert any("watertight" in f.lower() for f in report.flags)

    def test_high_overhang_without_support_penalises(self):
        report = _heuristic_score(self._req(support_enabled=False), self._metrics(max_overhang_deg=70.0))
        assert report.support_required is True
        assert any("overhang" in f.lower() for f in report.flags)

    def test_high_overhang_with_support_ok(self):
        report = _heuristic_score(self._req(support_enabled=True), self._metrics(max_overhang_deg=70.0))
        # Support enabled: overhang penalty should not trigger
        assert report.printability_score >= 0.85

    def test_thin_wall_penalises(self):
        report = _heuristic_score(self._req(), self._metrics(min_wall_thickness_mm=0.3))
        assert any("wall" in f.lower() for f in report.flags)
        assert report.printability_score <= 0.80

    def test_failure_rate_inversely_proportional_to_score(self):
        good = _heuristic_score(self._req(), self._metrics())
        bad = _heuristic_score(self._req(), self._metrics(is_watertight=False, max_overhang_deg=80.0, min_wall_thickness_mm=0.2))
        assert good.failure_rate_pct < bad.failure_rate_pct

    def test_score_is_clamped_to_unit_interval(self):
        # Pile on every failure at once
        report = _heuristic_score(
            self._req(material="ABS"),
            self._metrics(
                is_watertight=False,
                max_overhang_deg=89.0,
                min_wall_thickness_mm=0.1,
                bounding_box_mm=[10.0, 10.0, 200.0],
                volume_cm3=5.0,
                surface_area_cm2=50.0,
            ),
        )
        assert 0.0 <= report.printability_score <= 1.0

    def test_print_time_estimated_when_volume_given(self):
        report = _heuristic_score(self._req(), self._metrics(volume_cm3=20.0))
        assert report.estimated_print_time_min == 80  # 20 × 4

    def test_no_volume_gives_no_print_time(self):
        report = _heuristic_score(self._req(), self._metrics(volume_cm3=0.0))
        assert report.estimated_print_time_min is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Intent Classifier (pure unit tests)
# ══════════════════════════════════════════════════════════════════════════════


class TestIntentClassifier:

    def test_parametric_cad_routes_to_yantra4d(self):
        platform, confidence, _ = _classify_intent("Generate a parametric gear in OpenSCAD")
        assert platform == "yantra4d"
        assert confidence >= 0.80

    def test_geospatial_routes_to_factlas(self):
        platform, confidence, _ = _classify_intent("Show me a map of urban terrain in Mexico City")
        assert platform == "factlas"
        assert confidence >= 0.80

    def test_file_search_routes_to_blueprint_harvester(self):
        platform, confidence, _ = _classify_intent("Find STL files for a bicycle bracket")
        assert platform == "blueprint-harvester"
        assert confidence >= 0.75

    def test_generate_routes_to_ceq(self):
        platform, confidence, _ = _classify_intent("Generate a 3D model using AI diffusion")
        assert platform == "ceq"
        assert confidence >= 0.75

    def test_unknown_query_falls_back_to_blueprint_harvester(self):
        platform, confidence, _ = _classify_intent("hello world")
        assert platform == "blueprint-harvester"

    def test_confidence_is_unit_interval(self):
        for query in ["search mesh", "parametric", "city map", "generate image", "???"]:
            _, confidence, _ = _classify_intent(query)
            assert 0.0 <= confidence <= 1.0
