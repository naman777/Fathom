import time

import psycopg
from pgvector.psycopg import register_vector

from core import config

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position    INT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector({config.EMBED_DIM}),
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS s3_key TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS flags JSONB;  -- ingest-time prompt-injection scan (ingest/safety.py)

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_emb_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (document_id);
"""


def connect(vectors: bool = True, attempts: int = 3):
    """Open a connection. The serverless Postgres we develop against occasionally drops a fresh connection
    ("server closed the connection unexpectedly"), so opening is retried with a short backoff."""
    for attempt in range(1, attempts + 1):
        conn = None
        try:
            conn = psycopg.connect(config.DB_URL, autocommit=True)
            if vectors:
                register_vector(conn)
            return conn
        except psycopg.OperationalError:
            if conn is not None:
                conn.close()
            if attempt == attempts:
                raise
            time.sleep(0.3 * attempt)


def reset():
    """Drop everything in the public schema and recreate the Fathom schema."""
    with psycopg.connect(config.DB_URL, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.execute(SCHEMA)


def init():
    with psycopg.connect(config.DB_URL, autocommit=True) as c:
        c.execute(SCHEMA)


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        reset()
        print("database reset")
    else:
        init()
        print("schema ensured")
