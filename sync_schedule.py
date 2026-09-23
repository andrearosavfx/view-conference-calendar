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

# Explicitly excluding Monday 12th as requested
DAY_MAP = {
    "Tue 13th": "2026-10-13",
    "Wed 14th": "2026-10-14",
    "Thu 15th": "2026-10-15",
    "Fri 16th": "2026-10-16"
}

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
    """Fetches individual article page and extracts background image from class="bg cover"."""
    if not session_url or "/article/" not in session_url or session_url == PROGRAM_URL:
        return ""

    try:
        resp = session.get(session_url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            art_soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find element with both 'bg' and 'cover' classes
            bg_element = art_soup.find(class_=lambda c: c and "bg" in c.split() and "cover" in c.split())
            
            if bg_element and bg_element.has_attr("style"):
                style_attr = bg_element["style"]
                match = re.search(r'url\((?:\'|\")?(.*?)(?:\'|\")?\)', style_attr, re.IGNORECASE)
                if match:
                    raw_img_url = match.group(1).strip()
                    return urllib.parse.urljoin(BASE_URL, raw_img_url)

            # Secondary fallback: OpenGraph image
            og_img = art_soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                return urllib.parse.urljoin(BASE_URL, og_img["content"])

    except Exception as e:
        print(f"Warning: Could not fetch image from {session_url}: {e}")

    return ""

def scrape_full_schedule():
    session = requests.Session()
    resp = session.get(PROGRAM_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    event_id_counter = 1000
    image_cache = {}

    # Find distinct day sections or parse whole document top-down
    # Split HTML by day headers to isolate each day's content cleanly
    full_html = str(soup)
    day_splits = re.split(r'((?:Mon|Tue|Wed|Thu|Fri)\s+\d{1,2}(?:st|nd|rd|th)?)', full_html)

    current_date = None

    for idx in range(1, len(day_splits), 2):
        day_header = day_splits[idx].strip()
        day_content = day_splits[idx + 1] if idx + 1 < len(day_splits) else ""

        # Check if day belongs to Tue 13th - Fri 16th; skip Mon 12th
        current_date = None
        for key, date_val in DAY_MAP.items():
            if key in day_header:
                current_date = date_val
                break

        # If it's Monday 12th or unmapped, skip completely
        if not current_date:
            continue

        day_soup = BeautifulSoup(day_content, "html.parser")
        
        # Parse all session blocks inside this day section
        # Look for table rows, cards, or structured divs
        blocks = day_soup.find_all(['tr', 'div', 'article'])

        for block in blocks:
            text = block.get_text(" ", strip=True)

            # Match session time (e.g., 09:00-10:00 CET or 09:00 - 13:00)
            time_match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(?:CET)?', text, re.IGNORECASE)
            if not time_match:
                continue

            start_time, end_time = time_match.group(1).zfill(5), time_match.group(2).zfill(5)

            # Extract Room / Location
            room_match = re.search(r'In\s+([A-Z0-9\s]+?)\s*\((?:In Person|Remote|Hybrid)\)', text, re.IGNORECASE)
            location = f"OGR - {room_match.group(1).strip()}" if room_match else "OGR Venue"

            # Extract Title
            title_tag = block.find(['h2', 'h3', 'h4', 'strong', 'b', 'a'])
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or len(title) < 3:
                # Fallback: take first clean non-time string segment
                clean_lines = [l.strip() for l in text.split("  ") if l.strip() and "CET" not in l]
                title = clean_lines[0] if clean_lines else "VIEW Conference Session"

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

            # Session Article URL
            link_tag = block.find('a', href=True)
            session_url = urllib.parse.urljoin(BASE_URL, link_tag['href']) if link_tag else PROGRAM_URL

            # Extract Background Image from Article Page (cached)
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

    # Deduplicate events by date, start time, and title prefix
    unique_events = {}
    for ev in events:
        dedup_key = f"{ev['date']}_{ev['startTime']}_{ev['title'][:20].lower()}"
        if dedup_key not in unique_events:
            unique_events[dedup_key] = ev

    return list(unique_events.values())

def main():
    print("Scraping schedule for Oct 13-16 (filtering out Mon 12th)...")
    events = scrape_full_schedule()
    print(f"Successfully processed {len(events)} events for Tue 13th to Fri 16th.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    main()
