import argparse
import json
import uuid
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

LIBRECHAT_URL = "http://localhost:3080"
DATA_DIR = Path(__file__).parent / "data_confluence"
PROGRESS_FILE = Path(__file__).parent / ".ingest_progress.json"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": BROWSER_UA},
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


def upload_file(token: str, agent_id: str, file_path: Path) -> tuple[Path, bool, str]:
    file_id = str(uuid.uuid4())
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{LIBRECHAT_URL}/api/files",
                headers={"Authorization": f"Bearer {token}", "User-Agent": BROWSER_UA},
                data={
                    "file_id": file_id,
                    "endpoint": "agents",
                    "agent_id": agent_id,
                    "tool_resource": "file_search",
                },
                files={"file": (file_path.name, f, "text/plain")},
                timeout=60,
            )
        if resp.status_code in (200, 201) and "Illegal" not in resp.text:
            return file_path, True, ""
        return file_path, False, f"({resp.status_code}): {resp.text[:120]}"
    except Exception as e:
        return file_path, False, str(e)


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        return set(json.loads(PROGRESS_FILE.read_text()))
    return set()


def save_progress(done: set) -> None:
    PROGRESS_FILE.write_text(json.dumps(sorted(done)))


def main():
    parser = argparse.ArgumentParser(description="Ingest confluence docs into LibreChat RAG")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--workers", type=int, default=8, help="Concurrent uploads (default: 8)")
    args = parser.parse_args()

    token = login(args.email, args.password)

    all_files = sorted(DATA_DIR.rglob("*.txt"))
    print(f"Found {len(all_files)} .txt files in {DATA_DIR}")

    done = load_progress()
    remaining = [f for f in all_files if str(f) not in done]
    print(f"Already ingested: {len(done)} | Remaining: {len(remaining)}")

    success = 0
    failed = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(upload_file, token, args.agent_id, f): f
            for f in remaining
        }
        for i, future in enumerate(as_completed(futures), 1):
            path, ok, err = future.result()
            rel = path.relative_to(DATA_DIR)
            if ok:
                done.add(str(path))
                success += 1
                print(f"[{i}/{len(remaining)}] OK  {rel}")
            else:
                failed += 1
                print(f"[{i}/{len(remaining)}] FAIL {rel} — {err}")
            if i % 20 == 0:
                save_progress(done)

    save_progress(done)
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. Success: {success} | Failed: {failed} | Total: {len(done)}")


if __name__ == "__main__":
    main()
