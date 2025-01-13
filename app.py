import cv2
from flask import Flask, render_template,request, Response, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Mengizinkan akses dari domain lain

locations = {
    "pasar": {"name": "Pasar", "lat": -7.915016, "lng": 113.827289},
    "mts_2": {"name": "MTS 2", "lat": -7.915497, "lng": 113.816206},
    "SD": {"name": "SD Dabasah", "lat": -7.913832, "lng": 113.820898},
    "SMP_1": {"name": "SMPN 1 Bondowoso", "lat": -7.912070, "lng": 113.822498},
    "SDK": {"name": "SDK", "lat": -7.917106, "lng": 113.822214},
}

def video_stream():
    # URL streaming HLS
    video_url = "https://camera.jtd.co.id/camera/share/tios/2/78/index.m3u8"
    video_yt="https://youtu.be/PFu3b_sFIak"
    # Membuka streaming video
    cap = cv2.VideoCapture(video_url)
    if not cap.isOpened():
        print("Error: Tidak dapat membuka video stream.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Stream selesai atau terputus.")
            break

        # Encode frame ke format JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Kirim frame ke browser
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route("/calculate_route", methods=["POST"])
def calculate_route():
    data = request.json
    start = data.get("start")
    end = data.get("end")
    avoid_traffic = data.get("avoid_traffic", False)

    if not start or not end or start not in locations or end not in locations:
        return jsonify({"error": "Invalid start or end location"}), 400

    start_location = locations[start]
    end_location = locations[end]

    if(start_location == end_location):
        return

    # Tentukan waypoints berdasarkan kondisi
    waypoints = []
    if start == "pasar" and end == "mts_2" and avoid_traffic:
        waypoint1 = {"lat": -7.914000, "lng": 113.820000}
        waypoints.append(waypoint1)
    elif start == "pasar" and end == "SMP_1" and avoid_traffic:
        waypoint2 = {"lat": -7.915000, "lng": 113.820000}
        waypoints.append(waypoint2)

    # Return rute dan waypoints
    response = {
        "start": start_location,
        "end": end_location,
        "waypoints": waypoints,
    }
    return jsonify(response)

@app.route("/")
def index():
    return render_template('index.html', locations= locations)  # File HTML frontend

@app.route("/video_feed")
def video_feed():
    return Response(video_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

def main():
    app.run(debug=True)  # Jalankan server Flask

if __name__ == "__main__":
    main()
