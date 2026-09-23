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

# Only include Oct 13 to Oct 16 (skipping Mon 12th)
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

def clean_location(room_str):
    """Formats room names into standard OGR locations."""
    room_str = room_str.strip().upper()
    if "SOPPALCO" in room_str or "TECA-B" in room_str or "TECA B" in room_str:
        return "OGR - SOPPALCO"
    elif "FUCINE" in room_str:
        return "OGR - Sala Fucine"
    elif "BINARIO" in room_str:
        return "OGR - Binario 3"
    elif "MEZZANINO" in room_str:
        return "OGR - Mezzanino"
    return f"OGR - {room_str}"

def scrape_full_schedule():
    session = requests.Session()
    resp = session.get(PROGRAM_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    event_id_counter = 1000
    image_cache = {}

    current_date = None

    # Traverse elements sequentially in DOM order
    for elem in soup.find_all(['h1', 'h2', 'h3', 'div', 'tr', 'td', 'article']):
        text = elem.get_text(" ", strip=True)

        # 1. Track current date based on day headers encountered
        if "VIEW Conference" in text or "OCT" in text:
            for day_key, date_val in DAY_MAP.items():
                if day_key in text:
                    current_date = date_val
                    break
            if "Mon 12th" in text:
                current_date = None  # Skip Monday Oct 12th

        if not current_date:
            continue

        # 2. Match session time format (e.g., 09:00-10:00 CET or 09:00 - 13:00)
        time_match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(?:CET)?', text, re.IGNORECASE)
        if not time_match:
            continue

        # Ensure we are parsing a leaf node container
        if elem.find_all(['td', 'article', 'tr']):
            continue

        start_time, end_time = time_match.group(1).zfill(5), time_match.group(2).zfill(5)

        # 3. Extract Room / Location
        room_match = re.search(r'In\s+([A-Z0-9\s\/\-_]+?)\s*\((?:In Person|Remote|Hybrid)\)', text, re.IGNORECASE)
        if room_match:
            location = clean_location(room_match.group(1))
        else:
            location = "OGR Venue"

        # 4. Extract & Clean Title
        title_tag = elem.find(['h2', 'h3', 'h4', 'strong', 'b', 'a'])
        title = title_tag.get_text(strip=True) if title_tag else ""
        
        if not title or len(title) < 3:
            clean_parts = [p.strip() for p in text.split("  ") if p.strip() and "CET" not in p and "In Person" not in p]
            title = clean_parts[0] if clean_parts else "VIEW Conference Session"

        # Remove location strings if accidentally captured inside title
        title = re.sub(r'In\s+[A-Z0-9\s\/\-_]+\s*\((?:In Person|Remote|Hybrid)\)', '', title, flags=re.IGNORECASE).strip()

        # 5. Extract Speaker
        speaker = "Featured Speaker"
        speaker_div = elem.find(class_=re.compile(r'speaker|presenter|author', re.I))
        if speaker_div:
            speaker = speaker_div.get_text(", ", strip=True)
        else:
            speaker_match = re.search(r'\)(.+)', text)
            if speaker_match:
                candidate = speaker_match.group(1).strip()
                if candidate and len(candidate) < 150:
                    speaker = candidate

        # Session Article URL
        link_tag = elem.find('a', href=True)
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

    # Deduplicate events by date, start time, and title
    unique_events = {}
    for ev in events:
        dedup_key = f"{ev['date']}_{ev['startTime']}_{ev['title'][:20].lower()}"
        if dedup_key not in unique_events:
            unique_events[dedup_key] = ev

    return list(unique_events.values())

def main():
    print("Scraping schedule for Oct 13-16...")
    events = scrape_full_schedule()
    print(f"Successfully processed {len(events)} events for Oct 13-16.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    main()
