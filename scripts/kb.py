from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ingest import knowledge_store  # noqa: E402
from app.services.memory import init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Darukaa knowledge-base tools")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest a file or the knowledge directories")
    ingest.add_argument("path", nargs="?", help="Optional file or folder")
    sub.add_parser("rebuild", help="Rebuild vector index from stored chunks")
    sub.add_parser("status", help="Show document and chunk counts")
    args = parser.parse_args()
    init_db()
    if args.command == "ingest":
        if args.path:
            target = Path(args.path)
            if target.is_dir():
                print(knowledge_store.ingest_directory(target))
            else:
                print(knowledge_store.ingest_path(target))
        else:
            print(knowledge_store.ingest_directory())
    elif args.command == "rebuild":
        knowledge_store.rebuild_vectors()
        print({"rebuilt": True, "stats": knowledge_store.stats()})
    elif args.command == "status":
        docs, chunks = knowledge_store.stats()
        print({"documents": docs, "chunks": chunks})


if __name__ == "__main__":
    main()
