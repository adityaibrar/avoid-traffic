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
    "SMP_1": {"name": "SMPN 1 Bondowoso", "lat": -7.912070, "lng": 113.822498, "videoSource": "https://cctvjss.jogjakota.go.id/malioboro/Malioboro_21_Utara_Inna_Malioboro.stream/chunklist_w552182256.m3u8"},
    "SDK": {"name": "SDK", "lat": -7.917106, "lng": 113.822214, "videoSource": "https://video.sdk.com/stream"},
}

def get_vehicle_count(video_url):
    """Mendapatkan jumlah kendaraan dari video stream menggunakan YOLO"""
    cap = cv2.VideoCapture(video_url)
    if not cap.isOpened():
        return None
    
    ret, frame = cap.read()
    if not ret:
        cap.release()
        return None
    
    results = model(frame)
    vehicle_classes = {'car', 'motorcycle', 'bus', 'truck'}
    counts = {cls: 0 for cls in vehicle_classes}
    
    for result in results:
        for box in result.boxes:
            label = model.names[int(box.cls[0])]
            if label in vehicle_classes:
                counts[label] += 1
    
    cap.release()
    return sum(counts.values())

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

        # Dictionary untuk menyimpan jumlah objek per label
        object_counts = {}

        # Gambar bounding box hasil deteksi
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = result.names[int(box.cls[0])]
                confidence = float(box.conf[0])

                # Tambahkan jumlah label
                object_counts[label] = object_counts.get(label, 0) + 1

                # Gambar kotak deteksi
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Encode frame ke format JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Menggabungkan JSON (jumlah objek) dan frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
               b'Content-Type: application/json\r\n\r\n' + str(object_counts).encode() + b'\r\n')

    cap.release()

@app.route("/object_count")
def object_count():
    video_url = request.args.get("video_url")
    cap = cv2.VideoCapture(video_url)
    
    if not cap.isOpened():
        return jsonify({"error": "Tidak dapat membuka video stream"}), 400

    ret, frame = cap.read()
    if not ret:
        return jsonify({"error": "Tidak dapat membaca frame video"}), 400

    # Deteksi objek dengan YOLO
    results = model(frame)
    
    # Hitung jumlah objek per label
    object_counts = {}
    for result in results:
        for box in result.boxes:
            label = result.names[int(box.cls[0])]
            object_counts[label] = object_counts.get(label, 0) + 1

    cap.release()
    
    return jsonify(object_counts)

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

    # Otomatis deteksi kemacetan untuk rute pasar -> SMP_1
    if start == "pasar" and end == "SMP_1":
        video_url = end_location["videoSource"]
        vehicle_count = get_vehicle_count(video_url)
        
        if vehicle_count is None:
            return jsonify({"error": "Gagal memeriksa kepadatan lalu lintas"}), 500
            
        avoid_traffic = vehicle_count > 1  # Ambang batas 10 kendaraan

    waypoints = []
    pointMarker = []
    
    # Logika penentuan rute
    if start == "pasar" and end == "mts_2" and avoid_traffic:
        waypoint1 = {"lat": -7.914000, "lng": 113.820000, "videoSource": "https://extstream.hk-opt2.com/LiveApp/streams/710404214066673275657182.m3u8"}
        waypoints.append(waypoint1)
    elif start == "pasar" and end == "SMP_1" and avoid_traffic:
        # waypoint2 = {"lat": -7.915000, "lng": 113.820000}
        # -7.912589, 113.816900
        waypoint2 = {"lat": -7.912589, "lng": 113.816900}
        pointMarker1 = {"lat": -7.913432, "lng": 113.823489, "videoSource": "https://cctvjss.jogjakota.go.id/malioboro/Malioboro_21_Utara_Inna_Malioboro.stream/chunklist_w552182256.m3u8"}
        waypoints.append(waypoint2)
        pointMarker.append(pointMarker1)

    response = {
        "start": start_location,
        "end": end_location,
        "waypoints": waypoints,
        "point_marker": pointMarker,
        "origin": {  # Tambahkan koordinat asli
            "lat": start_location["lat"],
            "lng": start_location["lng"]
        },
        "destination": {  # Tambahkan koordinat tujuan
            "lat": end_location["lat"],
            "lng": end_location["lng"]
        }
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
    # app.run(host="0.0.0.0", port=5000, debug=True)  # Jalankan server Flask
    app.run(debug=True) #run web dilokal

if __name__ == "__main__":
    main()
