import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.viewconference.it"
PROGRAM_URL = "https://www.viewconference.it/assets/html/view_CET.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

DAY_MAP = {
    "Mon 12th": "2026-10-12",
    "Tue 13th": "2026-10-13",
    "Wed 14th": "2026-10-14",
    "Thu 15th": "2026-10-15",
    "Fri 16th": "2026-10-16"
}

DEFAULT_IMAGE = "https://s3.amazonaws.com/view-conference-www/assets/article/2026/08/21/bradbirdbanner2_688x387.jpg"

def determine_track(title_text, type_text=""):
    combined = f"{title_text} {type_text}".lower()
    if "keynote" in combined or "fireside" in combined:
        return "Keynote"
    elif "vfx" in combined or "visual effects" in combined or "marvel" in combined:
        return "VFX"
    elif "animation" in combined or "pixar" in combined or "disney" in combined or "stop-motion" in combined or "toy story" in combined:
        return "Animation"
    elif "ai" in combined or "tech" in combined or "nvidia" in combined or "unreal" in combined:
        return "AI & Tech"
    elif "cinematography" in combined or "deakins" in combined:
        return "Cinematography"
    return "Session"

def extract_article_bg_image(session_url, session):
    """Fetches the individual article page and extracts the background image URL from class="bg cover"."""
    if not session_url or "/article/" not in session_url or session_url == PROGRAM_URL:
        return DEFAULT_IMAGE

    try:
        resp = session.get(session_url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            art_soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look specifically for elements with both "bg" and "cover" classes
            bg_element = art_soup.find(class_=lambda c: c and "bg" in c.split() and "cover" in c.split())
            
            if bg_element and bg_element.has_attr("style"):
                style_attr = bg_element["style"]
                # Extract image path inside url('...') or url(...)
                match = re.search(r'url\((?:\'|\")?(.*?)(?:\'|\")?\)', style_attr, re.IGNORECASE)
                if match:
                    raw_img_url = match.group(1).strip()
                    return urllib.parse.urljoin(BASE_URL, raw_img_url)

            # Secondary fallback: check OpenGraph meta image tag if style element is missing
            og_img = art_soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                return urllib.parse.urljoin(BASE_URL, og_img["content"])

    except Exception as e:
        print(f"Warning: Could not fetch image from {session_url}: {e}")

    return DEFAULT_IMAGE

def scrape_full_schedule():
    session = requests.Session()
    resp = session.get(PROGRAM_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    event_id_counter = 1000

    current_date = "2026-10-12"
    
    # Locate all schedule blocks
    session_blocks = soup.find_all(class_=re.compile(r'session|event|talk-card|item', re.I))
    if not session_blocks:
        session_blocks = soup.find_all(['td', 'div'])

    # Cache article image URLs across identical sessions to minimize network calls
    image_cache = {}

    for block in session_blocks:
        text = block.get_text(" ", strip=True)
        
        # Check for date headers
        for day_key, date_val in DAY_MAP.items():
            if day_key in text:
                current_date = date_val

        # Extract Time
        time_match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*CET', text, re.IGNORECASE)
        if not time_match:
            continue

        start_time, end_time = time_match.group(1).zfill(5), time_match.group(2).zfill(5)

        # Extract Room / Location
        room_match = re.search(r'In\s+([A-Z0-9\s]+?)\s*\((?:In Person|Remote|Hybrid)\)', text, re.IGNORECASE)
        location = f"OGR - {room_match.group(1).strip()}" if room_match else "VIEW Conference Venue"

        # Extract Title
        title_tag = block.find(['h2', 'h3', 'h4', 'strong', 'b', 'a'])
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = lines[0] if lines else "VIEW Conference Session"

        # Extract Speaker
        speaker = "Featured Speaker"
        speaker_div = block.find(class_=re.compile(r'speaker|presenter|author', re.I))
        if speaker_div:
            speaker = speaker_div.get_text(", ", strip=True)
        else:
            speaker_match = re.search(r'\)(.+)', text)
            if speaker_match:
                candidate = speaker_match.group(1).strip()
                if candidate and len(candidate) < 150:
                    speaker = candidate

        # Session URL
        link_tag = block.find('a', href=True)
        session_url = urllib.parse.urljoin(BASE_URL, link_tag['href']) if link_tag else PROGRAM_URL

        # Article Background Image extraction
        if session_url in image_cache:
            img_url = image_cache[session_url]
        else:
            img_url = extract_article_bg_image(session_url, session)
            image_cache[session_url] = img_url

        event_id_counter += 1
        
        events.append({
            "id": str(event_id_counter),
            "title": title,
            "speaker": speaker,
            "location": location,
            "date": current_date,
            "startTime": start_time,
            "endTime": end_time,
            "track": determine_track(title, text),
            "imageUrl": img_url,
            "url": session_url
        })

    # Deduplicate events based on date, start time, and title
    unique_events = {}
    for ev in events:
        dedup_key = f"{ev['date']}_{ev['startTime']}_{ev['title'][:20].lower()}"
        if dedup_key not in unique_events:
            unique_events[dedup_key] = ev

    return list(unique_events.values())

def main():
    print("Scraping full schedule and fetching article background images...")
    events = scrape_full_schedule()
    print(f"Successfully processed {len(events)} events.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    main()
