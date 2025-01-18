from ultralytics import YOLO
import cv2
from flask import Flask, render_template,request, Response, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Mengizinkan akses dari domain lain

model = YOLO("yolov8n.pt")

locations = {
    "pasar": {"name": "Pasar", "lat": -7.915016, "lng": 113.827289, "videoSource": "https://video.pasar.com/stream"},
    "mts_2": {"name": "MTS 2", "lat": -7.915497, "lng": 113.816206, "videoSource": "https://video.mts2.com/stream"},
    "SD": {"name": "SD Dabasah", "lat": -7.913832, "lng": 113.820898, "videoSource": "https://video.sd.com/stream"},
    "SMP_1": {"name": "SMPN 1 Bondowoso", "lat": -7.912070, "lng": 113.822498, "videoSource": "https://video.smp1.com/stream"},
    "SDK": {"name": "SDK", "lat": -7.917106, "lng": 113.822214, "videoSource": "https://video.sdk.com/stream"},
}

def video_stream(video_url):
    cap = cv2.VideoCapture(video_url)
    if not cap.isOpened():
        print("Error: Tidak dapat membuka video stream.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Deteksi objek dengan YOLO
        results = model(frame)

        # Gambar bounding box hasil deteksi
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = result.names[int(box.cls[0])]
                confidence = float(box.conf[0])

                # Gambar kotak deteksi
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Encode frame ke format JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

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

    if start_location == end_location:
        return jsonify({"error": "Start and end locations cannot be the same"}), 400

    # Tentukan waypoints berdasarkan kondisi
    waypoints = []
    if start == "pasar" and end == "mts_2" and avoid_traffic:
        waypoint1 = {"lat": -7.914000, "lng": 113.820000, "videoSource": "https://extstream.hk-opt2.com/LiveApp/streams/710404214066673275657182.m3u8"}
        waypoints.append(waypoint1)
    elif start == "pasar" and end == "SMP_1" and avoid_traffic:
        waypoint2 = {"lat": -7.915000, "lng": 113.820000, "videoSource": "https://extstream.hk-opt2.com/LiveApp/streams/956464037412277558025165.m3u8"}
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
    video_url = request.args.get("video_url")
    if not video_url:
        return "Error: URL tidak diberikan", 400

    return Response(video_stream(video_url), mimetype="multipart/x-mixed-replace; boundary=frame")

def main():
    app.run(debug=True)  # Jalankan server Flask

if __name__ == "__main__":
    main()
