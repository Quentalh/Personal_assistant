import tkinter as tk
import threading
import speech_recognition as sr
from gtts import gTTS
import os
import time
import pygame
import datetime
import subprocess
import pyautogui
import pytesseract
import re
from PIL import Image, ImageOps
from interpreter import interpreter

# --- CONFIGURATION ---
interpreter.offline = True
interpreter.llm.model = "ollama/llama3"
interpreter.llm.api_base = "http://localhost:11434"
interpreter.auto_run = True
interpreter.custom_instructions = "My terminal is Zsh. Always use 'gtk-launch' for GUI apps."

# Global Control Flags
stop_event = threading.Event()
ui_state = "HIDDEN"  # States: HIDDEN, LISTENING, THINKING, SPEAKING

# --- THE GUI CLASS (Linux Compatible) ---
class JarvisUI:
    def __init__(self):
        self.root = tk.Tk()
        # Remove window borders
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        
        # LINUX FIX: Use overall transparency instead of color-keying
        self.root.attributes('-alpha', 0.7)  
        self.root.configure(bg='black')
        
        # Position in bottom-right corner
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"120x120+{screen_width-150}+{screen_height-150}")
        
        # Create the canvas
        self.canvas = tk.Canvas(self.root, width=120, height=120, bg='black', highlightthickness=0)
        self.canvas.pack()
        
        # Draw the Status Ball
        self.ball = self.canvas.create_oval(20, 20, 100, 100, fill="black", outline="white", width=2)
        
        self.label = tk.Label(self.root, text="OFFLINE", bg="black", fg="white", font=("Arial", 8))
        self.label.pack()

        # Start the updater loop
        self.update_ui()
        self.root.withdraw() # Start hidden
        self.root.mainloop()

    def update_ui(self):
        global ui_state
        
        if ui_state == "HIDDEN":
            self.root.withdraw()
        else:
            self.root.deiconify()
            if ui_state == "LISTENING":
                self.canvas.itemconfig(self.ball, fill="#00FF00") # Green
                self.label.config(text="LISTENING")
            elif ui_state == "THINKING":
                self.canvas.itemconfig(self.ball, fill="#0000FF") # Blue
                self.label.config(text="THINKING")
            elif ui_state == "SPEAKING":
                self.canvas.itemconfig(self.ball, fill="#FF0000") # Red
                self.label.config(text="SPEAKING")
        
        self.root.after(100, self.update_ui)

# --- AUDIO FUNCTIONS ---
def speak(text):
    global ui_state
    if stop_event.is_set(): return
    
    prev_state = ui_state
    ui_state = "SPEAKING" 
    
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
    
    ui_state = prev_state 

def listen_for_wakeword():
    global ui_state
    ui_state = "HIDDEN"
    
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
    global ui_state
    ui_state = "LISTENING"
    
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        r.pause_threshold = 2.0  
        r.dynamic_energy_threshold = True 
        
        print("👂 Listening (I am being patient)...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=None)
            ui_state = "THINKING"
            return r.recognize_google(audio, language='en-US').lower()
        except:
            return None

# --- VISION ---
def scan_screen_for_text(target_word):
    try:
        screenshot = pyautogui.screenshot()
        gray_image = screenshot.convert('L')
        inverted_image = ImageOps.invert(gray_image)
        screen_text = pytesseract.image_to_string(inverted_image).lower()
        return target_word.lower() in screen_text
    except:
        return False

# --- LOGIC BRAIN ---
def execute_task(command):
    global ui_state
    if stop_event.is_set(): return
    print(f"⚙️ Processing: {command}")
    
    # 1. VOLUME CONTROLS
    if "volume" in command:
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

    # 2. MEDIA (Targeted & General)
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

    # 5. APP LAUNCHER (With Vision)
    triggers = ["open ", "launch ", "start "]
    matched_trigger = next((t for t in triggers if command.startswith(t)), None)
    if matched_trigger:
        raw_app_name = command.replace(matched_trigger, "").strip()
        app_map = {
            "calculator": ["/usr/bin/gnome-calculator", "calculator"],
            "firefox": ["firefox-developer-edition", "firefox"],
            "browser": ["firefox-developer-edition", "firefox"],
            "terminal": ["gnome-terminal", "heitor"], 
            "files": ["nemo", "home"], 
            "spotify": ["spotify", "spotify"]
        }
        if raw_app_name in app_map:
            cmd, visual_keyword = app_map[raw_app_name]
            subprocess.Popen(cmd, shell=True)
            speak("Checking visual feed...")
            
            # Smart Wait Loop
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

# --- MAIN THREAD ---
def jarvis_logic():
    global ui_state
    speak("System Online.")
    
    while True:
        stop_event.clear()
        
        # 1. Wait (Hidden)
        wakeword_text = listen_for_wakeword()
        
        # 2. Wake Up (Show Ball)
        command = wakeword_text.replace("hey jarvis", "").strip()
        if not command:
            speak("Yes?")
            command = listen_for_command()
        
        if not command:
            ui_state = "HIDDEN"
            continue

        # 3. Execute
        ui_state = "THINKING"
        t_exec = threading.Thread(target=execute_task, args=(command,))
        t_exec.start()
        t_exec.join()
        
        # 4. Hide Ball
        ui_state = "HIDDEN"

# --- LAUNCHER ---
if __name__ == "__main__":
    t = threading.Thread(target=jarvis_logic)
    t.daemon = True 
    t.start()
    
    app = JarvisUI()