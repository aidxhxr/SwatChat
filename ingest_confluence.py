"""
Bulk-ingests all .txt files from data_confluence into the LibreChat RAG API,
associated with a specific Agent so every user of that agent can search them.

Usage:
    python ingest_confluence.py \
        --email admin@example.com \
        --password yourpassword \
        --agent-id <agent_id_from_librechat_ui>

Requirements:
    pip install requests

Steps before running:
    1. Create an Agent in LibreChat (Agents > New Agent):
       - Model: Qwen3.5-27B.Q5_K_M.gguf  (SwatGPT endpoint)
       - Enable "File Search" capability
       - Save and copy the agent ID from the URL or agent details
    2. Restart the LibreChat backend so it picks up RAG_API_URL from .env
    3. Run this script
"""

import argparse
import json
import os
import uuid
import sys
import time
from pathlib import Path

import requests

LIBRECHAT_URL = "http://localhost:3080"
DATA_DIR = Path(__file__).parent / "data_confluence"
PROGRESS_FILE = Path(__file__).parent / ".ingest_progress.json"


def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Login failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    token = resp.json().get("token")
    if not token:
        print("No token in login response:", resp.json())
        sys.exit(1)
    print("Logged in successfully.")
    return token


def upload_file(token: str, agent_id: str, file_path: Path) -> bool:
    file_id = str(uuid.uuid4())
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{LIBRECHAT_URL}/api/files",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_id": file_id,
                "endpoint": "agents",
                "agent_id": agent_id,
                "tool_resource": "file_search",
            },
            files={"file": (file_path.name, f, "text/plain")},
            timeout=60,
        )
    if resp.status_code in (200, 201):
        return True
    print(f"  FAILED ({resp.status_code}): {resp.text[:200]}")
    return False


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        return set(json.loads(PROGRESS_FILE.read_text()))
    return set()


def save_progress(done: set) -> None:
    PROGRESS_FILE.write_text(json.dumps(sorted(done)))


def main():
    parser = argparse.ArgumentParser(description="Ingest confluence docs into LibreChat RAG")
    parser.add_argument("--email", required=True, help="LibreChat admin email")
    parser.add_argument("--password", required=True, help="LibreChat admin password")
    parser.add_argument("--agent-id", required=True, help="LibreChat Agent ID to associate files with")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between uploads (default: 0.3)")
    args = parser.parse_args()

    token = login(args.email, args.password)

    all_files = sorted(DATA_DIR.rglob("*.txt"))
    print(f"Found {len(all_files)} .txt files in {DATA_DIR}")

    done = load_progress()
    remaining = [f for f in all_files if str(f) not in done]
    print(f"Already ingested: {len(done)} | Remaining: {len(remaining)}")

    success = 0
    failed = 0
    for i, path in enumerate(remaining, 1):
        rel = path.relative_to(DATA_DIR)
        print(f"[{i}/{len(remaining)}] {rel} ... ", end="", flush=True)
        ok = upload_file(token, args.agent_id, path)
        if ok:
            print("OK")
            done.add(str(path))
            success += 1
        else:
            failed += 1
        if i % 20 == 0:
            save_progress(done)
        if args.delay > 0:
            time.sleep(args.delay)

    save_progress(done)
    print(f"\nDone. Success: {success} | Failed: {failed} | Total ingested: {len(done)}")


if __name__ == "__main__":
    main()
