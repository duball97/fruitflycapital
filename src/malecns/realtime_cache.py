"""Build the explicit official-data subgraph used by the live Brian2 adapter.

The full MaleCNS v1.0 weighted graph is the source of truth, but stepping all
211k annotated neurons and 151M weighted edges at browser cadence is not a
reasonable first interactive reference.  This builder retains the exact
weighted paths from the checked-in sensory populations to the annotated flight
readout populations within a documented three-hop boundary.

The connectivity Feather is scanned in batches.  No edge is reweighted,
normalized, synthesized, or connected across fly copies.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .loader import normalize_edges, normalize_neurons, read_feather
from .motor.flight_registry import flight_population_ids


ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
NEUROTRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"
CONNECTIVITY = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
MAPPING = Path("data/mappings/malecns_sensory_motor_ids.csv")


def _unique(values: Iterable[Any]) -> set[int]:
    return {int(value) for value in values}


def _mapping_source_ids(path: Path) -> dict[str, list[int]]:
    """Load exact sensory IDs from the generated official-data inventory."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    populations = {
        "visual_R8d": ["visual_R8d"],
        "olfactory_ORN_DA1": ["olfactory_ORN_DA1"],
        "mechanosensory_auditory_JO-B1_b": ["mechanosensory_auditory_JO-B1_b"],
    }
    result: dict[str, list[int]] = {}
    for key, names in populations.items():
        result[key] = sorted({int(row["bodyId"]) for row in rows if row.get("population") in names})
    return result


def _iter_connectivity(path: Path, batch_size: int = 1_000_000):
    """Yield NumPy arrays for the three official weighted edge columns."""
    try:
        import pyarrow.feather as feather
    except ImportError as exc:  # pragma: no cover - dependency environment
        raise ImportError("Install pyarrow to build the MaleCNS realtime cache") from exc
    table = feather.read_table(path, columns=["body_pre", "body_post", "weight"], memory_map=True)
    for batch in table.to_batches(max_chunksize=batch_size):
        yield (
            np.asarray(batch.column("body_pre")),
            np.asarray(batch.column("body_post")),
            np.asarray(batch.column("weight")),
        )
    del table


def _collect_reverse_layers(
    connectivity_path: Path,
    target_ids: set[int],
    *,
    batch_size: int,
) -> tuple[set[int], set[int]]:
    """Find the two reverse layers that can reach the output population."""
    target_array = np.asarray(sorted(target_ids), dtype=np.int64)
    layer2: set[int] = set()
    for pre, post, _ in _iter_connectivity(connectivity_path, batch_size):
        mask = np.isin(post, target_array)
        layer2.update(int(value) for value in pre[mask])
    print(f"reverse layer 2: {len(layer2):,} neurons", flush=True)

    layer2_array = np.asarray(sorted(layer2), dtype=np.int64)
    layer1: set[int] = set()
    for pre, post, _ in _iter_connectivity(connectivity_path, batch_size):
        mask = np.isin(post, layer2_array)
        layer1.update(int(value) for value in pre[mask])
    print(f"reverse layer 1: {len(layer1):,} neurons", flush=True)
    return layer1, layer2


