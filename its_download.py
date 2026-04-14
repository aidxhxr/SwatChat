import os
import requests
import threading
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from dotenv import load_dotenv
load_dotenv()


# === CONFIG ===
BASE_URL = "https://swatkb.atlassian.net/wiki"
USERNAME = "aaidark1@swarthmore.edu"   # Atlassian login
API_TOKEN = os.getenv("API_TOKEN")
OUTPUT_DIR = "confluence_export_md"
LIMIT="1000"
count = 0
os.makedirs(OUTPUT_DIR, exist_ok=True)
auth = (USERNAME, API_TOKEN)

def get_all_spaces():
    url = f"{BASE_URL}/rest/api/space?limit={LIMIT}"
    spaces = []
    while url:
        r = requests.get(url, auth=auth)
        r.raise_for_status()
        data = r.json()
        spaces.extend(data["results"])
        next_rel = data["_links"].get("next")
        url = BASE_URL + next_rel if next_rel else None
    return spaces

def get_children(page_id):
    url = f"{BASE_URL}/rest/api/content/{page_id}/child/page?limit={LIMIT}"
    children = []
    while url:
        r = requests.get(url, auth=auth)
        r.raise_for_status()
        data = r.json()
        children.extend(data["results"])
        next_rel = data["_links"].get("next")
        url = BASE_URL + next_rel if next_rel else None
    return children

def get_page_content(page_id):
    url = f"{BASE_URL}/rest/api/content/{page_id}?expand=body.storage,version"
    r = requests.get(url, auth=auth)
    r.raise_for_status()
    return r.json()

def save_page(space_key, page):
    global count
    title = page["title"].replace("/", "-").replace(" ", "_")
    body_html = page["body"]["storage"]["value"]
    markdown = md(body_html)

    # Strip HTML tags -> plain text
    #soup = BeautifulSoup(body_html, "html.parser")
    #text = soup.get_text(separator="\n", strip=True)
    text = markdown

    # Build metadata header
    page_id = page["id"]
    url = f"{BASE_URL}/spaces/{space_key}/pages/{page_id}"
    metadata = (
        f"Title: {page['title']}\n"
        f"URL: {url}\n"
        f"Version: {page['version']['number']}\n"
        f"---\n\n"
    )

    # Save to file
    space_dir = os.path.join(OUTPUT_DIR, space_key)
    os.makedirs(space_dir, exist_ok=True)

    filepath = os.path.join(space_dir, f"{title}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(metadata + text)
    count += 1
    print(f"[{space_key}] Saved: {filepath}")

def walk_tree(space_key, page_id, visited):
    if page_id in visited:
        return
    visited.add(page_id)

    page = get_page_content(page_id)
    save_page(space_key, page)

    for child in get_children(page_id):
        walk_tree(space_key, child["id"], visited)

def scrape_space(space_key):
    print(f"\n=== Scraping space {space_key} ===")
    url = f"{BASE_URL}/rest/api/space/{space_key}/content?limit={LIMIT}"
    r = requests.get(url, auth=auth)
    r.raise_for_status()
    root_pages = r.json()["page"]["results"]

    visited = set()
    for page in root_pages:
        walk_tree(space_key, page["id"], visited)

def thread_worker(space):
    try:
        scrape_space(space["key"])
    except Exception as e:
        print(f"[{space['key']}] Error: {e}")

# === MAIN ===
spaces = get_all_spaces()
print(f"Found {len(spaces)} spaces.")

threads = []
for sp in spaces:
    t = threading.Thread(target=thread_worker, args=(sp,))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print("✅ Done. Total pages saved:", count)
