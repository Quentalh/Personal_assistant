import sys
import os
import subprocess
import time

def ensure_ghost_environment():
    """Checks if the Ghost Screen (:99) is running. If not, starts it."""
    print("👻 Checking Ghost Environment...")
    
    # 1. Check if Display :99 is active using xdpyinfo
    # We send output to DEVNULL to keep the terminal clean
    check = subprocess.run(
        "xdpyinfo -display :99", 
        shell=True, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL
    )
    
    if check.returncode == 0:
        print("✅ Ghost Environment is already running.")
        return
    
    print("❌ Ghost not found. Starting it now...")
    
    # 2. Find the script path relative to the executable
    if getattr(sys, 'frozen', False):
        # If running as compiled Jarvis app
        base_path = os.path.dirname(sys.executable)
    else:
        # If running as python script
        base_path = os.path.dirname(os.path.abspath(__file__))

    script_path = os.path.join(base_path, "ghost_spotify.sh")
    
    # 3. Launch the script
    if os.path.exists(script_path):
        try:
            # We use Popen so it runs in the background
            subprocess.Popen([script_path], cwd=base_path)
            
            # Give it 5 seconds to boot up Xvfb and Spotify
            print("⏳ Waiting 5s for Spotify to load...")
            time.sleep(5) 
            print("✅ Ghost Environment Started!")
        except Exception as e:
            print(f"⚠️ Failed to start script: {e}")
    else:
        print(f"⚠️ Could not find script at: {script_path}")
        print("Please make sure ghost_spotify.sh is in the same folder as Jarvis.")

import datetime
import threading
import re
from flask import Flask, send_from_directory
from flask_socketio import SocketIO
import webview  # The GUI engine
import speech_recognition as sr
from gtts import gTTS
import pygame
import pyautogui
import pytesseract
from PIL import Image, ImageOps
from interpreter import interpreter

# --- CONFIGURATION ---
interpreter.offline = True
interpreter.llm.model = "ollama/llama3"
interpreter.llm.api_base = "http://localhost:11434"
interpreter.auto_run = True
interpreter.custom_instructions = "My terminal is Zsh. Always use 'gtk-launch' for GUI apps."

# --- HELPER: FIX PATHS FOR FROZEN APP ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- FLASK SETUP ---
# We use resource_path to find the 'gui' folder safely
gui_folder = resource_path('gui')

app = Flask(__name__, static_folder=gui_folder, static_url_path='')
# Force async_mode to 'eventlet' to prevent errors
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

# Global Event to signal stopping
stop_event = threading.Event()

# --- HELPER: EMIT STATUS TO REACT ---
def change_status(status):
    print(f"📡 STATUS: {status}")
    socketio.emit('status_update', {'status': status})

# --- AUDIO ---
def speak(text):
    if stop_event.is_set(): return
    change_status("SPEAKING")
    
    try:
        print(f"🗣️ Speaking: {text}")
        tts = gTTS(text=text, lang='en', tld='co.uk')
        filename = "voice.mp3"
        tts.save(filename)
        
        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            if stop_event.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.1)
        
        pygame.mixer.quit()
        if os.path.exists(filename): os.remove(filename)
    except Exception as e:
        print(f"(TTS Error: {e})")
    
    change_status("IDLE")

# --- LISTENING ---
def listen_for_wakeword():
    change_status("HIDDEN")
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        r.pause_threshold = 0.8  
        print("\n💤 Waiting for 'Hey Jarvis'...")
        while True:
            try:
                audio = r.listen(source, timeout=None, phrase_time_limit=8)
                text = r.recognize_google(audio, language='en-US').lower()
                if "hey jarvis" in text:
                    return text
            except:
                continue

