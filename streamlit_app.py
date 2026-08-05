import json
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

# --- CONFIGURATION ---
ADMIN_EMAIL = "kingtechnical421@gmail.com"
USER_DB_FILE = "users.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

API_KEY_FROM_SECRETS = st.secrets.get("YOUTUBE_API_KEY", "")
PROXIES_FROM_SECRETS = st.secrets.get("PROXIES", [])

st.set_page_config(page_title="Madara Bot Service", layout="centered")

# --- JSON DATABASE HELPER FUNCTIONS ---
def load_users():
    """Load user data from users.json file."""
    if not os.path.exists(USER_DB_FILE):
        default_db = {
            ADMIN_EMAIL: {"status": "approved", "role": "admin"}
        }
        with open(USER_DB_FILE, "w") as f:
            json.dump(default_db, f, indent=4)
        return default_db
    try:
        with open(USER_DB_FILE, "r") as f:
            users = json.load(f)
            if ADMIN_EMAIL not in users:
                users[ADMIN_EMAIL] = {"status": "approved", "role": "admin"}
                save_users(users)
            return users
    except Exception:
        return {ADMIN_EMAIL: {"status": "approved", "role": "admin"}}

def save_users(users):
    """Save user data back to users.json file."""
    with open(USER_DB_FILE, "w") as f:
        json.dump(users, f, indent=4)

users_db = load_users()

# --- INITIALIZE PERSISTENT SESSION VIA QUERY PARAMS ---
query_params = st.query_params
saved_user_param = query_params.get("user", None)

if "logged_in_user" not in st.session_state:
    if saved_user_param and saved_user_param in users_db:
        if users_db[saved_user_param].get("status") == "approved":
            st.session_state.logged_in_user = saved_user_param
        else:
            st.session_state.logged_in_user = None
    else:
        st.session_state.logged_in_user = None

if "video_data" not in st.session_state:
    st.session_state.video_data = None

# --- AUTHENTICATION & LOGIN UI ---
st.sidebar.title("🔐 Authentication")

if st.session_state.logged_in_user is None:
    st.subheader("Login to Access the Automation Tool")
    email_input = st.text_input("Enter your Email Address:").strip().lower()
    
    if st.button("Login / Submit Request"):
        if not email_input or "@" not in email_input:
            st.error("Please enter a valid email address.")
        else:
            if email_input == ADMIN_EMAIL:
                st.session_state.logged_in_user = email_input
                st.query_params["user"] = email_input  # Persist login in URL
                st.success("Welcome to Madara Bot Service!")
                time.sleep(1)
                st.rerun()
            elif email_input in users_db:
                status = users_db[email_input].get("status")
                if status == "approved":
                    st.session_state.logged_in_user = email_input
                    st.query_params["user"] = email_input  # Persist login in URL
                    st.success("Welcome to Madara Bot Service!")
                    time.sleep(1)
                    st.rerun()
                elif status == "pending":
                    st.warning("Your access request is currently PENDING approval from the Admin.")
                elif status == "rejected":
                    st.error("Your access request was rejected by the Admin.")
            else:
                users_db[email_input] = {"status": "pending", "role": "user"}
                save_users(users_db)
                st.info("Access request sent to Admin! Please wait for approval before logging in.")
    st.stop()

# --- LOGGED IN HEADER ---
user_email = st.session_state.logged_in_user
is_admin = (user_email == ADMIN_EMAIL)

st.sidebar.write(f"Logged in as: **{user_email}**")
if is_admin:
    st.sidebar.write("👑 **Role:** Administrator")
else:
    st.sidebar.write("👤 **Role:** Standard User")

if st.sidebar.button("Logout"):
    st.session_state.logged_in_user = None
    st.session_state.video_data = None
    if "user" in st.query_params:
        del st.query_params["user"]  # Clear persistent login from URL
    st.rerun()

# --- WELCOME BANNER ---
st.title("🔥 Welcome to Madara Bot Service")
st.caption("Fetch metadata via YouTube Data API v3 & automate playback via Selenium")

# --- ADMIN PANEL (Visible ONLY to kingtechnical421@gmail.com) ---
if is_admin:
    st.markdown("## 🛡️ Admin Control Panel")
    st.caption("Manage pending user requests and view all registered accounts.")
    
    pending_users = [email for email, data in users_db.items() if data.get("status") == "pending"]
    
    if pending_users:
        st.subheader("⚠️ Pending Requests")
        for p_email in pending_users:
            col_email, col_approve, col_reject = st.columns([3, 1, 1])
            col_email.write(p_email)
            
            if col_approve.button("Approve", key=f"app_{p_email}"):
                users_db[p_email]["status"] = "approved"
                save_users(users_db)
                st.success(f"Approved {p_email}")
                st.rerun()
                
            if col_reject.button("Reject", key=f"rej_{p_email}"):
                users_db[p_email]["status"] = "rejected"
                save_users(users_db)
                st.error(f"Rejected {p_email}")
                st.rerun()
    else:
        st.info("No pending access requests.")

    with st.expander("📁 View All Registered Users (Stored in users.json)"):
        st.json(users_db)

    st.markdown("---")

# --- MAIN AUTOMATION TOOL (ACCESSIBLE TO APPROVED USERS) ---
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
    pattern = r"http://([^:]+):([^@]+)@([^:]+):(\d+)"
    match = re.match(pattern, proxy_url)
    if not match:
        return None, proxy_url.replace("http://", "")

    user, password, host, port = match.groups()

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "22.0.0"
    }
    """

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{ singleProxy: {{ scheme: "http", host: "{host}", port: parseInt({port}) }}, bypassList: ["localhost"] }}
    }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    function callbackFn(details) {{
        return {{ authCredentials: {{ username: "{user}", password: "{password}" }} }};
    }}
    chrome.webRequest.onAuthRequired.addListener(callbackFn, {{urls: ["<all_urls>"]}}, ['blocking']);
    """

    pluginpath = f'/tmp/proxy_auth_plugin_{random.randint(1000, 9999)}.zip'
    with zipfile.ZipFile(pluginpath, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return pluginpath, None

# --- STEP 1: API KEY & URL INPUT ---
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
    watch_duration = st.number_input("Playback Duration per view (seconds)", min_value=1, value=max(1, vdata['duration_sec']))

    def get_headless_driver():
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument("--mute-audio")
        chrome_options.binary_location = "/usr/bin/chromium"

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

        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)

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
