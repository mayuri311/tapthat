import cv2
import numpy as np
import socket
import math
from picamera2 import Picamera2

# ==========================================
# 1. NETWORK SETTINGS (MATCH YOUR PC)
# ==========================================
SERVER_IP = '172.26.79.103'  # <--- CHANGE THIS to your PC's IP
SERVER_PORT = 65432

# ==========================================
# 2. CAMERA & TRACKING CONFIGURATION
# ==========================================
BASELINE = 45.4    # mm (Distance between lens centers)
FOCAL_LEN = 530.0  # pixels
RES_X, RES_Y = 1280, 720
CENTER_X, CENTER_Y = RES_X/2, RES_Y/2

# IR OPTIMIZATION
IR_EXPOSURE = 2000 # microseconds (2ms). Lower = Darker/Sharper.
IR_GAIN = 1.0
THRESHOLD = 60     # Brightness threshold (0-255)

# INTERACTION SETTINGS
HIT_RADIUS = 8.0  # mm (How close to trigger hover)
TOGGLE_KEY = 9     # TAB key
TRIGGER_KEY = 32   # SPACEBAR (Later: replace with contact sensor)

# ==========================================
# 3. HELPER FUNCTIONS (VISION & MATH)
# ==========================================

def init_cameras():
    """Sets up stereo cameras with IR optimizations."""
    print("   ...Initializing Cameras...")
    cam0 = Picamera2(0)
    cam1 = Picamera2(1)
    
    config = cam0.create_video_configuration(main={"size": (RES_X, RES_Y)})
    cam0.configure(config)
    cam1.configure(config)
    
    cam0.start()
    cam1.start()
    
    # LOCK EXPOSURE (The "Sunglasses" Trick)
    controls = {"AnalogueGain": IR_GAIN, "ExposureTime": IR_EXPOSURE}
    cam0.set_controls(controls)
    cam1.set_controls(controls)
    
    return cam0, cam1

def find_led_center(frame):
    """Finds brightest spot using RED channel (IR sensitive)."""
    # optimization: Extract only Red Channel
    gray = frame[:, :, 2]
    
    _, thresh = cv2.threshold(gray, THRESHOLD, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours: return None
    leds = []
    largest = max(contours, key=cv2.contourArea)
    M = cv2.moments(largest)
    
    # Filter tiny noise
    if M["m00"] > 5:
        u = int(M["m10"] / M["m00"])
        v = int(M["m01"] / M["m00"])
        brightness = M["m00"]
        leds.append((u, v, brightness))
    leds.sort(key=lambdra x: x[2], reverse=True)
    topfive = leds[:5]
    topfive.sort(key=lambda x: x[0])
    return [(b[0], b[1]) for b in topfive]

def calculate_depth(pL, pR):
    """Triangulates 3D position (x, y, z) in mm."""
    if pL is None or pR is None: return None
    
    uL, vL = pL
    uR, vR = pR
    
    disparity = abs(uL - uR)
    if disparity < 1: disparity = 0.1
    
    Z = (FOCAL_LEN * BASELINE) / disparity
    X = (Z * (uL - CENTER_X)) / FOCAL_LEN
    Y = (Z * (vL - CENTER_Y)) / FOCAL_LEN
    
    return (X, Y, Z)

def get_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)

def find_best_match(current_pos, database):
    """Finds nearest key in the database."""
    if not database: return None, None

    closest_key = None
    min_dist = 99999.0

    for key_char, saved_pos in database.items():
        dist = get_distance(current_pos, saved_pos)
        if dist < min_dist:
            min_dist = dist
            closest_key = key_char

    if min_dist < HIT_RADIUS:
        return closest_key, min_dist
    return None, min_dist

# ==========================================
# 4. MAIN PROGRAM
# ==========================================

# State Variables
KEY_DATABASE = {} 
mode = "RECORDING"

