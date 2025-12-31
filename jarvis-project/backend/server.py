import sys
import os
import threading
import time
import subprocess
import datetime
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

    # 3. SPOTIFY SEARCH
    if "play" in command and "spotify" in command:
        song_name = command.replace("play", "").replace("on spotify", "").strip()
        speak(f"Searching for {song_name}")
        try:
            game_window_id = subprocess.check_output(["xdotool", "getactivewindow"]).strip().decode()
            subprocess.Popen(["gtk-launch", "spotify"])
            time.sleep(1.5)
            pyautogui.hotkey('ctrl', 'l')
            pyautogui.write(song_name, interval=0.05)
            pyautogui.press('enter')
            time.sleep(0.5)
            pyautogui.press('enter')
            subprocess.Popen(["xdotool", "windowactivate", game_window_id])
        except:
            speak("Error switching windows.")
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
            "spotify": ["spotify", "spotify"]
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
    socketio.run(app, port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # 1. Start Threads
    t_logic = threading.Thread(target=jarvis_main_loop)
    t_logic.daemon = True
    t_logic.start()
    
    t_server = threading.Thread(target=start_flask)
    t_server.daemon = True
    t_server.start()

    # 2. Debug Information
    print("🚀 Launching DEBUG Window...")
    if os.path.exists(gui_folder):
        print(f"✅ GUI Path found: {gui_folder}")
        print(f"📂 Files inside: {os.listdir(gui_folder)}")
    else:
        print(f"❌ ERROR: GUI Path NOT found at: {gui_folder}")

    # 3. Create Window (Production Mode)
    # Changed title from 'Jarvis DEBUG' to 'Jarvis'
    # You can change transparent=True and frameless=True later if you want the "Orb" look
    # 3. Create Window (Siri Mode)
    window = webview.create_window(
        'Jarvis', 
        'http://127.0.0.1:5000',
        width=800,
        height=600,
        transparent=True,    # <--- Critical for Orb look
        frameless=True,      # <--- Removes borders
        on_top=True          # <--- Keeps it above everything
    )

    # 4. START THE APP (Production Mode)
    # debug=False disables the Inspection/Right-Click menu
    webview.start(debug=False)