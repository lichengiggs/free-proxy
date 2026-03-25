from __future__ import annotations

import json
from dataclasses import asdict
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_scripts.service import ProxyService


def run_smoke(provider: str, model: str) -> dict:
    service = ProxyService()
    models = service.list_models(provider)
    result = service.probe(provider, model)
    report = {
        'provider': provider,
        'models': models,
        'probe': asdict(result),
    }
    return report


def print_smoke(provider: str, model: str) -> int:
    report = run_smoke(provider, model)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['probe']['ok'] else 1