print("------------------------------------------------")
print("   GHOST GLOVE - STANDALONE CLIENT")
print("------------------------------------------------")

# A. Start Vision System
try:
    cam0, cam1 = init_cameras()
except Exception as e:
    print(f"CRITICAL ERROR: Camera failed to start. {e}")
    exit()

# B. Connect to Windows PC
print(f"   ...Connecting to PC at {SERVER_IP}:{SERVER_PORT}")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((SERVER_IP, SERVER_PORT))
    print("   ✅ CONNECTED!")
except Exception as e:
    print(f"   ❌ NETWORK ERROR: {e}")
    print("   (Proceeding in offline mode...)")
    sock = None

print("------------------------------------------------")
print(" [ RECORDING MODE ]")
print("   - Hover finger, press KEY (e.g. 'a') to save.")
print("   - Press TAB to switch modes.")
print(" [ TYPING MODE ]")
print("   - Hover finger, press SPACEBAR to click.")
print("------------------------------------------------")

try:
    while True:
        # 1. Capture
        frame0 = cam0.capture_array()
        frame1 = cam1.capture_array()
        
        # Flip (-1 = 180 degrees)
        frame0 = cv2.flip(frame0, -1)
        frame1 = cv2.flip(frame1, -1)
        
        # 2. Track
        posL = find_led_center(frame0)
        posR = find_led_center(frame1)
        current_pos = calculate_depth(posL, posR)
        
        # 3. Input & Logic
        key_code = cv2.waitKey(1) & 0xFF
        
        # Prepare UI
        combined = np.hstack((frame0, frame1))
        ui_color = (255, 255, 0)
        status_line = "No Finger"

        if current_pos:
            # Draw markers
            if posL: cv2.circle(frame0, posL, 10, (0, 255, 255), 2)
            if posR: cv2.circle(frame1, posR, 10, (0, 255, 255), 2)

            # --- RECORDING LOGIC ---
            if mode == "RECORDING":
                ui_color = (0, 165, 255) # Orange
                status_line = f"Recording... ({len(KEY_DATABASE)} saved)"
                
                if key_code == TOGGLE_KEY:
                    mode = "TYPING"
                    print(">>> SWITCHED TO TYPING MODE")
                
                # Check for valid key press (a-z, 0-9) to save position
                elif key_code != 255 and key_code != 27 and key_code != 32:
                    char = chr(key_code)
                    KEY_DATABASE[char] = current_pos
                    print(f"Saved Key: '{char}'")

            # --- TYPING LOGIC ---
            elif mode == "TYPING":
                ui_color = (0, 255, 0) # Green
                
                hover_key, dist = find_best_match(current_pos, KEY_DATABASE)
                
                if hover_key:
                    status_line = f"HOVER: [ {hover_key.upper()} ]"
                    
                    # >>> TRIGGER SIGNAL <<<
                    # Currently: SPACEBAR (32). Later: CONTACT SENSOR.
                    if key_code == TRIGGER_KEY:
                        print(f"--> CLICK! Sent: {hover_key}")
                        if sock:
                            try:
                                sock.sendall(hover_key.encode('utf-8'))
                                cv2.putText(combined, "SENT!", (600, 200), 
                                           cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 4)
                            except:
                                print("Socket disconnected.")
                else:
                    status_line = "Hovering..."
                    ui_color = (100, 100, 100)

                if key_code == TOGGLE_KEY:
                    mode = "RECORDING"

        # 4. Draw UI
        cv2.rectangle(combined, (0, 0), (1280, 120), (0, 0, 0), -1)
        cv2.putText(combined, f"MODE: {mode}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(combined, status_line, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, ui_color, 3)
        
        cv2.imshow("Ghost Glove", combined)
        
        if key_code == 27: # ESC
            break

finally:
    print("Shutting down...")
    if sock: sock.close()
    cam0.stop()
    cam1.stop()
    cv2.destroyAllWindows()
