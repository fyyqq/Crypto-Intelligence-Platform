"""Our own scripts are linked with a version (the file's modified time) so a deploy is never hidden by the 4-hour browser /
Cloudflare cache of the old copy (a changed mexc_lines_chart.js once kept running the old script for people who had loaded
it earlier the same day)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_asset_helper():
    """The helper's own code, run in isolation: importing frontend.frontend builds the whole Reflex app and leaks state into other tests."""
    path = ROOT / "frontend" / "frontend" / "frontend.py"
    src = path.read_text()
    start = src.index("def _asset(name: str) -> str:")
    end = src.index("\n\n\n", start)
    namespace = {"Path": Path, "__file__": str(path)}
    exec(src[start:end], namespace)
    return namespace["_asset"]


def test_asset_url_carries_the_files_modified_time_and_unknown_files_fall_back():
    asset = _load_asset_helper()
    mtime = int((ROOT / "frontend" / "assets" / "mexc_lines_chart.js").stat().st_mtime)
    assert asset("mexc_lines_chart.js") == f"/mexc_lines_chart.js?v={mtime}"
    assert asset("no_such_file.js") == "/no_such_file.js"


def test_every_custom_script_in_the_app_goes_through_asset():
    src = (ROOT / "frontend" / "frontend" / "frontend.py").read_text()
    bare = re.findall(r'script\(src="/[A-Za-z0-9_]+\.js"\)', src)
    assert bare == []  # no script is linked without a version
    assert '_asset("mexc_lines_chart.js")' in src and '_asset("instant_ui.js")' in src
