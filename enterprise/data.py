"""Readers for the EnterpriseRAG-Bench parquet files (https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench).

Documents: doc_id, source_type, title, content (about 512k rows). Questions: question_id, question_type, source_types,
question, expected_doc_ids, gold_answer, answer_facts (500 rows). The files live outside the repo (config.ENT_DATA_DIR).
"""
from pathlib import Path

import pyarrow.parquet as pq

from core import config


def _file(kind: str) -> Path:
    p = Path(config.ENT_DATA_DIR) / "data" / kind / "test.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Download the dataset into ENT_DATA_DIR (see README, Enterprise search).")
    return p


def questions() -> list[dict]:
    return pq.read_table(_file("questions")).to_pylist()


def iter_documents(batch_size: int = 2000, columns=None):
    """Yield documents one at a time without loading the whole 1.4 GB file."""
    f = pq.ParquetFile(_file("documents"))
    for batch in f.iter_batches(batch_size=batch_size, columns=columns):
        yield from batch.to_pylist()


def count_documents() -> int:
    return pq.ParquetFile(_file("documents")).metadata.num_rows