def listen_for_command():
    change_status("LISTENING")
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        r.pause_threshold = 2.0  
        r.dynamic_energy_threshold = True 
        
        print("👂 Listening (Patient Mode)...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=None)
            change_status("THINKING")
            return r.recognize_google(audio, language='en-US').lower()
        except sr.WaitTimeoutError:
            return None
        except:
            return None

# --- VISION ---
def scan_screen_for_text(target_word):
    try:
        screenshot = pyautogui.screenshot()
        gray_image = screenshot.convert('L')
        inverted_image = ImageOps.invert(gray_image)
        screen_text = pytesseract.image_to_string(inverted_image).lower()
        if target_word.lower() in screen_text:
            return True
        else:
            return False
    except Exception as e:
        print(f"Vision Error: {e}")
        return False

# --- LOGIC BRAIN ---
def execute_task(command):
    if stop_event.is_set(): return
    print(f"⚙️ Processing: {command}")
    change_status("THINKING")

    # 1. VOLUME
    if any(trigger in command for trigger in ["volume", "audio", "mute", "unmute"]):
        numbers = re.findall(r'\d+', command)
        if numbers:
            level = numbers[0]
            if int(level) > 120: level = "120"
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
            speak(f"Volume set to {level} percent.")
            return

        if "unmute" in command:
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            speak("Unmuted.")
            return
            
        if "mute" in command:
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
            speak("Muted.")
            return

        if "up" in command or "increase" in command:
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"])
            speak("Volume up.")
            return

        if "down" in command or "decrease" in command:
            subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"])
            speak("Volume down.")
            return
        return

    # 2. MEDIA
    if "resume" in command:
        if any(w in command for w in ["spotify", "music"]):
             subprocess.Popen(["playerctl", "-p", "spotify", "play"])
             speak("Resuming Spotify.")
        else:
             subprocess.Popen(["playerctl", "play"])
        return

    if "pause" in command:
        if any(w in command for w in ["spotify", "music"]):
             subprocess.Popen(["playerctl", "-p", "spotify", "pause"])
             speak("Pausing Spotify.")
        else:
             subprocess.Popen(["playerctl", "pause"])
        return

    if "next" in command or "skip" in command:
        subprocess.Popen(["playerctl", "next"])
        speak("Next.")
        return

# 3. SPOTIFY SEARCH (GHOST WORKER METHOD)
    if "play" in command and "spotify" in command:
        song_name = command.replace("play", "").replace("on spotify", "").strip()
        speak(f"Queuing {song_name}")
        
        try:
            # SMART PATH FIX:
            # 1. Get the folder where the running 'Jarvis' executable lives
            if getattr(sys, 'frozen', False):
                # If running as compiled app (PyInstaller)
                application_path = os.path.dirname(sys.executable)
            else:
                # If running as python script
                application_path = os.path.dirname(os.path.abspath(__file__))

            # 2. Combine with the worker name
            worker_path = os.path.join(application_path, "spotify_worker")
            
            # 3. Run it
            subprocess.Popen(
                [worker_path, song_name],
                env={**os.environ, "DISPLAY": ":99"} 
            )
        except Exception as e:
            print(f"Failed to launch worker: {e}")
            speak("I couldn't start the background task.")
        return

    # 4. MATH
    math_triggers = ["calculate", "what is", "what's", "how much is"]
    if any(t in command for t in math_triggers):
        expression = command
        for t in math_triggers: expression = expression.replace(t, "")
        expression = expression.replace("times", "*").replace("x", "*")
        expression = expression.replace("divided by", "/").replace("plus", "+").replace("minus", "-")
        safe = "0123456789.+-*/ "
        expression = "".join([c for c in expression if c in safe])
        try:
            result = eval(expression)
            speak(f"The result is {result}")
        except:
            pass
        return

    # 5. APP LAUNCHER
    triggers = ["open ", "launch ", "start "]
    matched_trigger = next((t for t in triggers if command.startswith(t)), None)
    if matched_trigger:
        raw_app_name = command.replace(matched_trigger, "").strip()
        app_map = {
            "calculator": ["/usr/bin/gnome-calculator", "calculator"],
            "firefox": ["firefox-developer-edition", "firefox"],
            "fire": ["firefox-developer-edition", "firefox"],
            "browser": ["firefox-developer-edition", "firefox"],
            "terminal": ["gnome-terminal", "heitor"], 
            "files": ["nemo", "home"], 
            "spotify": ["spotify", "spotify"],
            "whatsapp": ["flatpak run com.rtosta.zapzap", "whatsapp"]
        }
        if raw_app_name in app_map:
            cmd, visual_keyword = app_map[raw_app_name]
            subprocess.Popen(cmd, shell=True)
            speak("Checking visual feed...")
            
            app_found = False
            for attempt in range(5):
                time.sleep(2.0)
                if scan_screen_for_text(visual_keyword):
                    app_found = True
                    speak(f"I see {visual_keyword}.")
                    break
            if not app_found:
                speak(f"I opened it, but I don't see the {visual_keyword} window yet.")
            return

    # 6. AI BRAIN (Fallback)
    try:
        now = datetime.datetime.now().strftime("%H:%M")
        prompt = f"(System: Time is {now}) {command}"
        if not stop_event.is_set():
            interpreter.chat(prompt)
    except:
        pass

# --- MAIN LOOP ---
def jarvis_main_loop():
    print("🧠 JARVIS BRAIN ONLINE")
    #speak("System Online.")
    socketio.emit('status', {'status': 'IDLE', 'text': ''})
    
    while True:
        stop_event.clear()
        wakeword_text = listen_for_wakeword()
        
        command = wakeword_text.replace("hey jarvis", "").strip()
        if not command:
            speak("Yes?")
            command = listen_for_command()
        
        if not command:
            change_status("HIDDEN")
            continue

        execute_task(command)
        change_status("HIDDEN")

def start_flask():
    ensure_ghost_environment()
    # ADD allow_unsafe_werkzeug=True TO FIX THE CRASH
    socketio.run(app, port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    # 1. Start Threads
    t_logic = threading.Thread(target=jarvis_main_loop)
    t_logic.daemon = True
    t_logic.start()
    
    t_server = threading.Thread(target=start_flask)
    t_server.daemon = True
    t_server.start()

    # --- ADD THIS DELAY ---
    print("⏳ Waiting for server to start...")
    time.sleep(2.0)  # Gives Flask 2 seconds to initialize port 5000
    # ----------------------

    # 2. Debug Information
    print("🚀 Launching Jarvis...")
    if os.path.exists(gui_folder):
        print(f"✅ GUI Path found: {gui_folder}")
    else:
        print(f"❌ ERROR: GUI Path NOT found at: {gui_folder}")

    # 3. Define Window Size
    ORB_WIDTH = 200
    ORB_HEIGHT = 200
    
    # Define Icon Path


    # 4. Create Window
    window = webview.create_window(
        'Jarvis', 
        'http://127.0.0.1:5000',  # Now this URL should be ready!
        width=ORB_WIDTH,
        height=ORB_HEIGHT,
        transparent=True,
        frameless=True,
        on_top=True,
    )

    # 5. Snap to Right Logic
    def move_to_right():
        time.sleep(1) 
        try:
            screens = webview.screens
            screen = screens[0]
            x_pos = screen.width - ORB_WIDTH
            y_pos = (screen.height - ORB_HEIGHT) // 2
            window.move(int(x_pos), int(y_pos))
        except Exception as e:
            print(f"❌ Could not move window: {e}")

    # 6. START
    webview.start(func=move_to_right, debug=False)
    os._exit(0)