import random
import re
import time
import requests
import streamlit as st
from seleniumwire import webdriver  # Handles proxy authentication seamlessly
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="YouTube Automation", layout="centered")
st.title("YouTube Automation Tool")
st.caption("Fetch metadata via YouTube Data API v3 & automate playback via Selenium")

# --- USER AGENTS & SECRETS CONFIGURATION ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

# Pull API Key and Proxies safely from Streamlit Secrets
API_KEY_FROM_SECRETS = st.secrets.get("YOUTUBE_API_KEY", "")
PROXIES_FROM_SECRETS = st.secrets.get("PROXIES", [])

# Initialize session state for storing fetched metadata across reruns
if "video_data" not in st.session_state:
    st.session_state.video_data = None

# --- HELPER FUNCTIONS ---
def extract_video_id(url):
    """Extracts YouTube Video ID from standard, short, or Shorts links."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def parse_iso8601_duration(iso_str):
    """Converts ISO 8601 duration (e.g. PT1M30S) into total seconds."""
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(iso_str)
    if not match:
        return 0
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return hours * 3600 + minutes * 60 + seconds

def fetch_api_metadata(video_id, api_key):
    """Fetches video metadata using official YouTube Data API v3."""
    endpoint = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&id={video_id}&key={api_key}"
    try:
        response = requests.get(endpoint)
        data = response.json()
        
        if "error" in data:
            st.error(f"API Error: {data['error']['message']}")
            return None
        
        items = data.get("items", [])
        if not items:
            st.error("No video found for this Video ID.")
            return None

        video_info = items[0]
        snippet = video_info.get("snippet", {})
        content_details = video_info.get("contentDetails", {})
        statistics = video_info.get("statistics", {})

        thumbnails = snippet.get("thumbnails", {})
        thumb_url = (
            thumbnails.get("maxres", {}).get("url") or 
            thumbnails.get("high", {}).get("url") or 
            thumbnails.get("default", {}).get("url")
        )

        return {
            "title": snippet.get("title", "Unknown Title"),
            "duration_sec": parse_iso8601_duration(content_details.get("duration", "PT0S")),
            "thumbnail": thumb_url,
            "current_views": statistics.get("viewCount", "N/A")
        }
    except Exception as e:
        st.error(f"Failed to fetch API data: {e}")
        return None

# --- STEP 1: API KEY RETRIEVAL & URL INPUT ---
api_key = API_KEY_FROM_SECRETS
if api_key:
    st.success("YouTube API Key loaded from Streamlit Secrets!")
else:
    api_key = st.text_input("YouTube Data API Key", type="password", placeholder="AIzaSy...")

url_input = st.text_input("YouTube Video URL", placeholder="https://www.youtube.com/watch?v=... or shorts URL")
submit_btn = st.button("Submit & Fetch Data")

if submit_btn:
    if not api_key:
        st.warning("Please enter your YouTube API Key or configure it in Streamlit Secrets.")
    elif not url_input:
        st.warning("Please enter a YouTube video URL.")
    else:
        video_id = extract_video_id(url_input)
        if not video_id:
            st.error("Could not parse a valid YouTube Video ID from the link.")
        else:
            with st.spinner("Fetching accurate video data via YouTube API..."):
                metadata = fetch_api_metadata(video_id, api_key)
                if metadata:
                    st.session_state.video_data = metadata
                    st.success("Metadata successfully loaded!")

# --- STEP 2: DISPLAY METADATA & AUTOMATION SETTINGS ---
if st.session_state.video_data:
    vdata = st.session_state.video_data
    
    st.markdown("---")
    st.subheader("Fetched Video Metadata")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        if vdata["thumbnail"]:
            st.image(vdata["thumbnail"], use_container_width=True)
    with col2:
        st.write(f"**Title:** {vdata['title']}")
        
        # Convert seconds to HH:MM:SS format
        mins, secs = divmod(vdata['duration_sec'], 60)
        hrs, mins = divmod(mins, 60)
        st.write(f"**Duration:** {hrs:02d}:{mins:02d}:{secs:02d} ({vdata['duration_sec']} seconds)")
        
        formatted_views = f"{int(vdata['current_views']):,}" if vdata['current_views'].isdigit() else vdata['current_views']
        st.write(f"**Current Total Views on YouTube:** {formatted_views}")

    st.markdown("---")
    st.subheader("Automation Setup")
    
    if PROXIES_FROM_SECRETS:
        st.info(f"Proxy pool active: {len(PROXIES_FROM_SECRETS)} rotating proxies loaded from Secrets.")
    else:
        st.warning("No proxies configured in Secrets. Requests will run directly from server IP.")

    total_views = st.number_input("Target Total Views to Generate", min_value=1, value=10, step=1)
    
    watch_duration = st.number_input(
        "Playback Duration per view (seconds)", 
        min_value=1, 
        value=max(1, vdata['duration_sec'])
    )

    # --- SELENIUM HEADLESS DRIVER SETUP WITH PROXY ROTATION ---
    def get_headless_driver():
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument("--mute-audio")

        # Set a random User-Agent header
        random_user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={random_user_agent}")

        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())

        # Inject rotating proxy if available in Secrets
        if PROXIES_FROM_SECRETS:
            selected_proxy = random.choice(PROXIES_FROM_SECRETS)
            seleniumwire_options = {
                'proxy': {
                    'http': selected_proxy,
                    'https': selected_proxy,
                    'no_proxy': 'localhost,127.0.0.1'
                }
            }
            return webdriver.Chrome(
                service=service,
                options=chrome_options,
                seleniumwire_options=seleniumwire_options
            )
        else:
            return webdriver.Chrome(service=service, options=chrome_options)

    # --- STEP 3: START AUTOMATION ---
    if st.button("Start Automation"):
        status_text = st.empty()
        progress_bar = st.progress(0)

        for current_view in range(1, int(total_views) + 1):
            status_text.info(f"Running session {current_view} of {total_views}...")
            
            driver = None
            try:
                driver = get_headless_driver()
                driver.get(url_input)
                time.sleep(3)  # Wait for player script elements to initialize

                # Force playback start via JavaScript execution
                driver.execute_script(
                    "var video = document.querySelector('video'); if(video) { video.muted = true; video.play(); }"
                )
                
                time.sleep(watch_duration)
                
            except Exception as e:
                st.error(f"Error on iteration {current_view}: {e}")
            finally:
                if driver:
                    driver.quit()

            progress_bar.progress(current_view / total_views)

        status_text.success(f"Automation finished for {total_views} view iterations!")
