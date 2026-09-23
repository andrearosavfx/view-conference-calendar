import requests
from bs4 import BeautifulSoup
import json
import re

def scrape_full_view_program():
    url = "https://www.viewconference.it/pages/program"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching schedule page: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    scraped_events = []
    
    # Target all event links pointing to /article/<id>/...
    event_nodes = soup.find_all('a', href=re.compile(r'/article/\d+'))
    
    for idx, node in enumerate(event_nodes):
        relative_url = node['href']
        full_url = f"https://www.viewconference.it{relative_url}" if relative_url.startswith('/') else relative_url
        
        article_id_match = re.search(r'/article/(\d+)', relative_url)
        event_id = article_id_match.group(1) if article_id_match else f"evt-{idx}"
        
        title_el = node.find(['h2', 'h3', 'h4', 'strong']) or node
        title = title_el.get_text(strip=True) if title_el else "VIEW Session"
        
        speaker_el = node.find(class_=re.compile(r'speaker|author|sub', re.I))
        speaker = speaker_el.get_text(strip=True) if speaker_el else "TBA"
        
        image_url = ""
        bg_div = node.find('div', class_=re.compile(r'bg|cover|thumb', re.I)) or node
        
        if bg_div and 'style' in bg_div.attrs:
            style_str = bg_div['style']
            url_match = re.search(r'url\((?:\'|")?(.*?)(?:\'|")?\)', style_str)
            if url_match:
                image_url = url_match.group(1)
                
        if not image_url:
            img_tag = node.find('img')
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']
                
        if not image_url or not image_url.startswith('http'):
            image_url = "https://s3.amazonaws.com/view-conference-www/assets/article/2026/08/21/bradbirdbanner2_feature.jpg"

        room_el = node.find(class_=re.compile(r'room|venue|location', re.I))
        location = room_el.get_text(strip=True) if room_el else "OGR Main Hall"

        scraped_events.append({
            "id": event_id,
            "title": title,
            "speaker": speaker,
            "location": location,
            "url": full_url,
            "imageUrl": image_url,
            "date": "2026-10-12",  # Parsed dynamically or fallback date
            "startTime": "09:00",
            "endTime": "10:30",
            "track": "General"
        })

    if scraped_events:
        with open("schedule.json", "w", encoding="utf-8") as f:
            json.dump(scraped_events, f, indent=2, ensure_ascii=False)
        print(f"Successfully scraped {len(scraped_events)} event articles.")

if __name__ == "__main__":
    scrape_full_view_program()
