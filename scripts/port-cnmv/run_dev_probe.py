"""PORT-CNMV-1 — minimal DEV probe runner.

Prereg: evidence/port-cnmv/PORT-CNMV-1-PREREG.md

Runs ``history.reconstruct`` over the four DEV targets declared in
``split-v2/selection.json``, replaying ONLY ``split-v2/dev`` manifest
entries as EVIDENCE_IMPORT FetchResults. Zero network: the fetch
function reads captured bytes and returns MISSING for anything else —
there is no live-fetch path in this file.

Isolation is asserted mechanically before any byte is opened:

  * the manifest must live inside split-v2/dev/;
  * every manifest entry path must stay inside split-v2/dev/;
  * every fetch is checked against the dev entry set — a URL or path
    outside it can only produce MISSING, never a read.

Profile loading is explicit (prereg §6): this module imports
``regdelta.profiles.cnmv`` and calls ``use_profile("cnmv-circular")``.
``profiles/__init__.py`` is untouched, so default BdE behavior in the
rest of the tree is unchanged.

Usage:
    PYTHONPATH=src python -X utf8 scripts/port-cnmv/run_dev_probe.py \
        --output evidence/port-cnmv/port-cnmv-1/dev-run-<id>.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Profile selection must precede any runtime import: with two profiles
# registered, the first profile-backed lazy import (PEP 562 aliases in
# operations.py) calls active_profile() and fails closed without one.
import regdelta.profiles.cnmv  # noqa: E402,F401  (explicit registration)
from regdelta.profile import active_profile, use_profile  # noqa: E402

PROFILE_ID = "cnmv-circular"
use_profile(PROFILE_ID)

# Boundary adapter (journaled incompatibility #8): normalize legacy CNMV
# stylesheet class tokens to the canonical vocabulary at the parse
# boundary. Installed before the pipeline is imported so every
# boe_diario.parse_diario call inside frozen history.py resolves the
# wrapper. See cnmv_boundary.py header for the required justification.
import cnmv_boundary  # noqa: E402

cnmv_boundary.install()

from regdelta import db as dbm, history  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402
DEV_ROOT = ROOT / "evidence" / "port-cnmv" / "split-v2" / "dev"
SELECTION = ROOT / "evidence" / "port-cnmv" / "split-v2" / "selection.json"
HOLDOUT_PREFIX = "evidence/port-cnmv/split-v2/holdout"


def _isolation_assert(manifest_path: Path) -> dict[str, dict]:
    """Return dev ``by_url`` map; refuse anything outside split-v2/dev."""
    manifest_path = manifest_path.resolve()
    if DEV_ROOT.resolve() not in manifest_path.parents:
        raise SystemExit(
            f"ISOLATION_BROKEN: manifest outside split-v2/dev: "
            f"{manifest_path}")
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_url: dict[str, dict] = {}
    for name, entry in man["entries"].items():
        rel = entry.get("path", "")
        target = (ROOT / rel).resolve()
        if not rel.startswith("evidence/port-cnmv/split-v2/dev/") \
                or DEV_ROOT.resolve() not in target.parents:
            raise SystemExit(
                f"ISOLATION_BROKEN: manifest entry escapes dev root: "
                f"{name} -> {rel}")
        by_url[entry["url"]] = entry
    return by_url


def _evidence_fetch(by_url: dict[str, dict]):
    """Replay-only fetch: dev manifest bytes or MISSING. No network."""
    def fetch(url: str, accept: str) -> FetchResult:
        e = by_url.get(url)
        if e is None or "path" not in e:
            return FetchResult(url, None, None, None, "MISSING",
                               "url not in dev evidence",
                               via=EVIDENCE_IMPORT)
        path = (ROOT / e["path"]).resolve()
        if DEV_ROOT.resolve() not in path.parents:
            return FetchResult(url, None, None, None, "MISSING",
                               "path outside dev root refused",
                               via=EVIDENCE_IMPORT)
        return FetchResult(url, 200, "application/octet-stream",
                           path.read_bytes(), None, None,
                           via=EVIDENCE_IMPORT)
    return fetch


def _census(conn: sqlite3.Connection) -> dict:
    """DEV census counters straight from the run's own tables."""
    out: dict = {}
    rel_cols = ("relation_id", "kind", "operation_kind", "resolution",
                "resolution_notes", "locator_raw", "publication_date")
    out["relations"] = [dict(zip(rel_cols, r)) for r in conn.execute(
        "SELECT relation_id, kind, operation_kind, resolution,"
        " resolution_notes, locator_raw, publication_date"
        " FROM modification_relations")]
    out["resolution_counts"] = {
        r[0]: r[1] for r in conn.execute(
            "SELECT resolution, COUNT(*) FROM modification_relations"
            " GROUP BY resolution")}
    out["op_kind_counts"] = {
        r[0]: r[1] for r in conn.execute(
            "SELECT operation_kind, COUNT(*) FROM modification_relations"
            " GROUP BY operation_kind")}
    out["subjects"] = conn.execute(
        "SELECT COUNT(*) FROM subjects").fetchone()[0]
    out["subject_kinds"] = {
        r[0]: r[1] for r in conn.execute(
            "SELECT subject_kind, COUNT(*) FROM subjects"
            " GROUP BY subject_kind")}
    out["representations"] = conn.execute(
        "SELECT COUNT(*) FROM representations").fetchone()[0]
    out["applicability_clauses"] = conn.execute(
        "SELECT COUNT(*) FROM applicability_clauses").fetchone()[0]
    out["applicability_effects"] = conn.execute(
        "SELECT COUNT(*) FROM applicability_effects").fetchone()[0]
    out["anomalies_by_kind"] = {
        r[0]: r[1] for r in conn.execute(
            "SELECT kind, COUNT(*) FROM anomalies GROUP BY kind")}
    out["anomaly_details"] = [
        {"kind": k, "detail": d} for k, d in conn.execute(
            "SELECT kind, detail FROM anomalies")]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-manifest", type=Path,
                    default=DEV_ROOT / "manifest.json")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--run-id", default="dev-probe")
    ap.add_argument("--persist-dir", type=Path, default=None,
                    help="keep each target's data_dir (sqlite + raw "
                         "blobs) under DIR/<target>/ for the independent "
                         "evaluator instead of a tempdir")
    args = ap.parse_args()

    # --- mechanical base/isolation asserts (prereg steps 1–2) ---------
    head = subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True,
                            cwd=ROOT).stdout.strip()
    if branch != "port-cnmv-1":
        raise SystemExit(f"ISOLATION_BROKEN: branch {branch!r} "
                         f"!= port-cnmv-1")

    sel = json.loads(SELECTION.read_text(encoding="utf-8"))
    targets = list(sel["dev"])
    if len(targets) != 4:
        raise SystemExit(f"unexpected dev target count: {targets}")

    by_url = _isolation_assert(args.dev_manifest)
    fetch = _evidence_fetch(by_url)

    profile = active_profile()

    def _run_target(data_dir: Path, target: str) -> dict:
        conn = dbm.connect(data_dir / "regdelta.sqlite")
        try:
            try:
                report = history.reconstruct(conn, data_dir, target, fetch)
                conn.commit()
                return {"target": target, "report": report,
                        "census": _census(conn)}
            except Exception:
                return {"target": target, "error": traceback.format_exc()}
        finally:
            conn.close()

    results = []
    for target in targets:
        if args.persist_dir is not None:
            data_dir = args.persist_dir / target
            # a persisted dir must reflect THIS run only: leftover
            # sqlite/raw state would silently merge rows across runs
            # (journal #13)
            if data_dir.exists():
                shutil.rmtree(data_dir, ignore_errors=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            results.append(_run_target(data_dir, target))
            continue
        with tempfile.TemporaryDirectory(prefix="cnmv1-",
                                         ignore_cleanup_errors=True) as td:
            data_dir = Path(td) / target
            data_dir.mkdir()
            results.append(_run_target(data_dir, target))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "gate": "PORT-CNMV-1",
        "run_id": args.run_id,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "git_branch": branch,
        "src_tree": subprocess.run(
            ["git", "rev-parse", "HEAD:src/regdelta"],
            capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "boundary_adapter": "cnmv_boundary.parse_diario",
        "boundary_renames": dict(cnmv_boundary.renames_total),
        "dev_manifest": str(args.dev_manifest),
        "dev_entries": len(by_url),
        "python": sys.version,
        "via": EVIDENCE_IMPORT,
        "targets": results,
    }
    args.output.write_text(json.dumps(envelope, ensure_ascii=False,
                                      indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    for r in results:
        if "error" in r:
            print(f"{r['target']}: ERROR\n{r['error'][:2000]}")
        else:
            rep = r["report"]
            inv = rep.get("operation_inventory", {})
            print(f"{r['target']}: modifiers={len(rep.get('modifiers', []))}"
                  f" leaf_ops={inv.get('leaf_operations_parsed')}"
                  f" dispositions={inv.get('attribution_dispositions')}"
                  f" relations={rep.get('relations')}"
                  f" anomalies={rep.get('anomaly_count')}"
                  f" fetch_errors={len(rep.get('fetch_errors', []))}"
                  f" resolutions={r['census']['resolution_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
