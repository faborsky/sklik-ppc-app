#!/usr/bin/env python3
"""Sklik DRAK CLI — entrypoint.

Thin wrapper; the implementation lives in the `sklik` package:
  sklik/api.py            engine (auth, session, rate limiting, API calls, errors)
  sklik/formatting.py     CZK/haléře + JSON output helpers
  sklik/reports.py        two-step report helper
  sklik/images.py         image IO shared by combined ads and banners
  sklik/commands/*.py     one module per Sklik domain
  sklik/cli.py            argument parsing and dispatch
"""
from sklik.cli import main

if __name__ == "__main__":
    main()
