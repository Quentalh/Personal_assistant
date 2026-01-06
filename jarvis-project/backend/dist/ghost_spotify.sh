#!/bin/bash

# 1. Kill any existing Spotify or Xvfb to start fresh
killall spotify
killall Xvfb

# 2. Start the Virtual Screen :99 in the background
# 1024x768 is big enough for the app
Xvfb :99 -screen 0 1024x768x24 &

# Give it 1 second to start
sleep 1

# 3. Start Spotify inside that invisible screen
export DISPLAY=:99
spotify &

echo "👻 Ghost Spotify started on Display :99"
