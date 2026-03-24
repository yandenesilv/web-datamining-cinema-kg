"""
TD1 - Phase 1: Web Crawler for Cinema Domain
Course: Web Mining & Semantics - ESILV

Crawls Wikipedia pages about cinema (films, directors, awards),
extracts clean text using trafilatura, follows internal links up to depth 2,
and saves results to crawler_output.jsonl.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura


# ── Configuration ──────────────────────────────────────────────────────────────

SEED_URLS = [
    "https://en.wikipedia.org/wiki/Academy_Award_for_Best_Picture",
    "https://en.wikipedia.org/wiki/Palme_d%27Or",
    "https://en.wikipedia.org/wiki/Christopher_Nolan",
    "https://en.wikipedia.org/wiki/Martin_Scorsese",
    "https://en.wikipedia.org/wiki/Quentin_Tarantino",
    "https://en.wikipedia.org/wiki/Cate_Blanchett",
    "https://en.wikipedia.org/wiki/Parasite_(film)",
    "https://en.wikipedia.org/wiki/Inception",
    "https://en.wikipedia.org/wiki/The_Godfather",
]

MAX_DEPTH = 2               # Follow links up to depth 2
MIN_WORD_COUNT = 500         # Minimum words to keep a page
POLITENESS_DELAY = 1.0       # Seconds between requests
MAX_PAGES = 150              # Safety cap on total pages crawled
OUTPUT_FILE = "../../data/crawler_output.jsonl"
USER_AGENT = "ESILV-WebMining-Bot/1.0 (student project; +https://esilv.fr)"


# ── Robots.txt compliance ─────────────────────────────────────────────────────

def check_robots_txt(url: str) -> bool:
    """Check if the URL is allowed by the site's robots.txt.
    Fetches robots.txt with a proper User-Agent and parses it.
    If the file contains no standard Disallow directives (like Wikipedia's
    minimal policy notice), we treat it as allowing /wiki/ article pages.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        resp = httpx.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        robots_text = resp.text

        # Check if the robots.txt contains actual User-agent/Disallow rules
        has_rules = any(
            line.strip().lower().startswith(("user-agent:", "disallow:", "allow:"))
            for line in robots_text.split("\n")
        )

        if not has_rules:
            # No standard rules found (e.g., Wikipedia's policy-only response)
            # Log the policy and proceed respectfully
            print(f"  robots.txt contains no standard rules. Proceeding with politeness.")
            return True

        # Parse standard robots.txt
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(robots_text.split("\n"))
        return rp.can_fetch("*", url)
    except Exception:
        return True


# ── Content hashing for deduplication ─────────────────────────────────────────

def content_hash(text: str) -> str:
    """Generate MD5 hash of text content for deduplication."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ── Link extraction ───────────────────────────────────────────────────────────

def extract_wiki_links(html: str, base_url: str) -> list[str]:
    """Extract internal Wikipedia article links from raw HTML."""
    # Match href="/wiki/..." links, excluding special namespaces
    pattern = r'href="(/wiki/[^"#]+)"'
    matches = re.findall(pattern, html)

    links = []
    excluded_prefixes = (
        "/wiki/Wikipedia:", "/wiki/Talk:", "/wiki/User:",
        "/wiki/Template:", "/wiki/Category:", "/wiki/Portal:",
        "/wiki/Help:", "/wiki/Special:", "/wiki/File:",
        "/wiki/Module:", "/wiki/Draft:", "/wiki/MediaWiki:",
    )

    for match in matches:
        if match.startswith(excluded_prefixes):
            continue
        # Skip non-article pages (containing colons after /wiki/)
        page_name = match.replace("/wiki/", "")
        if ":" in page_name:
            continue
        full_url = urljoin(base_url, match)
        if full_url not in links:
            links.append(full_url)

    return links


# ── Page fetching & extraction ────────────────────────────────────────────────

def fetch_page(url: str, client: httpx.Client) -> tuple[str | None, str | None]:
    """Fetch a page and return (raw_html, extracted_text)."""
    try:
        response = client.get(url, follow_redirects=True, timeout=15)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None, None

    # Use trafilatura to extract main content
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    return html, text


def get_page_title(html: str) -> str:
    """Extract page title from HTML."""
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1)
        # Remove " - Wikipedia" suffix
        title = re.sub(r"\s*[-–]\s*Wikipedia.*$", "", title)
        return title.strip()
    return "Unknown"


# ── Main crawler ──────────────────────────────────────────────────────────────

def crawl():
    """Main crawling function. BFS traversal up to MAX_DEPTH."""
    print("=" * 60)
    print("  Cinema Domain Web Crawler - TD1")
    print("=" * 60)

    # Queue: list of (url, depth)
    queue = [(url, 0) for url in SEED_URLS]
    visited_urls: set[str] = set()
    content_hashes: set[str] = set()
    results = []

    # Check robots.txt once for en.wikipedia.org
    print("\n[*] Checking robots.txt compliance...")
    if not check_robots_txt(SEED_URLS[0]):
        print("[!] robots.txt disallows crawling. Aborting.")
        return
    print("[+] robots.txt allows crawling. Proceeding.\n")

    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )

    try:
        while queue and len(results) < MAX_PAGES:
            url, depth = queue.pop(0)

            # Skip already visited
            if url in visited_urls:
                continue
            visited_urls.add(url)

            # Politeness delay
            time.sleep(POLITENESS_DELAY)

            print(f"[Depth {depth}] Crawling: {url}")

            # Fetch and extract
            html, text = fetch_page(url, client)
            if not html or not text:
                print(f"  -> Skipped (no content extracted)")
                continue

            # Word count filter
            word_count = len(text.split())
            if word_count < MIN_WORD_COUNT:
                print(f"  -> Skipped ({word_count} words < {MIN_WORD_COUNT} minimum)")
                continue

            # Deduplication via content hash
            h = content_hash(text)
            if h in content_hashes:
                print(f"  -> Skipped (duplicate content)")
                continue
            content_hashes.add(h)

            # Extract title
            title = get_page_title(html)

            # Save result
            record = {
                "url": url,
                "title": title,
                "text": text,
                "word_count": word_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            results.append(record)
            print(f"  -> Saved: \"{title}\" ({word_count} words)")

            # Follow internal links if depth < MAX_DEPTH
            if depth < MAX_DEPTH:
                links = extract_wiki_links(html, url)
                new_links = [l for l in links if l not in visited_urls]
                # Limit links per page to avoid explosion
                max_links_per_page = 15 if depth == 0 else 5
                for link in new_links[:max_links_per_page]:
                    queue.append((link, depth + 1))
                print(f"  -> Queued {min(len(new_links), max_links_per_page)} new links (depth {depth + 1})")

    finally:
        client.close()

    # Write results to JSONL
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for record in results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("\n" + "=" * 60)
    print(f"  Crawling complete!")
    print(f"  Pages visited: {len(visited_urls)}")
    print(f"  Pages saved:   {len(results)}")
    print(f"  Output file:   {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    crawl()
1