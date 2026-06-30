import os
import sys
import json
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_PROJECT_ROOT, "src")

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

collect_ignore = [
    "collect_disease_progression.py",
    "debug_symptoms.py",
    "test_warmup_check.py",
]

_LANE_ORDER = ("fast", "core", "heavy", "benchmark", "research")
_MANIFEST_PATH = Path(__file__).with_name("test_manifest.json")
_VALID_LANES = frozenset(_LANE_ORDER)


def _load_test_manifest():
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    files = data.get("files")
    if not isinstance(files, dict):
        raise ValueError("tests/test_manifest.json must contain a top-level 'files' object")

    lane_map = {}
    bundle_map = {}
    for filename, meta in files.items():
        if not isinstance(meta, dict):
            raise ValueError(f"Manifest entry for {filename} must be an object")
        lane = meta.get("lane")
        bundle = meta.get("bundle")
        if lane not in _VALID_LANES:
            raise ValueError(f"Manifest lane for {filename} must be one of {_LANE_ORDER}, got {lane!r}")
        if not isinstance(bundle, str) or not bundle:
            raise ValueError(f"Manifest bundle for {filename} must be a non-empty string")
        lane_map[filename] = lane
        bundle_map[filename] = bundle

    return lane_map, bundle_map


CHANNEL_FILE_LANES, FILE_BUNDLES = _load_test_manifest()
_BUNDLE_NAMES = tuple(sorted(set(FILE_BUNDLES.values())))

_CHANNEL_SELECTION = {
    "fast": {"fast"},
    "fast-only": {"fast"},
    "core": {"fast", "core"},
    "core-only": {"core"},
    "heavy": {"fast", "core", "heavy"},
    "heavy-only": {"heavy"},
    "benchmark": {"benchmark"},
    "research": {"research"},
    "all": {"fast", "core", "heavy", "benchmark", "research"},
}


def _base_lane_for_item(item) -> str:
    filename = Path(str(item.fspath)).name
    try:
        return CHANNEL_FILE_LANES[filename]
    except KeyError as exc:
        raise KeyError(f"Collected test file missing lane mapping in test_manifest.json: {filename}") from exc


def _bundle_for_item(item) -> str:
    filename = Path(str(item.fspath)).name
    try:
        return FILE_BUNDLES[filename]
    except KeyError as exc:
        raise KeyError(f"Collected test file missing bundle mapping in test_manifest.json: {filename}") from exc


def _promote_lane(base_lane: str, target_lane: str) -> str:
    base_idx = _LANE_ORDER.index(base_lane)
    target_idx = _LANE_ORDER.index(target_lane)
    return _LANE_ORDER[max(base_idx, target_idx)]


def _effective_lane_for_item(item) -> str:
    lane = _base_lane_for_item(item)
    if item.get_closest_marker("slower"):
        return _promote_lane(lane, "benchmark")
    if item.get_closest_marker("slow"):
        return _promote_lane(lane, "heavy")
    return lane


def pytest_addoption(parser):
    parser.addoption(
        "--channel",
        action="store",
        default="all",
        choices=sorted(_CHANNEL_SELECTION),
        help=(
            "Run a named test channel without collecting the full suite into "
            "marker deselection noise. Supports cumulative lanes (fast, core, "
            "heavy, all) and exact split lanes (fast-only, core-only, "
            "heavy-only, benchmark, research)."
        ),
    )
    parser.addoption(
        "--bundle",
        action="append",
        default=[],
        choices=_BUNDLE_NAMES,
        help=(
            "Optionally narrow a run to one or more named test bundles such as "
            "core-runtime, benchmark-performance, core-solver, or "
            "benchmark-deterioration."
        ),
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "fast: fast daily development lane (formulae, invariants, lightweight contracts)",
    )
    config.addinivalue_line(
        "markers",
        "core: core regression lane layered on top of fast",
    )
    config.addinivalue_line(
        "markers",
        "heavy: heavier integration/validation lane layered on top of core",
    )
    config.addinivalue_line(
        "markers",
        "benchmark: long-running endurance/benchmark lane kept out of normal loops",
    )
    config.addinivalue_line(
        "markers",
        "research: ultra-heavy validation lane reserved for rare deep runs",
    )
    config.addinivalue_line(
        "markers",
        "slow: long-running tests excluded from quick development runs",
    )
    config.addinivalue_line(
        "markers",
        "slower: heavier endurance or validation-style tests",
    )


def pytest_collection_modifyitems(config, items):
    """Apply lane markers and optional channel-level filtering."""
    channel = config.getoption("--channel")
    bundle_filter = set(config.getoption("--bundle") or [])
    allowed_lanes = _CHANNEL_SELECTION[channel]
    selected = []

    for item in items:
        lane = _effective_lane_for_item(item)
        bundle = _bundle_for_item(item)
        item.add_marker(lane)
        if lane in allowed_lanes and (not bundle_filter or bundle in bundle_filter):
            selected.append(item)

    items[:] = selected
