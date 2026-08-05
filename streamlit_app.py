import os
import random
import re
import time
import zipfile
import requests
import streamlit as st
from selenium import webdriver
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

API_KEY_FROM_SECRETS = st.secrets.get("YOUTUBE_API_KEY", "")
PROXIES_FROM_SECRETS = st.secrets.get("PROXIES", [])

if "video_data" not in st.session_state:
    st.session_state.video_data = None

# --- HELPER FUNCTIONS ---
def extract_video_id(url):
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
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(iso_str)
    if not match:
        return 0
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return hours * 3600 + minutes * 60 + seconds

def fetch_api_metadata(video_id, api_key):
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

def create_proxy_auth_extension(proxy_url):
    """Creates a temporary Chrome Extension ZIP to handle authenticated proxies."""
    pattern = r"http://([^:]+):([^@]+)@([^:]+):(\d+)"
    match = re.match(pattern, proxy_url)
    if not match:
        return None, proxy_url.replace("http://", "")  # IP:Port format without user/pass

    user, password, host, port = match.groups()

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version": "22.0.0"
    }
    """

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
          singleProxy: {{
            scheme: "http",
            host: "{host}",
            port: parseInt({port})
          }},
          bypassList: ["localhost"]
        }}
      }};

    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{user}",
                password: "{password}"
            }}
        }};
    }}

    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """

    pluginpath = f'/tmp/proxy_auth_plugin_{random.randint(1000, 9999)}.zip'
    with zipfile.ZipFile(pluginpath, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return pluginpath, None

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
        st.warning("No proxies configured in Secrets. Running directly from server IP.")

    total_views = st.number_input("Target Total Views to Generate", min_value=1, value=10, step=1)
    
    watch_duration = st.number_input(
        "Playback Duration per view (seconds)", 
        min_value=1, 
        value=max(1, vdata['duration_sec'])
    )

    def get_headless_driver():
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument("--mute-audio")

        random_user_agent = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={random_user_agent}")

        pluginpath = None
        if PROXIES_FROM_SECRETS:
            selected_proxy = random.choice(PROXIES_FROM_SECRETS)
            pluginpath, unauth_proxy = create_proxy_auth_extension(selected_proxy)
            if pluginpath:
                chrome_options.add_extension(pluginpath)
            elif unauth_proxy:
                chrome_options.add_argument(f"--proxy-server=http://{unauth_proxy}")

        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Cleanup extension zip file after load
        if pluginpath and os.path.exists(pluginpath):
            os.remove(pluginpath)

        return driver

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
                time.sleep(3)

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
