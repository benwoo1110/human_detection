# import the necessary packages

# Video capture
from imutils.video import VideoStream
import imutils
import threading
import argparse
import numpy as np
import cv2

# Time
import datetime
import time

# Web
from flask import Response, Flask, render_template, request
import json
import jsonify
import socket

# Python files
from singlemotiondetector import SingleMotionDetector
from database import Database


#
# initialize a flask object
#
app = Flask(__name__)

# Grep device ip
ip_address = ''
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    ip_address = s.getsockname()[0]
    s.close()

except:
    print("No network avaliable.")
    ip_address = "127.0.1.1"

#
# Video feed
#
# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful when multiple browsers/tabs
# are viewing the stream)
outputFrame = None
lock = threading.Lock()

data_all = {"time":[], "duration":[], "num_today":[]}

# initialize the video stream and allow the camera sensor to warmup
vs = cv2.VideoCapture(0)
vs.set(3,800)
vs.set(4,600)

time.sleep(2.0)

def detect_motion(frameCount):
    # grab global references to the video stream, output frame, and
    # lock variables
    global  vs, outputFrame, lock, data_all

    # initialize the motion detector and the total number of frames
    # read thus far
    md = SingleMotionDetector(accumWeight=0.25)

    enter_image = ""
    curr_data = {"year":" ", "month":" ", "day":" ", "time":" ", "duration":" "}
    total = 0
    counter = 0
    time_in_motion = 0
    time_in_toliet = 0
    movement = []
    in_toliet = "Unoccupied"
    hit_box = [400, 0, 800, 640]
    # loop over frames from the video stream
    while True:
	# read the next frame from the video stream, resize it,
	# convert the frame to grayscale, and blur it
        ret, frame = vs.read()

        # frame = imutils.rotate(frame, 180)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)

	# grab the current timestamp and draw it on the frame
        timestamp = datetime.datetime.now()
        cv2.putText(frame, timestamp.strftime("%A %d %B %Y %I:%M:%S%p"), (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

	# show status of toliet
        cv2.putText(frame, in_toliet, (20, frame.shape[0] - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

	# show toliet entry detection area
        cv2.rectangle(frame, tuple(hit_box[:2]), tuple(hit_box[2:]), (255, 0, 255), 2)

	# if the total number of frames has reached a sufficient
	# number to construct a reasonable background model, then
	# continue to process the frame
        if total > frameCount:
	    # detect motion in the image
            motion = md.detect(gray)

	    # check to see if motion was found in the frame
            if motion is not None:
                counter = 0
                if len(movement) == 0: time_in_motion = time.time()

		# unpack the tuple of movement frame
		# "motion area" on the output frame
                (thresh, (minX, minY, maxX, maxY)) = motion

		# Only show if movement more than 500 unit^2 to prevent false detections
                if (maxX-minX)*(maxY-minY) > 500:
                    cv2.rectangle(frame, (minX, minY), (maxX, maxY), (0, 0, 255), 2)

		    # Save movement history
                    movement.append(((minX+maxX)//2, (minY+maxY)//2))

            else:
                counter += 1
		# Threshold incase of missed detection
                if counter > 5:
                    if time.time()-time_in_motion > 0.3:

			# Entered room
                        if len(movement) != 0 and hit_box[0] < movement[-1][0] < hit_box[2] and hit_box[1] < movement[-1][1] < hit_box[3]:
                            # If exited detection is missed:
                            if in_toliet == "Occupied":
                                Database.add_data(str(curr_data["year"]), str(curr_data["month"]), str(curr_data["day"]), str(curr_data["time"]), str('-1'))
                                # Database.read_data()

                            print("entered")
                            in_toliet = "Occupied"
                            time_in_toliet = time.time()

                            curr_data["year"] = time.strftime("%Y")
                            curr_data["month"] = timestamp.strftime("%m")
                            curr_data["day"] = timestamp.strftime("%e")
                            curr_data["time"] = timestamp.strftime("%R")

			# Exited room
                        if len(movement) != 0 and hit_box[0] < movement[0][0] < hit_box[2] and hit_box[1] < movement[0][1] < hit_box[3]:
                            if in_toliet == "Unoccupied":
                                curr_data["year"] = time.strftime("%Y")
                                curr_data["month"] = timestamp.strftime("%m")
                                curr_data["day"] = timestamp.strftime("%e")
                                curr_data["time"] = timestamp.strftime("%R")
                                Database.add_data(str(curr_data["year"]), str(curr_data["month"]), str(curr_data["day"]), str(curr_data["time"]), str('-2'))
                                Database.read_data()

                            print("exited")
                            curr_data["duration"] = int(time.time() - time_in_toliet)

                            if in_toliet == "Occupied":
                                # Only save if duration is more that 5 second
                                if curr_data["duration"] > 8:
                                    Database.add_data(str(curr_data["year"]), str(curr_data["month"]), str(curr_data["day"]), str(curr_data["time"]), str(curr_data["duration"]))
                                    Database.read_data()

                            in_toliet = "Unoccupied"

                    counter, movement = 0, []

	# Show movement history
        movement_points = len(movement)
        for points in range(0, movement_points, 3):
            if points > 0:
                cv2.line(frame, movement[points-3], movement[points], (0, 255, 0), 2)

	# update the background model and increment the total number
	# of frames read thus far
        md.update(gray)
        total += 1

	# acquire the lock, set the output frame, and release the
	# lock
        with lock:
            outputFrame = frame.copy()

def generate():
	# grab global references to the output frame and lock variables
	global outputFrame, lock

	# loop over frames from the output stream
	while True:
		# wait until the lock is acquired
		with lock:
			# check if the output frame is available, otherwise skip
			# the iteration of the loop
			if outputFrame is None:
				continue

			# encode the frame in JPEG format
			(flag, encodedImage) = cv2.imencode(".jpg", outputFrame)

			# ensure the frame was successfully encoded
			if not flag:
				continue

		# yield the output frame in the byte format
		yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
			bytearray(encodedImage) + b'\r\n')

@app.route("/video_feed")
def video_feed():
	# return the response generated along with the specific media
	# type (mime type)
	return Response(generate(),
		mimetype = "multipart/x-mixed-replace; boundary=frame")


#
# Testing request sending
#
@app.route('/data', methods = ['POST', 'GET'])
def data():
    global data_all

    if request.method == 'POST':
        data = request.get_json()

        print (data)
        return "connected"

    if request.method == 'GET':
        return Database.send_data()


#
# check to see if this is the main thread of execution
#
if __name__ == '__main__':
	# start a thread that will perform motion detection
	t = threading.Thread(target=detect_motion, args=(
		32,))
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host=ip_address, port=5000, debug=True, threaded=True, use_reloader=False)


#
# Progam ended
#
# release the video stream pointer
#vs.stop()
