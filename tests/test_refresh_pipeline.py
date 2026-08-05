"""Tests for the DataForSEO refresh scheduler. All clients are mocked —
no network calls, no billing."""

import json
import sys
from datetime import date
from unittest.mock import MagicMock

import scripts.pipelines.refresh as refresh_module


def test_refresh_runs_pipelines_and_writes_rollups(tmp_path, monkeypatch, capsys):
    config = tmp_path / "refresh.tasks.json"
    config.write_text(json.dumps({
        "serp": [{"keyword": "no-code", "location_code": 2840}],
        "keyword_volume": [{"keywords": ["no-code"], "location_code": 2840}],
    }))

    fake_serp = MagicMock()
    fake_serp.search.return_value = [{"keyword": "no-code", "rank_absolute": 3}]
    fake_serp.total_cost = 0.01

    fake_kw = MagicMock()
    fake_kw.search_volume.return_value = [{"keywords": ["no-code"], "search_volume": 100}]
    fake_kw.total_cost = 0.02

    compiled = tmp_path / "compiled"
    monkeypatch.setattr(refresh_module, "GoogleOrganicSERP", lambda: fake_serp)
    monkeypatch.setattr(refresh_module, "GoogleAdsKeywords", lambda: fake_kw)
    monkeypatch.setattr(refresh_module, "COMPILED_DIR", compiled)
    monkeypatch.setattr(sys, "argv", ["refresh.py", "--config", str(config)])

    refresh_module.main()

    serp_path = compiled / f"serp-google-organic-search-{date.today()}.json"
    kw_path = compiled / f"keywords-google-ads-search-volume-{date.today()}.json"
    assert serp_path.exists()
    assert kw_path.exists()
    assert json.loads(serp_path.read_text()) == fake_serp.search.return_value
    out = capsys.readouterr().out
    assert "DataForSEO API cost this run: $0.0300" in out


def test_refresh_with_empty_sections_does_nothing(tmp_path, monkeypatch, capsys):
    config = tmp_path / "refresh.tasks.json"
    config.write_text(json.dumps({"serp": [], "keyword_volume": []}))
    compiled = tmp_path / "compiled"
    monkeypatch.setattr(refresh_module, "GoogleOrganicSERP", MagicMock)
    monkeypatch.setattr(refresh_module, "GoogleAdsKeywords", MagicMock)
    monkeypatch.setattr(refresh_module, "COMPILED_DIR", compiled)
    monkeypatch.setattr(sys, "argv", ["refresh.py", "--config", str(config)])

    refresh_module.main()

    assert not compiled.exists()
    assert "cost this run: $0.0000" in capsys.readouterr().out
