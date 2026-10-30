"""Subset exports must preserve gold documents and resume acknowledged writes without duplicates."""
import json
from types import SimpleNamespace as NS

import pytest

from eval import ent_copy_subset as copy


def test_native_copy_preserves_dense_sparse_vectors_and_payload():
    grpc = copy.grpc
    record = grpc.RetrievedPoint(id=grpc.PointId(num=1), payload={"doc_id": grpc.Value(string_value="gold")},
                                vectors=grpc.VectorsOutput(vectors=grpc.NamedVectorsOutput(vectors={
                                    "dense": grpc.VectorOutput(data=[0.25, 0.75]),
                                    "bm25": grpc.VectorOutput(data=[1.5], indices=grpc.SparseIndices(data=[17]))})))
    point = copy.native_point(record)
    assert point.id == record.id and point.payload == record.payload
    assert list(point.vectors.vectors.vectors["dense"].data) == [0.25, 0.75]
    assert list(point.vectors.vectors.vectors["bm25"].indices.data) == [17]
    assert list(point.vectors.vectors.vectors["bm25"].data) == [1.5]


def test_selection_keeps_gold_even_outside_hash_sample(monkeypatch):
    monkeypatch.setattr(copy.ent_subset, "gold_ids", lambda: {"gold"})
    monkeypatch.setattr(copy.ent_subset, "in_sample", lambda doc, rate: doc == "selected")
    monkeypatch.setattr(copy.data, "iter_documents", lambda **kw: iter([{"doc_id": d} for d in ["other", "selected", "gold", "gold"]]))
    assert copy.selected_ids(250) == ["gold", "selected"]
    with pytest.raises(ValueError):
        copy.selected_ids(0)


def test_resume_replays_partial_batch_and_preserves_vectors(monkeypatch, tmp_path):
    source = [NS(id=i, vector={"dense": [1.0, 0.0]}, payload={"doc_id": d}) for i, d in enumerate(["a", "b", "b"], 1)]

    class Client:
        exists = False
        fail = True
        points = {}

        def get_collection(self, name):
            return NS(points_count=len(source), config=NS(params=NS(vectors={"dense": NS(size=2)})))

        def collection_exists(self, name):
            return self.exists

        def update_collection(self, *args, **kwargs):
            pass

        def scroll(self, name, scroll_filter, offset, **kwargs):
            docs = scroll_filter.must[0].match.any
            rows = [p for p in source if p.payload["doc_id"] in docs]
            pos = offset or 0
            return rows[pos:pos + 1], pos + 1 if pos + 1 < len(rows) else None

        def upsert(self, name, points, wait):
            assert name == "target" and wait is True
            for p in points:
                self.points[p.id] = p
            if points[0].id == 2 and self.fail:
                self.fail = False
                raise RuntimeError("interrupted after write, before acknowledgement")

        def count(self, *args, **kwargs):
            return NS(count=len(self.points))

    client = Client()
    monkeypatch.setattr(copy.config, "ENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(copy, "selected_ids", lambda rate: ["a", "b"])
    monkeypatch.setattr(copy.store, "client", lambda: client)
    monkeypatch.setattr(copy.store, "create", lambda *a, **k: setattr(client, "exists", True))
    monkeypatch.setattr("sys.argv", ["copy", "--source", "source", "--target", "target", "--docs-per-batch", "1"])
    with pytest.raises(RuntimeError, match="interrupted"):
        copy.main()
    path = tmp_path / "copy_target.json"
    assert json.loads(path.read_text())["documents_done"] == 1
    copy.main()
    assert json.loads(path.read_text())["points_verified"] == 3
    assert len(client.points) == 3 and client.points[2].vector == source[1].vector
