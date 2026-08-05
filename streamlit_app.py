import time
import requests
import streamlit as st
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.title("YouTube Automation Tool")
st.caption("Automate video playback via Selenium")

# --- INPUT FIELDS ---
url_input = st.text_input("YouTube Video URL", placeholder="https://www.youtube.com/watch?v=...")
dur_input = st.text_input("Duration per loop (HH:MM:SS)", value="00:01:00")
loop_input = st.text_input("Loops (enter 'inf' or a number)", value="1")

# --- HELPER FUNCTIONS ---
def get_video_id(url):
    try:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            return url.split("youtu.be/")[1].split("?")[0]
    except IndexingError:
        return None
    return None

def duration_to_seconds(dur_str):
    parts = dur_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 60

# --- THUMBNAIL DISPLAY ---
if url_input:
    video_id = get_video_id(url_input)
    if video_id:
        img_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        res = requests.get(img_url)
        if res.status_code == 200:
            st.image(res.content, caption="Video Thumbnail", use_container_width=True)

# --- SELENIUM DRIVER SETUP ---
def get_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Automatically manages Chromium/ChromeDriver installation on Streamlit Cloud
    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    return webdriver.Chrome(service=service, options=chrome_options)

# --- START AUTOMATION ---
if st.button("Start Automation"):
    if not url_input:
        st.error("Please enter a valid YouTube URL.")
    else:
        seconds = duration_to_seconds(dur_input)
        
        if loop_input.lower() == "inf":
            total_loops = 999999
        else:
            try:
                total_loops = int(loop_input)
            except ValueError:
                total_loops = 1

        status_text = st.empty()
        progress_bar = st.progress(0)

        for i in range(total_loops):
            status_text.info(f"Running iteration {i + 1} of {total_loops}...")
            
            driver = None
            try:
                driver = get_headless_driver()
                driver.get(url_input)
                time.sleep(seconds)
            except Exception as e:
                st.error(f"Error encountered: {e}")
            finally:
                if driver:
                    driver.quit()
            
            progress_bar.progress((i + 1) / total_loops)

        status_text.success("Automation sequence finished.")
