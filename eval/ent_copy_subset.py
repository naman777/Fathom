"""Copy an existing enterprise index into a reproducible demo subset, without re-embedding.

    python -m eval.ent_copy_subset --source enterprise_full --target enterprise_demo_25 --per-mille 250

Every benchmark gold document is retained. Remaining documents use ent_subset's stable hash sample.
Writes are acknowledged before checkpointing; replaying an interrupted document batch is idempotent.
The source collection is read-only. This command never deletes or replaces a collection.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import grpc, models
from qdrant_client.conversions.conversion import RestToGrpc

from core import config
from enterprise import data, store
from eval import ent_subset


def selected_ids(per_mille: int) -> list[str]:
    if not 1 <= per_mille <= 1000:
        raise ValueError("per-mille must be between 1 and 1000")
    gold = ent_subset.gold_ids()
    return sorted({d["doc_id"] for d in data.iter_documents(columns=["doc_id"])
                   if d["doc_id"] in gold or ent_subset.in_sample(d["doc_id"], per_mille)})


def native_point(record):
    """Preserve named dense and sparse vectors without a float-by-float REST/Pydantic round trip."""
    if not record.vectors.HasField("vectors"):
        raise ValueError("Expected named enterprise vectors")
    vectors = {name: grpc.Vector(**{field.name: value for field, value in vector.ListFields()})
               for name, vector in record.vectors.vectors.vectors.items()}
    return grpc.PointStruct(id=record.id, payload=record.payload,
                            vectors=grpc.Vectors(vectors=grpc.NamedVectors(vectors=vectors)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--per-mille", type=int, default=250)
    ap.add_argument("--docs-per-batch", type=int, default=1000)
    ap.add_argument("--page-size", type=int, default=256)
    ap.add_argument("--native-grpc", action="store_true", help="copy protobuf vectors directly (faster; requires gRPC)")
    args = ap.parse_args()
    if args.source == args.target or min(args.docs_per_batch, args.page_size) < 1:
        ap.error("source and target must differ; batch sizes must be positive")
    ids = selected_ids(args.per_mille)
    client = store.client()
    source = client.get_collection(args.source)
    identity = {"source": args.source, "target": args.target, "per_mille": args.per_mille,
                "selected_documents": len(ids), "source_points": source.points_count,
                "selection_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest()}
    checkpoint = Path(config.ENT_DATA_DIR) / f"copy_{args.target}.json"
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if state and state["identity"] != identity:
        raise RuntimeError("Checkpoint does not match this source and selection; use a new target name")
    if state is None:
        if client.collection_exists(args.target):
            raise RuntimeError("Target exists without a matching checkpoint; refusing to modify it")
        store.create(args.target, dim=source.config.params.vectors[store.DENSE].size)
        state = {"identity": identity, "documents_done": 0, "points_copied": 0, "documents_found": 0,
                 "started_at": datetime.now(timezone.utc).isoformat(), "copy_seconds": 0}
        checkpoint.write_text(json.dumps(state, indent=2))
    elif not client.collection_exists(args.target):
        raise RuntimeError("Checkpoint exists but target collection is missing")
    client.update_collection(args.target, optimizers_config=models.OptimizersConfigDiff(
        indexing_threshold=0, default_segment_number=12, max_optimization_threads=1),
        hnsw_config=models.HnswConfigDiff(max_indexing_threads=2))
    start = time.perf_counter()
    previous_seconds = state["copy_seconds"]
    print(json.dumps(identity), flush=True)
    def copy_group(i):
        group = ids[i:i + args.docs_per_batch]
        flt = models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=group))])
        offset = None
        found, copied = set(), 0
        while True:
            if args.native_grpc:
                request = grpc.ScrollPoints(collection_name=args.source, filter=RestToGrpc.convert_filter(flt),
                                            limit=args.page_size, with_vectors=grpc.WithVectorsSelector(enable=True),
                                            with_payload=grpc.WithPayloadSelector(enable=True))
                if offset is not None:
                    request.offset.CopyFrom(offset)
                page = client.grpc_points.Scroll(request, timeout=120)
                points = page.result
                offset = page.next_page_offset if page.HasField("next_page_offset") else None
                if points:
                    found.update(p.payload["doc_id"].string_value for p in points)
                    client.grpc_points.Upsert(grpc.UpsertPoints(collection_name=args.target, wait=True,
                                                               points=[native_point(p) for p in points]), timeout=120)
            else:
                points, offset = client.scroll(args.source, scroll_filter=flt, offset=offset, limit=args.page_size,
                                               with_vectors=True, with_payload=True)
                if points:
                    found.update(p.payload["doc_id"] for p in points)
                    client.upsert(args.target, points=[models.PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                                                       for p in points], wait=True)
            copied += len(points)
            if offset is None:
                break
        if set(group) != found:
            raise RuntimeError(f"{len(set(group) - found)} selected documents missing from source")
        return i + len(group), copied, len(found)

    for i in range(state["documents_done"], len(ids), args.docs_per_batch):
        done, copied, found = copy_group(i)
        state.update(documents_done=done, points_copied=state["points_copied"] + copied,
                     documents_found=state["documents_found"] + found,
                     copy_seconds=previous_seconds + time.perf_counter() - start)
        checkpoint.write_text(json.dumps(state, indent=2))
        print(f"{state['documents_done']}/{len(ids)} documents, {state['points_copied']} points, "
              f"{state['copy_seconds'] / 60:.1f} min", flush=True)
    actual = client.count(args.target, exact=True).count
    if actual != state["points_copied"]:
        raise RuntimeError(f"Target count mismatch: {actual} vs {state['points_copied']} acknowledged writes")
    client.update_collection(args.target, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000))
    state.update(points_verified=actual, completed_at=datetime.now(timezone.utc).isoformat())
    checkpoint.write_text(json.dumps(state, indent=2))
    print(f"Copy verified: {actual} points; indexing enabled. Wait for green status before snapshotting.", flush=True)


if __name__ == "__main__":
    main()
