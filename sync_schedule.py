import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

PROGRAM_URL = "https://www.viewconference.it/assets/html/view_CET.html"
BASE_URL = "https://www.viewconference.it"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_program_schedule():
    """Parses the official view_CET.html endpoint which contains the complete timetable."""
    try:
        resp = requests.get(PROGRAM_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"Failed to fetch program page: {resp.status_code}")
            return []
        
        soup = BeautifulSoup(resp.text, "html.parser")
        events = []
        
        # The program list items inside view_CET.html
        items = soup.find_all("li") or soup.find_all("div", class_=re.compile(r'item|session|event', re.I))
        
        # Fallback: scan text blocks if structured list tags aren't standard
        text_content = soup.get_text()
        
        # Parse individual sessions out of the program page HTML structure
        # Matches patterns like: "09:00-10:00 CET [Talk in English] In FUCINE ... TITLE ... SPEAKER"
        session_blocks = re.split(r'\n(?=\d{2}:\d{2}-\d{2}:\d{2})', text_content)
        
        article_id_counter = 1000

        for block in session_blocks:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            if not lines:
                continue

            # Time matching (e.g. 09:00-10:00 CET)
            time_match = re.search(r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})', lines[0])
            if not time_match:
                continue
            
            start_time = time_match.group(1)
            end_time = time_match.group(2)

            # Room / Location
            location = "OGR Main Hall"
            if "FUCINE" in block:
                location = "OGR - Sala Fucine"
            elif "BINARIO3" in block or "BINARIO 3" in block:
                location = "OGR - Binario 3"
            elif "MEZZANINO" in block:
                location = "OGR - Mezzanino"
            elif "TECA" in block or "SOPPALCO" in block:
                location = "OGR - Teca / Soppalco"
            elif "MASSIMO" in block:
                location = "Cinema Massimo"

            # Track
            track = "Session"
            if "Keynote" in block or "KEYNOTE" in block:
                track = "Keynote"
            elif "Panel" in block or "PANEL" in block:
                track = "Panel"
            elif "Lab" in block or "LAB" in block or "Workshop" in block:
                track = "Workshop"
            elif "VFX" in block:
                track = "VFX"

            # Date detection (VIEW Conference runs Mon Oct 12 to Fri Oct 16, 2026)
            date_str = "2026-10-12"
            if "Tue" in block or "Oct 13" in block:
                date_str = "2026-10-13"
            elif "Wed" in block or "Oct 14" in block:
                date_str = "2026-10-14"
            elif "Thu" in block or "Oct 15" in block:
                date_str = "2026-10-15"
            elif "Fri" in block or "Oct 16" in block:
                date_str = "2026-10-16"

            # Clean Title and Speaker extraction
            title = "VIEW Session"
            speaker = "Featured Speaker"

            # Extract title (first line following the time block)
            for l in lines[1:]:
                if not re.search(r'CET|In Person|Talk in|Panel in|Lab in', l, re.I):
                    if len(l) > 3 and title == "VIEW Session":
                        title = l
                    elif len(l) > 3 and speaker == "Featured Speaker":
                        speaker = l
                        break

            article_id_counter += 1

            events.append({
                "id": str(article_id_counter),
                "title": title,
                "speaker": speaker,
                "location": location,
                "date": date_str,
                "startTime": start_time,
                "endTime": end_time,
                "track": track,
                "imageUrl": "https://s3.amazonaws.com/view-conference-www/assets/article/2026/08/21/bradbirdbanner2_688x387.jpg",
                "url": PROGRAM_URL
            })

        return events
    except Exception as e:
        print(f"Error parsing schedule: {e}")
        return []

def scrape_articles_directly():
    """Scrapes individual /article/ URLs for precise titles, images, and speakers."""
    start_urls = [
        f"{BASE_URL}/pages/program",
        f"{BASE_URL}/pages/speakers",
        BASE_URL
    ]
    
    article_urls = set()
    for s_url in start_urls:
        try:
            r = requests.get(s_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    if "/article/" in a['href']:
                        article_urls.add(urllib.parse.urljoin(BASE_URL, a['href']))
        except Exception as e:
            print(f"Error discovering URLs: {e}")

    events = []
    for url in article_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            
            soup = BeautifulSoup(r.text, "html.parser")
            html_text = r.text

            # ID
            id_match = re.search(r'/article/(\d+)', url)
            article_id = id_match.group(1) if id_match else str(hash(url))

            # Precise Title (Filter out generic header title)
            title = ""
            # Check meta tag or article title element first
            meta_title = soup.find("meta", property="og:title")
            if meta_title and meta_title.get("content"):
                title = meta_title["content"].split("|")[0].strip()
            if not title or title.lower().startswith("view conference"):
                for header in soup.find_all(['h1', 'h2', 'h3']):
                    txt = header.get_text(strip=True)
                    if txt and not txt.lower().startswith("view conference"):
                        title = txt
                        break
            if not title:
                title = "VIEW Conference Session"

            # Speaker
            speaker = "Featured Speaker"
            speaker_tag = soup.find(class_=re.compile(r'speaker|author|byline|subtitle', re.I))
            if speaker_tag:
                speaker = speaker_tag.get_text(strip=True)

            # Image
            img_url = "https://s3.amazonaws.com/view-conference-www/assets/article/2026/08/21/bradbirdbanner2_688x387.jpg"
            img_tag = soup.find("img", src=re.compile(r'/assets/article/'))
            if img_tag and img_tag.get("src"):
                img_url = urllib.parse.urljoin(BASE_URL, img_tag["src"])

            # Time Parsing (e.g., 14:00-15:00)
            time_match = re.search(r'(\d{1,2}:\d{2})\s*[-–—to]\s*(\d{1,2}:\d{2})', html_text)
            start_time = time_match.group(1) if time_match else "10:00"
            end_time = time_match.group(2) if time_match else "11:00"

            # Date Parsing
            date_str = "2026-10-12"
            if "oct 13" in html_text.lower() or "october 13" in html_text.lower() or "tuesday" in html_text.lower():
                date_str = "2026-10-13"
            elif "oct 14" in html_text.lower() or "october 14" in html_text.lower() or "wednesday" in html_text.lower():
                date_str = "2026-10-14"
            elif "oct 15" in html_text.lower() or "october 15" in html_text.lower() or "thursday" in html_text.lower():
                date_str = "2026-10-15"
            elif "oct 16" in html_text.lower() or "october 16" in html_text.lower() or "friday" in html_text.lower():
                date_str = "2026-10-16"

            # Room Parsing
            location = "OGR Main Hall"
            if "fucine" in html_text.lower():
                location = "OGR - Sala Fucine"
            elif "binario" in html_text.lower():
                location = "OGR - Binario 3"
            elif "mezzanino" in html_text.lower():
                location = "OGR - Mezzanino"
            elif "massimo" in html_text.lower():
                location = "Cinema Massimo"

            # Track
            track = "Session"
            if "keynote" in html_text.lower():
                track = "Keynote"
            elif "vfx" in html_text.lower():
                track = "VFX"
            elif "animation" in html_text.lower():
                track = "Animation"

            events.append({
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
            })
        except Exception as e:
            print(f"Error parsing {url}: {e}")

    return events

def main():
    print("Scraping direct schedule and article pages...")
    events = parse_program_schedule()
    
    # If timetable scraping returned few results, scrape individual article pages
    if len(events) < 10:
        print("Schedule page empty or dynamic. Fetching individual article pages...")
        events = scrape_articles_directly()

    print(f"Successfully scraped {len(events)} valid schedule items.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    main()
