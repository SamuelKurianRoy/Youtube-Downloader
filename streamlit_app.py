import streamlit as st
import subprocess
import os
import signal
import time
import sys
from pathlib import Path

# Set page config
st.set_page_config(
    page_title="Telegram YouTube Downloader Bot",
    page_icon="🤖",
    layout="wide"
)

# Define paths
base_dir = Path(__file__).parent
logs_dir = base_dir / "logs"
bot_log_path = logs_dir / "bot.log"
user_log_path = logs_dir / "user.log"
bot_script_path = base_dir / "bot.py"

# Create logs directory if it doesn't exist
logs_dir.mkdir(exist_ok=True)

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
        return "Log file not found."
    except Exception as e:
        return f"Error reading log: {str(e)}"

def start_bot():
    """Start the bot process"""
    global bot_process
    if bot_process is None or bot_process.poll() is not None:
        try:
            # Start the bot as a subprocess
            bot_process = subprocess.Popen(
                [sys.executable, str(bot_script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            st.session_state.bot_running = True
            return True
        except Exception as e:
            st.error(f"Failed to start bot: {e}")
    return False

def stop_bot():
    """Stop the bot process"""
    global bot_process
    if bot_process is not None and bot_process.poll() is None:
        try:
            # Send SIGTERM signal to the process
            if os.name == 'nt':  # Windows
                bot_process.terminate()
            else:  # Unix/Linux
                os.kill(bot_process.pid, signal.SIGTERM)
            
            # Wait for process to terminate
            try:
                bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate
                if os.name == 'nt':
                    bot_process.kill()
                else:
                    os.kill(bot_process.pid, signal.SIGKILL)
            
            bot_process = None
            st.session_state.bot_running = False
            return True
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
    return False

# Initialize session state
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False

# Main app
st.title("Telegram YouTube Downloader Bot Control Panel")

# Status and control section
st.header("Bot Status")
col1, col2 = st.columns([1, 3])

with col1:
    status = "🟢 Running" if st.session_state.bot_running else "🔴 Stopped"
    st.subheader(status)
    
    if st.session_state.bot_running:
        if st.button("Stop Bot", type="primary"):
            if stop_bot():
                st.success("Bot stopped successfully!")
                time.sleep(1)
                st.rerun()
    else:
        if st.button("Start Bot", type="primary"):
            if start_bot():
                st.success("Bot started successfully!")
                time.sleep(1)
                st.rerun()

# Log section
st.header("Logs")
tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])

with tab1:
    st.subheader("Bot Log (Errors & System Messages)")
    
    # Add search filter
    bot_search = st.text_input("Filter bot logs (case-insensitive):", key="bot_search")
    
    # Add log level filter
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
    st.code(bot_log_content, language="text")

with tab2:
    st.subheader("User Activity Log")
    
    # Add search filter
    user_search = st.text_input("Filter user logs (case-insensitive):", key="user_search")
    
    # Add activity type filter
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
    st.code(user_log_content, language="text")

# Add log statistics
if st.checkbox("Show Log Statistics"):
    st.subheader("Log Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("Bot Log Statistics")
        
        # Count log entries by level
        if os.path.exists(bot_log_path):
            with open(bot_log_path, 'r', encoding='utf-8') as f:
                bot_logs = f.readlines()
                
            info_count = sum(1 for line in bot_logs if " - INFO - " in line)
            warning_count = sum(1 for line in bot_logs if " - WARNING - " in line)
            error_count = sum(1 for line in bot_logs if " - ERROR - " in line)
            
            st.write(f"INFO: {info_count}")
            st.write(f"WARNING: {warning_count}")
            st.write(f"ERROR: {error_count}")
    
    with col2:
        st.write("User Log Statistics")
        
        # Count user activity by type
        if os.path.exists(user_log_path):
            with open(user_log_path, 'r', encoding='utf-8') as f:
                user_logs = f.readlines()
            
            url_requests = sum(1 for line in user_logs if "URL REQUEST" in line)
            downloads_started = sum(1 for line in user_logs if "DOWNLOAD START" in line)
            downloads_completed = sum(1 for line in user_logs if "DOWNLOAD COMPLETE" in line)
            downloads_failed = sum(1 for line in user_logs if "DOWNLOAD FAILED" in line)
            
            st.write(f"URL Requests: {url_requests}")
            st.write(f"Downloads Started: {downloads_started}")
            st.write(f"Downloads Completed: {downloads_completed}")
            st.write(f"Downloads Failed: {downloads_failed}")
            
            if downloads_started > 0:
                success_rate = (downloads_completed / downloads_started) * 100
                st.write(f"Success Rate: {success_rate:.1f}%")

# Auto-refresh logs
if st.session_state.bot_running:
    if st.button("Refresh Logs"):
        st.rerun()

# Bot information
st.header("Bot Information")
st.markdown("""
This control panel allows you to start and stop the Telegram YouTube Downloader Bot.

**Features:**
- Download videos from YouTube, TikTok, Instagram, Twitter, and more
- Choose between video and audio formats
- Select different quality options
- Automatic yt-dlp updates

**Commands:**
- `/start` - Start the bot
- `/help` - Show help information
""")





