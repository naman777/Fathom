"""Restore a Qdrant snapshot into the enterprise collection (used to ship an index built on a GPU machine to a server).

    python scripts/restore_snapshot.py enterprise_dev.snapshot

The file must be in the directory mounted at /qdrant/snapshots in the Qdrant container. Replaces the collection named
by ENT_COLLECTION with the snapshot's contents.
"""
import sys

from core import config
from enterprise import store

name = sys.argv[1]
client = store.client()
client.recover_snapshot(config.ENT_COLLECTION, location=f"file:///qdrant/snapshots/{name}", wait=True)
info = client.get_collection(config.ENT_COLLECTION)
print(f"{config.ENT_COLLECTION}: status={info.status} points={info.points_count}")
