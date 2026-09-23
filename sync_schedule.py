import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.viewconference.it"
START_URLS = [
    f"{BASE_URL}/pages/program",
    BASE_URL
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def discover_article_urls():
    discovered = set()
    for start_url in START_URLS:
        try:
            resp = requests.get(start_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract all links matching /article/... pattern
            for a in soup.find_all("a", href=True):
                href = a['href']
                if "/article/" in href:
                    full_url = urllib.parse.urljoin(BASE_URL, href)
                    discovered.add(full_url)
        except Exception as e:
            print(f"Error fetching {start_url}: {e}")
            
    return list(discovered)

def parse_article(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        html_text = resp.text
        
        # Article ID from URL (e.g., /article/1296/...)
        article_id_match = re.search(r'/article/(\d+)', url)
        article_id = article_id_match.group(1) if article_id_match else str(hash(url))

        # Title
        title_el = soup.find('h1') or soup.find('h2')
        title = title_el.get_text(strip=True) if title_el else "VIEW Conference Session"

        # Speaker Name
        speaker = "Speaker"
        author_el = soup.find(class_=re.compile(r'speaker|author|byline', re.I))
        if author_el:
            speaker = author_el.get_text(strip=True)

        # Image Banner
        img_url = "https://s3.amazonaws.com/view-conference-www/assets/article/2026/08/21/bradbirdbanner2_feature.jpg"
        img_tag = soup.find("img", src=re.compile(r'/assets/article/'))
        if img_tag and img_tag.get("src"):
            img_url = urllib.parse.urljoin(BASE_URL, img_tag["src"])

        # Date Parsing (Default: Mon Oct 12, 2026)
        date_str = "2026-10-12"
        if "october 13" in html_text.lower() or "oct 13" in html_text.lower():
            date_str = "2026-10-13"
        elif "october 14" in html_text.lower() or "oct 14" in html_text.lower():
            date_str = "2026-10-14"
        elif "october 15" in html_text.lower() or "oct 15" in html_text.lower():
            date_str = "2026-10-15"
        elif "october 16" in html_text.lower() or "oct 16" in html_text.lower():
            date_str = "2026-10-16"

        # Time Parsing (Look for HH:MM patterns)
        time_match = re.search(r'(\d{1,2}:\d{2})\s*[-–—to]\s*(\d{1,2}:\d{2})', html_text)
        start_time = time_match.group(1) if time_match else "10:00"
        end_time = time_match.group(2) if time_match else "11:00"

        # Location Parsing
        location = "OGR Main Hall"
        if "stage b" in html_text.lower():
            location = "OGR Stage B"
        elif "auditorium" in html_text.lower():
            location = "ITS Auditorium"
        elif "massimo" in html_text.lower():
            location = "Cinema Massimo"

        # Track Parsing
        track = "Session"
        if "keynote" in html_text.lower():
            track = "Keynote"
        elif "vfx" in html_text.lower():
            track = "VFX"
        elif "animation" in html_text.lower():
            track = "Animation"
        elif "ai" in html_text.lower() or "tech" in html_text.lower():
            track = "AI & Tech"

        return {
            "id": article_id,
            "title": title,
            "speaker": speaker,
            "location": location,
            "date": date_str,
            "startTime": start_time,
            "endTime": end_time,
            "track": track,
            "imageUrl": img_url,
            "url": url
        }
    except Exception as e:
        print(f"Error parsing article {url}: {e}")
        return None

def main():
    print("Discovering article URLs across program & speaker pages...")
    urls = discover_article_urls()
    print(f"Found {len(urls)} article URLs.")

    events = []
    for url in urls:
        event = parse_article(url)
        if event:
            events.append(event)

    print(f"Successfully scraped {len(events)} event articles.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    main()
