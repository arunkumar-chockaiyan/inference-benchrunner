#!/usr/bin/env python3
"""
Seed the engine model registry from data/seed_models.json.

Usage:
    python backend/seed_models.py                        # default: http://localhost:8080
    python backend/seed_models.py --base-url http://localhost:8080
    python backend/seed_models.py --engine ollama        # seed one engine only
    python backend/seed_models.py --dry-run              # print what would be seeded
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

FIXTURE_PATH = Path(__file__).parent.parent / "data" / "seed_models.json"

ENGINES = {"ollama", "llamacpp", "vllm", "sglang"}


def load_fixture(engine_filter: str | None) -> list[dict]:
    if not FIXTURE_PATH.exists():
        print(f"Fixture not found: {FIXTURE_PATH}", file=sys.stderr)
        sys.exit(1)

    raw: dict = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    models: list[dict] = [
        m for m in raw.get("models", [])
        if "engine" in m  # skip comment-only entries
    ]

    if engine_filter:
        if engine_filter not in ENGINES:
            print(f"Unknown engine {engine_filter!r}. Valid: {sorted(ENGINES)}", file=sys.stderr)
            sys.exit(1)
        models = [m for m in models if m["engine"] == engine_filter]

    return models


def seed(base_url: str, models: list[dict], dry_run: bool) -> None:
    added = skipped = failed = 0

    print(f"{'[DRY RUN] ' if dry_run else ''}Seeding {len(models)} model(s) → {base_url}\n")

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        for m in models:
            engine: str = m["engine"]
            model_id: str = m["model_id"]
            label = f"{engine:8s}  {model_id}"

            if dry_run:
                print(f"  [DRY]  {engine:8s}  {model_id}")
                continue

            payload = {
                "engine": engine,
                "model_id": model_id,
                "display_name": m.get("display_name", model_id),
                "notes": m.get("notes", ""),
            }

            try:
                resp = client.post(f"/api/engines/{engine}/models", json=payload)

                if resp.status_code == 201:
                    print(f"  +  {label}")
                    added += 1
                elif resp.status_code == 409:
                    print(f"  ~  {label}  (already exists, skipped)")
                    skipped += 1
                else:
                    detail = resp.json().get("detail", resp.text) if resp.content else resp.text
                    print(f"  !  {label}  HTTP {resp.status_code}: {detail}", file=sys.stderr)
                    failed += 1

            except httpx.ConnectError:
                print(
                    f"\nCannot reach {base_url}. Is the backend running?\n"
                    "  just backend   # or: uvicorn main:app --port 8080",
                    file=sys.stderr,
                )
                sys.exit(1)
            except httpx.RequestError as exc:
                print(f"  !  {label}  {exc}", file=sys.stderr)
                failed += 1

    print(f"\n{'─' * 48}")
    print(f"  Added:   {added}")
    print(f"  Skipped: {skipped}  (already existed)")
    print(f"  Failed:  {failed}")

    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed engine models from data/seed_models.json into the registry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        metavar="URL",
        help="Backend API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--engine",
        choices=sorted(ENGINES),
        default=None,
        metavar="ENGINE",
        help="Seed only this engine (ollama | llamacpp | vllm | sglang)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without making any API calls",
    )
    args = parser.parse_args()

    models = load_fixture(args.engine)

    if not models:
        print("No models to seed (fixture is empty or engine filter matched nothing).")
        sys.exit(0)

    seed(base_url=args.base_url, models=models, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
