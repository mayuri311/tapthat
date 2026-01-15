
import cv2
import numpy as np
from picamera2 import Picamera2

def find_light(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY) #dim
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    #returns list of contour shapes  with edges. largest white area is found. 
    # m00 is total area, m10 is sum of x coords, m01 is sum of y coords
    # u, v uses center formula
    blobs = []
    for c in contours:
        M = cv2.moments(c)
        largest = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest)
        if M["m00"] != 0:
            u = int(M["m10"]/M["m00"])
            v = int(M["m01"]/M["m00"])
            brightness = M["m00"]
            blobs.append((u, v, brightness))
    blobs.sort(key=lambda x: x[2], reverse=True)
    top_five = blobs[:5]
    top_five.sort(key=lambda x: x[0])
    # sort by brightness and then x coords so that finger[0] is leftmost
    return [(b[0], b[1]) for b in top_five]

def get3d(uL, vL, uR, vR):
    disparity = uL-uR
    print(f"Shift: {disparity} pixels")
    lp = np.array([[uL], [vL]])
    rp = np.array([[uR], [vR]])
    # triangulate function
    Z = (530.0 * 44.0) /disparity
    X = (Z*(uL-320.0))/530.0
    Y = (Z*(vL-240.0))/530.0
    return X, Y, Z

cam0 = Picamera2(0)
cam1 = Picamera2(1)

# constants!!!
B = 44.0
f = 530.0
Cx, Cy = 320, 240

# projection matrix
P1 = np.array([[f, 0, Cx, 0],
               [0, f, Cy, 0],
               [0, 0, 1, 0]])
P2 = np.array([[f, 0, Cx, -f*B],
               [0, f, Cy, 0],
               [0, 0, 1, 0]])

home_pos = None
threshold = 15 #mm to trigger key change

# low res
config = cam0.create_video_configuration(main={"size": (640, 480)})
cam0.configure(config)
cam1.configure(config)

cam0.start()
cam1.start()
home_pos = [None] * 5
deltas = [(0.0), (0.0)] * 5
# press q to quit window
print("place ir led in view and press c to calibrate home row")

try:
    while True:
        frame0 = cam0.capture_array()
        frame1 = cam1.capture_array()
       
        left_pix = find_light(frame0)
        right_pix = find_light(frame1)
        num_visible = min(len(left_pix), len(right_pix))
        text = "not calibrated yet"
        for i in range(num_visible):
            uL, vL = left_pix[i]
            uR, vR = right_pix[i]
            X, Y, Z = get3d(uL, vL, uR, vR)

            key = cv2.waitKey(1) & 0xFF
            if (key != 255): print("you pressed {key}")
            if key == ord('c'):
                home_pos[i] = (X,Y,Z)
                print(f"home of finger {i}  is: {home_pos[i]}")
            if home_pos[i]:
                dX, dY, dZ = float(X-home_pos[i][0]), float(Y-home_pos[i][1]), float(Z-home_pos[i][2])
                deltas[i] = (dX, dZ)
                '''text = f"MOVE: dX:{dX} dY:{dY} dZ:{dZ}"
                if dX>threshold: print("RIGHT")
                elif dX<-threshold: print("LEFT")
                if dZ > threshold: print("UP")
                elif dZ < -threshold: print("DOWN")'''
                if abs(dX) > 15 or abs(dZ) > 15:
                    print(f"FINGER {i} | dX: {int(dX)} dZ: {int(dZ)}")

        #font = cv2.FONT_HERSHEY_SIMPLEX
        combined = np.hstack((frame0, frame1))
        #cv2.putText(combined, text, (20, 35), font, 0.7, (0, 255, 0), 1)
        cv2.imshow("tracker", cv2.cvtColor(combined, cv2.COLOR_RGB2BGR))
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    cam0.stop()
    cam1.stop()
    cv2.destroyAllWindows()

