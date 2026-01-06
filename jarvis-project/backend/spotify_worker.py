import sys
import time
import pyautogui
import os

# Force this script to see ONLY the Ghost Screen
os.environ['DISPLAY'] = ':99'

if len(sys.argv) > 1:
    song_name = " ".join(sys.argv[1:])
else:
    sys.exit()

try:
    # 1. Search
    pyautogui.click(500, 50) # Click Search Bar (Top Center)
    pyautogui.hotkey('ctrl', 'l') 
    time.sleep(0.5)
    
    pyautogui.write(song_name, interval=0.1)
    pyautogui.press('enter')
    time.sleep(2.0) # Wait for results to load
    
    # 2. CLICK THE "TOP RESULT" (Bullseye Method)
    # Based on your screenshot, (300, 300) hits the center of the "Top Result" card
    pyautogui.doubleClick(300, 300)
    
    # Backup: Sometimes focus is weird, so we press Enter too
    time.sleep(0.5)
    pyautogui.press('enter')
        
except Exception as e:
    print(f"Error in ghost worker: {e}")