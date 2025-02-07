import pymysql
from flask import Flask, render_template, request, Response, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import cv2
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Lock
import atexit
from dotenv import load_dotenv
import os

load_dotenv()

# Konfigurasi MySQL
DB_CONFIG = {
    "host": "127.0.0.1",  # Gunakan IP daripada 'localhost' untuk menghindari socket issues
    "user": "root",
    "password": "",
    "database": "traffic_monitoring",
    "cursorclass": pymysql.cursors.DictCursor
}

# Fungsi untuk mendapatkan koneksi database
def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

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

# Data akumulasi dan lock
accumulated_data = {}
data_lock = Lock()

# Scheduler untuk menyimpan data
scheduler = BackgroundScheduler()
scheduler.start()

def save_averages():
    with data_lock:
        global accumulated_data
        current_data = accumulated_data
        accumulated_data = {}

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            for video_url, counts in current_data.items():
                avg_car = sum(counts['car']) / len(counts['car']) if counts['car'] else 0
                avg_motorcycle = sum(counts['motorcycle']) / len(counts['motorcycle']) if counts['motorcycle'] else 0
                avg_bus = sum(counts['bus']) / len(counts['bus']) if counts['bus'] else 0
                avg_truck = sum(counts['truck']) / len(counts['truck']) if counts['truck'] else 0
                total_avg = (sum(counts['car']) + sum(counts['motorcycle']) +
                            sum(counts['bus']) + sum(counts['truck'])) / len(counts['car']) if counts['car'] else 0

                # Simpan ke database
                cur.execute("""
                    INSERT INTO traffic_averages 
                    (video_url, average_car, average_motorcycle, average_bus, average_truck, total_average, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (video_url, avg_car, avg_motorcycle, avg_bus, avg_truck, total_avg))

            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print("Error saving averages:", str(e))

# Jadwalkan penyimpanan setiap menit
scheduler.add_job(save_averages, 'interval', seconds=60)

@app.route("/historical_averages")
def get_historical_averages():
    video_url = request.args.get("video_url")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT timestamp, average_car, average_motorcycle, average_bus, average_truck, total_average 
            FROM traffic_averages 
            WHERE video_url = %s 
            ORDER BY timestamp DESC 
            LIMIT 10
        """, (video_url,))
        result = cur.fetchall()

        cur.close()
        conn.close()

        averages = [{
            "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "car": round(row["average_car"], 1),
            "motorcycle": round(row["average_motorcycle"], 1),
            "bus": round(row["average_bus"], 1),
            "truck": round(row["average_truck"], 1),
            "total": round(row["total_average"], 1)
        } for row in result]

        return jsonify(averages)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

    vehicle_classes = {'car', 'motorcycle', 'bus', 'truck'}  # Hanya mendeteksi kendaraan

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Deteksi objek dengan YOLO
        results = model(frame)

        # Gambar bounding box hanya untuk kendaraan
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                label = model.names[class_id]  # Ambil label dari model

                if label in vehicle_classes:  # Hanya proses kendaraan
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    confidence = float(box.conf[0])

                    # Gambar kotak deteksi
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Encode frame ke format JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Kirim frame ke client
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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

    results = model(frame)
    vehicle_classes = {'car', 'motorcycle', 'bus', 'truck'}
    counts = {cls: 0 for cls in vehicle_classes}

    for result in results:
        for box in result.boxes:
            label = model.names[int(box.cls[0])]
            if label in vehicle_classes:
                counts[label] += 1

    # Akumulasi data
    with data_lock:
        if video_url not in accumulated_data:
            accumulated_data[video_url] = {cls: [] for cls in vehicle_classes}

        for cls in vehicle_classes:
            accumulated_data[video_url][cls].append(counts[cls])

    cap.release()
    return jsonify(counts)

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
    apiKey = os.getenv("GMAPS_API_KEY")
    return render_template('index.html', locations= locations, apiKey= apiKey)  # File HTML frontend

@app.route("/video_feed")
def video_feed():
    video_url = request.args.get("video_url")
    if not video_url:
        return "Error: URL tidak diberikan", 400

    return Response(video_stream(video_url), mimetype="multipart/x-mixed-replace; boundary=frame")

# Shutdown scheduler saat aplikasi dihentikan
atexit.register(lambda: scheduler.shutdown())

def main():
    # app.run(host="0.0.0.0", port=5000, debug=True)  # Jalankan server Flask
    app.run(debug=True) #run web dilokal

if __name__ == "__main__":
    main()
