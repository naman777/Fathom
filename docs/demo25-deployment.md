# 25% enterprise demo deployment

The `enterprise_demo_25` collection contains **667,447 points from 128,795 distinct documents**: 25.23% of the
2,645,730-point full index. It retains all 722 benchmark gold document IDs and uses the existing deterministic
250-per-mille hash sample for distractors. Gold inclusion means demo retrieval is not an independent benchmark.

The source parquet has four repeated document IDs. Selection deduplicates IDs; the copy preserves the source index's
payloads, dense embeddings and BM25 vectors. No embeddings are regenerated. Acknowledged writes are checkpointed,
interrupted batches can be replayed, and the final exact point count must match acknowledged writes.

## Build and validate locally

With the full index available on the configured Qdrant instance:

```powershell
.venv/Scripts/python.exe -m eval.ent_copy_subset --source enterprise_full --target enterprise_demo_25 --per-mille 250 --native-grpc --page-size 512
```

The command refuses to replace an unrelated existing collection. Progress lives beside the dataset in
`ENT_DATA_DIR/copy_enterprise_demo_25.json`. Wait for green collection status and an `ok` optimizer before creating
a snapshot. Verify all gold IDs and compare sampled vectors and payloads to the source before exporting.

## Stage on the existing production VM

`compose.demo25.yml` overlays the VM's existing `/opt/fathom/compose.prod.yml`. It creates a separate Qdrant service,
volume and collection, with a 2,500 MiB memory limit and no public Qdrant ports. Keep the original `qdrant` service
available during staging. The API image tag in the overlay refers to the separately prepared deployment image.

```bash
cd /opt/fathom
docker compose -p fathom -f compose.prod.yml -f compose.demo25.yml up -d qdrant25
```

Transfer the compressed snapshot, compare its SHA-256 with the local export, decompress it into the mounted
`qdrant_snapshots/enterprise_demo_25.snapshot`, and verify the uncompressed SHA-256. Restore into the new collection
using `QDRANT_URL=http://qdrant25:6333`. Do not restore over the currently serving collection.

Preserve the prebuilt indexes after restoring on the two-vCPU server: set the collection optimizer's
`default_segment_number=12`, `max_optimization_threads=1`, and HNSW `max_indexing_threads=2`. The restored collection
has eight segments. Leaving the segment target on automatic makes it depend on CPU count and can trigger unnecessary
merges/rebuilds after moving a snapshot from a larger machine. The copy utility now sets these limits for future exports.

Before cutover, check green status, the exact count of 667,447 points, gold-document coverage and role filtering.
Run `scripts/check_enterprise_deployment.py` in the deployed API environment, with the staged Qdrant URL and collection
overridden for that process. Use the same question IDs and concurrency for the original and staged collections.
The deployment sample uses 12 questions across six benchmark categories, three concurrent full-agent requests, and
retrieval/expansion checks under every restricted role. Answer calls are paid; no judge calls are made.

Observe Qdrant working memory, host available memory and cgroup OOM events during restore and load. Check the other
projects' container states and restart counts. These checks assess a small demo workload, not sustained capacity or
benchmark answer accuracy. Recorded results are in `eval/results/deployment_demo25.json` after deployment.

## Cutover and rollback

Once staging passes, recreate only the API with the overlay:

```bash
cd /opt/fathom
docker compose -p fathom -f compose.prod.yml -f compose.demo25.yml up -d --no-deps --no-build api
```

Check public API health, the roles endpoint's passage count, an end-to-end streamed answer and the deployed Results page.
Use both compose files for subsequent API updates. The Results page reads the live passage count from the roles endpoint.
The full-corpus evaluation artifact remains separate from deployment smoke-test measurements.

Rollback uses the original compose file and image; it starts the preserved original Qdrant service if necessary:

```bash
cd /opt/fathom
docker compose -p fathom -f compose.prod.yml up -d --no-build api
```

Keep the original volume and baseline image. After a successful cutover, stop the original Qdrant container to release
RAM; do not remove its volume. API source/image metadata and original configuration are backed up under
`/opt/fathom/backups/demo25-20261030/`.
