"""Every public class, function, and plot method appears in the API reference."""

import importlib
import inspect
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
API_DOCS = REPO / "docs" / "api"

# Plot styling helpers used only by the dashboard are not part of the reference.
DOCUMENTED_MODULES = (
    "src.utils.data_loader",
    "src.utils.timezone_enricher",
    "src.spatial_intelligence.config",
    "src.spatial_intelligence.fix_events",
    "src.spatial_intelligence.geo",
    "src.spatial_intelligence.name_match",
    "src.spatial_intelligence.mobility_analyzer",
    "src.spatial_intelligence.spatial_profiler",
    "src.spatial_intelligence.facility_validator",
)


def _documented_identifiers() -> set:
    text = "\n".join(page.read_text() for page in API_DOCS.glob("*.md"))
    return set(re.findall(r"^::: ([\w.]+)", text, flags=re.MULTILINE))


def _public_symbols():
    for module_name in DOCUMENTED_MODULES:
        module = importlib.import_module(module_name)
        for name, obj in vars(module).items():
            if name.startswith("_") or getattr(obj, "__module__", None) != module_name:
                continue
            if inspect.isclass(obj) or inspect.isfunction(obj):
                yield f"{module_name}.{name}", obj


@pytest.mark.parametrize("identifier,obj", list(_public_symbols()), ids=lambda v: v if isinstance(v, str) else "")
def test_public_symbol_is_documented(identifier, obj):
    documented = _documented_identifiers()
    assert identifier in documented, f"{identifier} is missing from docs/api"
    if inspect.isclass(obj):
        for name in vars(obj):
            if name.startswith("plot_"):
                assert f"{identifier}.{name}" in documented, f"{identifier}.{name} is missing from docs/api"