def _collect_path_edges(
    connectivity_path: Path,
    source_ids: set[int],
    layer1_all: set[int],
    layer2_all: set[int],
    target_ids: set[int],
    *,
    batch_size: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Copy exact source/layer/layer/target rows from the official graph."""
    source_array = np.asarray(sorted(source_ids), dtype=np.int64)
    layer1_array = np.asarray(sorted(layer1_all), dtype=np.int64)
    layer2_array = np.asarray(sorted(layer2_all), dtype=np.int64)
    target_array = np.asarray(sorted(target_ids), dtype=np.int64)
    # First narrow the reverse candidate layer to nodes actually reached by a
    # sensory source.  Keeping ``layer1_all`` here would retain millions of
    # unrelated intermediate edges and would not be the documented source-
    # reachable path algorithm.
    first_parts: list[pd.DataFrame] = []
    for pre, post, weight in _iter_connectivity(connectivity_path, batch_size):
        first = np.isin(pre, source_array) & np.isin(post, layer1_array)
        if first.any():
            first_parts.append(pd.DataFrame({
                "source_body_id": pre[first],
                "target_body_id": post[first],
                "synapse_weight": weight[first],
            }))
    first_edges = pd.concat(first_parts, ignore_index=True) if first_parts else pd.DataFrame(
        columns=["source_body_id", "target_body_id", "synapse_weight"]
    )
    layer1 = _unique(first_edges["target_body_id"])
    print(f"forward layer 1: {len(layer1):,} neurons", flush=True)

    # Now narrow the second layer to nodes reached from those actual layer-1
    # nodes, then retain only their edges into the reverse-reachable layer.
    layer1_source_array = np.asarray(sorted(layer1), dtype=np.int64)
    second_parts: list[pd.DataFrame] = []
    for pre, post, weight in _iter_connectivity(connectivity_path, batch_size):
        second = np.isin(pre, layer1_source_array) & np.isin(post, layer2_array)
        if second.any():
            second_parts.append(pd.DataFrame({
                "source_body_id": pre[second],
                "target_body_id": post[second],
                "synapse_weight": weight[second],
            }))
    second_edges = pd.concat(second_parts, ignore_index=True) if second_parts else pd.DataFrame(
        columns=["source_body_id", "target_body_id", "synapse_weight"]
    )
    layer2 = _unique(second_edges["target_body_id"])
    print(f"forward layer 2: {len(layer2):,} neurons", flush=True)

    # Finally, retain only layer-2 edges that terminate at the exact flight
    # output population. Each row still carries its original official weight.
    layer2_source_array = np.asarray(sorted(layer2), dtype=np.int64)
    third_parts: list[pd.DataFrame] = []
    for pre, post, weight in _iter_connectivity(connectivity_path, batch_size):
        third = np.isin(pre, layer2_source_array) & np.isin(post, target_array)
        if third.any():
            third_parts.append(pd.DataFrame({
                "source_body_id": pre[third],
                "target_body_id": post[third],
                "synapse_weight": weight[third],
            }))
    third_edges = pd.concat(third_parts, ignore_index=True) if third_parts else pd.DataFrame(
        columns=["source_body_id", "target_body_id", "synapse_weight"]
    )
    edges = pd.concat([first_edges, second_edges, third_edges], ignore_index=True)
    # The source file has one weighted row per body pair. This also makes the
    # path union deterministic if a boundary pair is encountered in two
    # retained path categories.
    edges = edges.drop_duplicates(subset=["source_body_id", "target_body_id"], keep="first")
    return edges, {
        "source_to_layer1": int(len(first_edges)),
        "layer1_to_layer2": int(len(second_edges)),
        "layer2_to_target": int(len(third_edges)),
    }


def _official_path(data_dir: Path, filename: str) -> Path:
    path = data_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing official MaleCNS file: {path}")
    return path


def build_cache(
    data_dir: str | Path = "data/raw",
    output_dir: str | Path = "data/runtime/malecns-realtime-3hop",
    *,
    mapping_path: str | Path = MAPPING,
    batch_size: int = 1_000_000,
) -> dict[str, Any]:
    data_root = Path(data_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    annotations_path = _official_path(data_root, ANNOTATIONS)
    nt_path = data_root / NEUROTRANSMITTERS
    connectivity_path = _official_path(data_root, CONNECTIVITY)
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        raise FileNotFoundError(f"Missing official sensory inventory mapping: {mapping_file}")

    annotations = read_feather(annotations_path)
    normalized_annotations = normalize_neurons(annotations)
    source_populations = _mapping_source_ids(mapping_file)
    source_ids = _unique(value for values in source_populations.values() for value in values)
    target_populations = flight_population_ids(normalized_annotations)
    target_ids = _unique(value for values in target_populations.values() for value in values)
    if not source_ids:
        raise ValueError("No exact sensory source IDs were found in the mapping inventory")
    if not target_ids:
        raise ValueError("No exact flight output IDs were found in MaleCNS annotations")
    print(f"sources: {len(source_ids):,} exact sensory neurons", flush=True)
    print(f"targets: {len(target_ids):,} exact annotated flight neurons", flush=True)

    layer1_all, layer2_all = _collect_reverse_layers(connectivity_path, target_ids, batch_size=batch_size)
    edge_frame, path_counts = _collect_path_edges(
        connectivity_path,
        source_ids,
        layer1_all,
        layer2_all,
        target_ids,
        batch_size=batch_size,
    )
    node_ids = source_ids | target_ids | _unique(edge_frame["source_body_id"]) | _unique(edge_frame["target_body_id"])
    node_ids_array = np.asarray(sorted(node_ids), dtype=np.int64)
    sub_annotations = annotations[annotations["bodyId"].isin(node_ids_array)].copy().reset_index(drop=True)

    nt = None
    if nt_path.exists():
        nt = read_feather(nt_path)
        nt_body_column = "body" if "body" in nt.columns else "body_id"
        nt = nt[nt[nt_body_column].isin(node_ids_array)].copy().reset_index(drop=True)
    neurons = normalize_neurons(sub_annotations, nt)
    edges = normalize_edges(edge_frame)
    neurons.dataframe.to_feather(output_root / "neurons.feather")
    edges.dataframe.to_feather(output_root / "edges.feather")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "graph": "official MaleCNS v1.0 weighted Feather",
        "source_data": {
            "annotations": str(annotations_path),
            "neurotransmitters": str(nt_path) if nt_path.exists() else None,
            "connectivity": str(connectivity_path),
        },
        "cache_is_analysis_boundary": True,
        "path_hops": 3,
        "source_populations": source_populations,
        "target_populations": target_populations,
        "source_ids": sorted(source_ids),
        "target_ids": sorted(target_ids),
        "reverse_layer1_count": len(layer1_all),
        "reverse_layer2_count": len(layer2_all),
        "node_count": len(neurons.dataframe),
        "edge_count": len(edges.dataframe),
        "path_edge_counts_before_pair_deduplication": path_counts,
        "raw_weight": float(edges.dataframe["synapse_weight"].sum()),
        "unknown_sign_default": "exclude",
        "batch_size": batch_size,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("node_count", "edge_count", "raw_weight")}, indent=2), flush=True)
    del annotations, normalized_annotations, nt, neurons, edges, edge_frame
    gc.collect()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/runtime/malecns-realtime-3hop"))
    parser.add_argument("--mapping", type=Path, default=MAPPING)
    parser.add_argument("--batch-size", type=int, default=1_000_000)
    args = parser.parse_args()
    build_cache(args.data_dir, args.output_dir, mapping_path=args.mapping, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
