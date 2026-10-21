"""Our own scripts are linked with a version (the file's modified time) so a deploy is never hidden by the 4-hour browser /
Cloudflare cache of the old copy (a changed mexc_lines_chart.js once kept running the old script for people who had loaded
it earlier the same day)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))


def test_asset_url_carries_the_files_modified_time_and_unknown_files_fall_back():
    from frontend.frontend import _asset

    url = _asset("mexc_lines_chart.js")
    mtime = int((ROOT / "frontend" / "assets" / "mexc_lines_chart.js").stat().st_mtime)
    assert url == f"/mexc_lines_chart.js?v={mtime}"
    assert _asset("no_such_file.js") == "/no_such_file.js"


def test_every_custom_script_in_the_app_goes_through_asset():
    src = (ROOT / "frontend" / "frontend" / "frontend.py").read_text()
    bare = re.findall(r'script\(src="/[A-Za-z0-9_]+\.js"\)', src)
    assert bare == []  # no script is linked without a version
    assert '_asset("mexc_lines_chart.js")' in src and '_asset("instant_ui.js")' in src
