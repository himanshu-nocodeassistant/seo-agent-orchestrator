#!/usr/bin/env python3
"""
Backlinks pipeline.

Wraps agent.dataforseo.backlinks.backlinks.BacklinksAPI. Subcommands:
summary_live, backlinks_live, anchors_live, domain_pages_live,
referring_domains_live, referring_networks_live, domain_intersection_live,
competitors_live, bulk_ranks_live, bulk_referring_domains_live.

Usage:
    python scripts/pipelines/backlinks.py --help
    python scripts/pipelines/backlinks.py summary_live --task '{"target": "example.com"}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.backlinks.backlinks import BacklinksAPI
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(BacklinksAPI, "backlinks")
