import streamlit as st
import subprocess
import os
import signal
import time
import sys
import requests
from pathlib import Path
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="Telegram YouTube Downloader Bot",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #FF0000;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.8rem;
        margin-top: 2rem;
    }
    .status-running {
        color: #00CC00;
        font-weight: bold;
    }
    .status-stopped {
        color: #FF0000;
        font-weight: bold;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;    
    }
    .log-container {
        height: 400px;
        overflow-y: auto;
        background-color: #f9f9f9;
        border-radius: 5px;
        padding: 10px;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# Define paths for Streamlit Cloud compatibility
base_dir = Path.cwd()
logs_dir = base_dir / "logs"
bot_log_path = logs_dir / "bot.log"
user_log_path = logs_dir / "user.log"
bot_script_path = base_dir / "bot.py"

# Create logs directory if it doesn't exist
logs_dir.mkdir(exist_ok=True)

# Create empty log files if they don't exist
if not bot_log_path.exists():
    with open(bot_log_path, 'w') as f:
        f.write("Log initialized for Streamlit Cloud\n")
        
if not user_log_path.exists():
    with open(user_log_path, 'w') as f:
        f.write("User log initialized for Streamlit Cloud\n")

# Global variables
bot_process = None

# Functions
def get_log_content(log_path, max_lines=100):
    """Get the content of a log file"""
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        return "Log file not found or empty."
    except Exception as e:
        return f"Error reading log: {str(e)}"

def start_bot():
    """Start the bot process for Streamlit Cloud"""
    global bot_process
    
    # For Streamlit Cloud, we'll use a different approach
    # since we can't directly manage processes
    try:
        # Write to the log that we're attempting to start
        with open(bot_log_path, 'a') as f:
            f.write(f"{datetime.now()} - INFO - Attempting to start bot via Streamlit Cloud\n")
            
        # In Streamlit Cloud, we'll use a flag file to indicate the bot should be running
        with open(base_dir / "bot_running.flag", 'w') as f:
            f.write(str(datetime.now()))
            
        st.session_state.bot_running = True
        return True
    except Exception as e:
        st.error(f"Failed to start bot: {e}")
        return False

def stop_bot():
    """Stop the bot process for Streamlit Cloud"""
    global bot_process
    
    try:
        # Write to the log that we're attempting to stop
        with open(bot_log_path, 'a') as f:
            f.write(f"{datetime.now()} - INFO - Attempting to stop bot via Streamlit Cloud\n")
            
        # Remove the flag file to indicate the bot should stop
        flag_file = base_dir / "bot_running.flag"
        if flag_file.exists():
            flag_file.unlink()
            
        st.session_state.bot_running = False
        return True
    except Exception as e:
        st.error(f"Failed to stop bot: {e}")
        return False

def check_bot_status():
    """Check if the bot is running in Streamlit Cloud"""
    flag_file = base_dir / "bot_running.flag"
    return flag_file.exists()

def get_download_stats():
    """Get download statistics from logs"""
    stats = {
        "total_requests": 0,
        "completed": 0,
        "failed": 0,
        "success_rate": 0,
        "recent_downloads": []
    }
    
    if os.path.exists(user_log_path):
        try:
            with open(user_log_path, 'r', encoding='utf-8') as f:
                logs = f.readlines()
                
            stats["total_requests"] = sum(1 for line in logs if "URL REQUEST" in line)
            stats["completed"] = sum(1 for line in logs if "DOWNLOAD COMPLETE" in line)
            stats["failed"] = sum(1 for line in logs if "DOWNLOAD FAILED" in line)
            
            if stats["completed"] + stats["failed"] > 0:
                stats["success_rate"] = (stats["completed"] / (stats["completed"] + stats["failed"])) * 100
                
            # Get recent downloads
            recent_downloads = []
            for line in reversed(logs):
                if "DOWNLOAD COMPLETE" in line:
                    parts = line.split(" | ")
                    if len(parts) >= 5:
                        try:
                            timestamp = parts[0]
                            title = parts[-1].replace("Title: ", "").strip()
                            format_type = parts[3].replace("Format: ", "").strip()
                            size = parts[4].replace("Size: ", "").replace("MB", "").strip()
                            
                            recent_downloads.append({
                                "timestamp": timestamp,
                                "title": title,
                                "format": format_type,
                                "size": f"{size} MB"
                            })
                            
                            if len(recent_downloads) >= 5:
                                break
                        except:
                            pass
                            
            stats["recent_downloads"] = recent_downloads
                
        except Exception as e:
            st.error(f"Error reading statistics: {e}")
            
    return stats

def check_yt_dlp_version():
    """Check the installed version of yt-dlp"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "yt-dlp"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.replace("Version:", "").strip()
        
        return "Unknown"
    except:
        return "Unknown"

# Initialize session state
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = check_bot_status()
    
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
    
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Sidebar
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/800px-YouTube_full-color_icon_%282017%29.svg.png", width=100)
    st.markdown("<h2 style='text-align: center;'>Bot Controls</h2>", unsafe_allow_html=True)
    
    status = "🟢 RUNNING" if st.session_state.bot_running else "🔴 STOPPED"
    status_class = "status-running" if st.session_state.bot_running else "status-stopped"
    st.markdown(f"<h3 style='text-align: center;' class='{status_class}'>{status}</h3>", unsafe_allow_html=True)
    
    # Note about Streamlit Cloud limitations
    st.info("⚠️ Note: On Streamlit Cloud, the bot control buttons are for demonstration only. The actual bot needs to be run separately.")
    
    if st.session_state.bot_running:
        if st.button("⏹️ STOP BOT", type="primary", use_container_width=True):
            if stop_bot():
                st.success("Bot stop signal sent!")
                time.sleep(1)
                st.rerun()
    else:
        if st.button("▶️ START BOT", type="primary", use_container_width=True):
            if start_bot():
                st.success("Bot start signal sent!")
                time.sleep(1)
                st.rerun()
    
    st.divider()
    
    st.markdown("### Auto-Refresh")
    auto_refresh = st.checkbox("Enable auto-refresh", value=st.session_state.auto_refresh)
    
    if auto_refresh != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_refresh
        st.rerun()
    
    if st.session_state.auto_refresh:
        refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 15)
        current_time = datetime.now()
        if (current_time - st.session_state.last_refresh).total_seconds() > refresh_interval:
            st.session_state.last_refresh = current_time
            st.rerun()
            
        st.info(f"Next refresh in {refresh_interval - int((current_time - st.session_state.last_refresh).total_seconds())} seconds")
    
    st.divider()
    
    # System info
    st.markdown("### System Info")
    yt_dlp_version = check_yt_dlp_version()
    st.markdown(f"**yt-dlp version:** {yt_dlp_version}")
    st.markdown(f"**Python version:** {sys.version.split()[0]}")
    
    if st.button("Manual Refresh", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

# Main content
st.markdown("<h1 class='main-header'>📥 Telegram YouTube Downloader Bot</h1>", unsafe_allow_html=True)

# Streamlit Cloud notice
st.warning("""
**Streamlit Cloud Deployment Notice:**
This dashboard is running on Streamlit Cloud, which has limitations for running background processes.
For full functionality, the bot should be run on a dedicated server or local machine.
This interface can be used to monitor logs and statistics from a separately running bot instance.
""")

# Dashboard
st.markdown("<h2 class='sub-header'>📊 Dashboard</h2>", unsafe_allow_html=True)

stats = get_download_stats()
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Requests", stats["total_requests"])
    
with col2:
    st.metric("Downloads Completed", stats["completed"])
    
with col3:
    st.metric("Downloads Failed", stats["failed"])
    
with col4:
    st.metric("Success Rate", f"{stats['success_rate']:.1f}%")

# Recent downloads
if stats["recent_downloads"]:
    st.markdown("<h2 class='sub-header'>🔄 Recent Downloads</h2>", unsafe_allow_html=True)
    
    for download in stats["recent_downloads"]:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{download['title']}**")
            with col2:
                st.markdown(f"Format: {download['format']}")
            with col3:
                st.markdown(f"Size: {download['size']}")
            st.divider()

# Logs section
st.markdown("<h2 class='sub-header'>📜 Logs</h2>", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])

with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        bot_search = st.text_input("Filter bot logs (case-insensitive):", key="bot_search")
    
    with col2:
        bot_log_level = st.selectbox(
            "Filter by log level:",
            ["All", "INFO", "WARNING", "ERROR", "CRITICAL"],
            key="bot_log_level"
        )
    
    # Get log content
    bot_log_content = get_log_content(bot_log_path, max_lines=500)
    
    # Apply filters
    if bot_search:
        filtered_lines = [line for line in bot_log_content.split('\n') 
                         if bot_search.lower() in line.lower()]
        bot_log_content = '\n'.join(filtered_lines)
    
    if bot_log_level != "All":
        filtered_lines = [line for line in bot_log_content.split('\n') 
                         if f" - {bot_log_level} - " in line]
        bot_log_content = '\n'.join(filtered_lines)
    
    # Display logs
    st.markdown("<div class='log-container'>", unsafe_allow_html=True)
    st.code(bot_log_content, language="text")
    st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        user_search = st.text_input("Filter user logs (case-insensitive):", key="user_search")
    
    with col2:
        user_activity_type = st.selectbox(
            "Filter by activity type:",
            ["All", "URL REQUEST", "VIDEO INFO", "FORMAT PREFERENCE", "DOWNLOAD START", 
             "DOWNLOAD COMPLETE", "DOWNLOAD FAILED", "PROCESSING ERROR"],
            key="user_activity_type"
        )
    
    # Get log content
    user_log_content = get_log_content(user_log_path, max_lines=500)
    
    # Apply filters
    if user_search:
        filtered_lines = [line for line in user_log_content.split('\n') 
                         if user_search.lower() in line.lower()]
        user_log_content = '\n'.join(filtered_lines)
    
    if user_activity_type != "All":
        filtered_lines = [line for line in user_log_content.split('\n') 
                         if f" | {user_activity_type} | " in line]
        user_log_content = '\n'.join(filtered_lines)
    
    # Display logs
    st.markdown("<div class='log-container'>", unsafe_allow_html=True)
    st.code(user_log_content, language="text")
    st.markdown("</div>", unsafe_allow_html=True)

# Bot information
st.markdown("<h2 class='sub-header'>ℹ️ Bot Information</h2>", unsafe_allow_html=True)

with st.expander("About This Bot"):
    st.markdown("""
    ### Telegram YouTube Downloader Bot
    
    This bot allows users to download videos from various platforms through Telegram.
    
    **Supported Platforms:**
    - YouTube
    - TikTok
    - Instagram
    - Twitter/X
    - Facebook
    - And many more!
    
    **Features:**
    - Download videos in different quality options
    - Extract audio from videos
    - Automatic format selection
    - Support for playlists
    - Automatic yt-dlp updates
    
    **Bot Commands:**
    - `/start` - Start the bot
    - `/help` - Show help information
    
    **How It Works:**
    1. User sends a video URL to the bot
    2. Bot extracts video information
    3. User selects format (video/audio) and quality
    4. Bot downloads and sends the file to the user
    """)

with st.expander("Streamlit Cloud Deployment Guide"):
    st.markdown("""
    ### Deploying on Streamlit Cloud
    
    **Important Limitations:**
    
    Streamlit Cloud has limitations that affect how this bot can be deployed:
    
    1. **Process Management**: Streamlit Cloud doesn't allow long-running background processes
    2. **File System**: The file system is ephemeral and resets between sessions
    3. **Resource Limits**: CPU and memory are limited
    
    **Recommended Deployment Strategy:**
    
    1. **Run the bot separately** on a dedicated server (VPS, Heroku, etc.)
    2. **Use this dashboard** to monitor logs and statistics
    3. **Share logs** between the bot and this dashboard using a shared database or API
    
    **Alternative Approach:**
    
    If you want to run everything on Streamlit Cloud:
    
    1. Modify the bot to run as a serverless function
    2. Use a database service for storing logs and statistics
    3. Create API endpoints for controlling the bot
    
    For full functionality, consider hosting on a VPS provider like DigitalOcean, Linode, or AWS.
    """)

with st.expander("Usage Instructions"):
    st.markdown("""
    ### How to Use the Bot
    
    1. **Start the bot** using the START BOT button in the sidebar
    2. **Open Telegram** and search for your bot by username
    3. **Send a URL** to the bot from any supported platform
    4. **Select format** (video or audio) when prompted
    5. **Choose quality** from the available options
    6. **Wait for download** to complete
    7. **Receive the file** directly in your Telegram chat
    
    ### Monitoring
    
    Use this dashboard to:
    - Monitor bot status
    - View download statistics
    - Check logs for errors
    - Track user activity
    
    ### Troubleshooting
    
    If the bot stops responding:
    1. Check the Bot Log for errors
    2. Stop and restart the bot using the sidebar controls
    3. Ensure your system has internet connectivity
    """)

