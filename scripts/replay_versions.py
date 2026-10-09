"""
Replay two versions of the spatial methodology on the same ledger.

Each version runs in its own process against its own source tree: the
baseline from a temporary git worktree, the candidate from this checkout.
Both national audits are saved as Parquet, and a Markdown report is printed
with flag counts, the Track 1 flag transition matrix, device classes,
hotspot-tagged BSSIDs, and selected facilities.

Usage:
    python scripts/replay_versions.py --ledger data/spatial_confidence_ledger/ALB/ALB_ledger.csv
    python scripts/replay_versions.py --ledger ... --country ALB --cases ID1,ID2

Outputs go to `--out` (default `/tmp/gigameter-replay`), never into the
repository, because they contain facility and device identifiers.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# The v0.2.0 tag predates the canonical loader; this is the last v0.2 commit.
DEFAULT_BASELINE_REF = "66d9596"

AUDIT_COLUMNS = (
    "school_id_giga",
    "school_name",
    "location_verification_flag",
    "location_confidence_score",
    "location_confidence_level",
    "recommended_action",
    "govt_displacement_m",
    "hardware_health_score",
    "hardware_anomaly_tags",
    "anchor_resolved_by",
    "strategy_agreement",
    "entity_attribution_flag",
    "distinct_devices",
)


# ----------------------------------------------------------------------
# Worker: runs inside one source tree
# ----------------------------------------------------------------------
def run_worker(root: str, ledger: str, out: str, country: str) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    sys.path.insert(0, root)
    import pandas as pd

    from src.spatial_intelligence.facility_validator import FacilityValidator
    from src.utils.data_loader import TelemetryLoader

    df = TelemetryLoader().load(file_path=ledger)
    kwargs = {"telemetry_df": df}
    if country:
        kwargs.update(country_iso3=country, load_entity_pins=True)
    validator = FacilityValidator(**kwargs)
    audit = validator.run_national_facility_audit().copy()
    for column in AUDIT_COLUMNS:
        if column not in audit.columns:
            audit[column] = None
    audit = audit[list(AUDIT_COLUMNS)]
    audit["hardware_anomaly_tags"] = audit["hardware_anomaly_tags"].map(
        lambda tags: tags if isinstance(tags, str) else ", ".join(tags or []) or "NONE"
    )
    audit.to_parquet(out)

    profiler_df = validator.spatial_profiler.df
    report = validator.mobility_analyzer.generate_facility_mobility_report()
    report[["device_id", "mobility_class"]].to_parquet(Path(out).with_name(Path(out).stem + "_devices.parquet"))
    hotspot_bssids = profiler_df.loc[
        profiler_df["is_mobile_hotspot"].astype(bool), "detected_wifi_bssid"
    ].dropna()
    stats = {
        "rows": int(len(df)),
        "facilities": int(df["school_id_giga"].nunique()),
        "devices": int(df["device_id"].nunique()),
        "bssids": int(df["detected_wifi_bssid"].nunique()),
        "hotspot_rows": int(profiler_df["is_mobile_hotspot"].astype(bool).sum()),
        "hotspot_bssids": int(hotspot_bssids.nunique()),
        "device_classes": report["mobility_class"].value_counts().to_dict() if not report.empty else {},
        "pins_source": getattr(validator, "entity_pins_source", None),
    }
    Path(out).with_suffix(".json").write_text(json.dumps(stats))


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------
def _run_version(root: Path, ledger: Path, out: Path, country: str) -> dict:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--root", str(root),
        "--ledger", str(ledger),
        "--audit-out", str(out),
        "--country", country or "",
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return json.loads(out.with_suffix(".json").read_text())


def _md_table(frame) -> str:
    header = "| " + " | ".join(str(c) for c in [frame.index.name or ""] + list(frame.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in range(len(frame.columns) + 1)) + " |"
    rows = [
        "| " + " | ".join([str(idx)] + [str(v) for v in row]) + " |"
        for idx, row in zip(frame.index, frame.itertuples(index=False))
    ]
    return "\n".join([header, rule, *rows])


def report(base, cand, base_stats: dict, cand_stats: dict, cases: list, base_dev=None, cand_dev=None) -> str:
    import pandas as pd

    lines = []
    lines.append("## Ledger\n")
    lines.append(
        f"{cand_stats['rows']:,} rows, {cand_stats['facilities']} facilities, "
        f"{cand_stats['devices']} devices, {cand_stats['bssids']} BSSIDs. "
        f"Candidate Track 3 pins: {cand_stats['pins_source']}.\n"
    )

    lines.append("## Track 1 flag counts\n")
    counts = pd.DataFrame(
        {
            "baseline": base["location_verification_flag"].value_counts(),
            "candidate": cand["location_verification_flag"].value_counts(),
        }
    ).fillna(0).astype(int)
    counts.index.name = "flag"
    lines.append(_md_table(counts) + "\n")

    merged = base.merge(cand, on="school_id_giga", how="outer", suffixes=("_base", "_cand"), indicator=True)
    matrix = pd.crosstab(
        merged["location_verification_flag_base"].fillna("(absent)"),
        merged["location_verification_flag_cand"].fillna("(absent)"),
    )
    matrix.index.name = "baseline \\ candidate"
    lines.append("## Flag transition matrix\n")
    lines.append(_md_table(matrix) + "\n")

    both = merged[merged["_merge"] == "both"]
    same = int((both["location_verification_flag_base"] == both["location_verification_flag_cand"]).sum())
    dist = (both["govt_displacement_m_cand"] - both["govt_displacement_m_base"]).abs()
    lines.append(
        f"Same flag: {same} of {len(both)} facilities. Median change in distance to pin: "
        f"{dist.median():,.0f} m; changes over 1 km: {int((dist > 1000).sum())}.\n"
    )

    lines.append("## Device classes and hotspot tags\n")
    classes = pd.DataFrame(
        {"baseline": base_stats["device_classes"], "candidate": cand_stats["device_classes"]}
    ).fillna(0).astype(int)
    classes.index.name = "class"
    lines.append(_md_table(classes) + "\n")
    if base_dev is not None and cand_dev is not None:
        devices = base_dev.merge(cand_dev, on="device_id", how="outer", suffixes=("_base", "_cand"))
        device_matrix = pd.crosstab(
            devices["mobility_class_base"].fillna("(absent)"),
            devices["mobility_class_cand"].fillna("(absent)"),
        )
        device_matrix.index.name = "baseline \\ candidate"
        lines.append(_md_table(device_matrix) + "\n")
    lines.append(
        f"Hotspot-tagged rows: {base_stats['hotspot_rows']:,} -> {cand_stats['hotspot_rows']:,}. "
        f"Hotspot-tagged BSSIDs: {base_stats['hotspot_bssids']} -> {cand_stats['hotspot_bssids']}.\n"
    )

    if cand.get("recommended_action") is not None:
        lines.append("## Candidate actions and confidence\n")
        tiers = pd.crosstab(cand["location_verification_flag"], cand["location_confidence_level"])
        tiers.index.name = "flag"
        lines.append(_md_table(tiers) + "\n")
        actions = cand["recommended_action"].value_counts().to_frame("facilities")
        actions.index.name = "action"
        lines.append(_md_table(actions) + "\n")

    if cases:
        lines.append("## Cases\n")
        keep = [
            "location_verification_flag", "location_confidence_score", "govt_displacement_m",
            "hardware_anomaly_tags", "location_confidence_level", "recommended_action",
            "anchor_resolved_by", "entity_attribution_flag",
        ]
        for case in cases:
            row = merged[merged["school_id_giga"] == case]
            if row.empty:
                lines.append(f"`{case}`: not in either audit.\n")
                continue
            row = row.iloc[0]
            lines.append(f"### `{case}`\n")
            for column in keep:
                lines.append(
                    f"- {column}: {row.get(column + '_base')} -> {row.get(column + '_cand')}"
                )
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, help="CSV or Parquet ledger, pre-enriched.")
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF, help="Git ref of the baseline version.")
    parser.add_argument("--country", default="", help="ISO3; loads Delta Sharing pins for the candidate's Track 3.")
    parser.add_argument("--cases", default="", help="Comma-separated facility IDs to list in detail.")
    parser.add_argument("--out", default="/tmp/gigameter-replay", help="Output directory.")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--root", help=argparse.SUPPRESS)
    parser.add_argument("--audit-out", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        run_worker(args.root, args.ledger, args.audit_out, args.country)
        return

    import pandas as pd

    ledger = Path(args.ledger).resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gigameter-baseline-") as tmp:
        worktree = Path(tmp) / "baseline"
        subprocess.run(
            ["git", "worktree", "add", "--detach", "-q", str(worktree), args.baseline_ref],
            cwd=REPO,
            check=True,
        )
        try:
            base_stats = _run_version(worktree, ledger, out / "baseline_audit.parquet", "")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=REPO, check=True)
    cand_stats = _run_version(REPO, ledger, out / "candidate_audit.parquet", args.country)

    text = report(
        pd.read_parquet(out / "baseline_audit.parquet"),
        pd.read_parquet(out / "candidate_audit.parquet"),
        base_stats,
        cand_stats,
        [c for c in args.cases.split(",") if c],
        pd.read_parquet(out / "baseline_audit_devices.parquet"),
        pd.read_parquet(out / "candidate_audit_devices.parquet"),
    )
    (out / "report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
