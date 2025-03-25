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
    "host": os.getenv("DB_HOST"),  # Mengambil nilai dari .env
    "port": int(os.getenv("DB_PORT")),  # Konversi ke integer
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "cursorclass": pymysql.cursors.DictCursor
}

# Fungsi untuk mendapatkan koneksi database
def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

app = Flask(__name__)
CORS(app)  # Mengizinkan akses dari domain lain

model = YOLO("models/best_100_4663.pt")

locations = {
    "Jl. Bandung": {"name": "Jl. Bandung", "lat": -7.960674, "lng": 112.622380, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/001034626224094756998994.m3u8"},
    "Jl. Sumbersari": {"name": "Jl. Sumbersari", "lat": -7.952562, "lng": 112.609506, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/636589114401733445781917.m3u8"},
    "Jl. Gajayana Selatan": {"name": "Jl. Gajayana Selatan", "lat": -7.951431, "lng": 112.608987, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/455597782591873967365987.m3u8"},
    "Jl. MT Haryono Barat": {"name": "Jl. MT Haryono Barat", "lat": -7.935947, "lng": 112.605314, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/385150101635081489243344.m3u8"},
    "Jl. Borobudur": {"name": "Jl. Borobudur", "lat": -7.938960, "lng": 112.633439, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/807179387709306202506877.m3u8"},
    "Jl. Soekarno Hatta UB": {"name": "Jl. Soekarno Hatta UB", "lat": -7.949721, "lng": 112.615483, "videoSource": "http://stream.cctv.malangkota.go.id/WebRTCApp/streams/490076087057536757601215.m3u8"},
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
                avg_car = round(sum(counts['car']) / len(counts['car'])) if counts['car'] else 0
                avg_motorcycle = round(sum(counts['motorcycle']) / len(counts['motorcycle'])) if counts['motorcycle'] else 0
                avg_bus = round(sum(counts['bus']) / len(counts['bus'])) if counts['bus'] else 0
                avg_truck = round(sum(counts['truck']) / len(counts['truck'])) if counts['truck'] else 0
                total_avg = round((sum(counts['car']) + sum(counts['motorcycle']) +
                            sum(counts['bus']) + sum(counts['truck']))) / len(counts['car']) if counts['car'] else 0

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
scheduler.add_job(save_averages, 'interval', seconds=20)

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
    """Mendapatkan total rata-rata kendaraan dari database dalam 30 menit terakhir"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Cari data dalam 30 menit terakhir
        cur.execute("""
            SELECT total_average 
            FROM traffic_averages 
            WHERE video_url = %s 
            AND timestamp >= NOW() - INTERVAL 5 MINUTE 
            ORDER BY timestamp DESC 
            LIMIT 1;
        """, (video_url,))
            # AND timestamp >= NOW() - INTERVAL 1 MINUTE 
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result is not None:
            print(f"DEBUG: Data ditemukan, total_average = {result['total_average']}")
            return result['total_average']
        else:
            # Jika tidak ada data, lakukan deteksi real-time dan simpan
            return perform_realtime_detection(video_url)

    except Exception as e:
        print("Error in get_vehicle_count:", str(e))
        return None

def perform_realtime_detection(video_url):
    print(f"Debug: {video_url}")
    """Deteksi kendaraan real-time dan simpan ke database"""
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
            confidence = float(box.conf[0])  # Ambil confidence score
            if label in vehicle_classes and confidence >= 0.5:  # Filter confidence
                counts[label] += 1
    total = round(sum(counts.values()))
    cap.release()
    # Simpan hasil deteksi langsung ke database
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO traffic_averages 
            (video_url, average_car, average_motorcycle, average_bus, average_truck, total_average, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (video_url, counts['car'], counts['motorcycle'], counts['bus'], counts['truck'], total))
        conn.commit()
        cur.close()
        conn.close()
        return total
    except Exception as e:
        print("Error saving real-time data:", str(e))
        return None

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
        # Gambar bounding box hanya untuk kendaraan dengan confidence >= 0.5
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                label = model.names[class_id]  # Ambil label dari model
                confidence = float(box.conf[0])  # Ambil confidence score
                if label in vehicle_classes and confidence >= 0.5:  # Filter confidence
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
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
            confidence = float(box.conf[0])  # Ambil confidence score
            if label in vehicle_classes and confidence >= 0.5:  # Filter confidence
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

    # Definisikan logika rute dalam dictionary
    route_logic = {
        ("Jl. Gajayana Selatan", "Jl. MT Haryono Barat"): {
            "threshold": 0,
            "waypoints": [{"lat": -7.943472, "lng": 112.603881}],
            "point_markers": [{"lat": -7.946302, "lng": 112.609128}]
        },
        ("Jl. Bandung", "Jl. Sumbersari"): {
            "threshold": 1,
            "waypoints": [{"lat": -7.965025, "lng": 112.616374}],
            "point_markers": [{"lat": -7.956383, "lng": 112.613366}]
        },
        ("Jl. Borobudur", "Jl. Soekarno Hatta UB"): {
            "threshold": 1,
            "waypoints": [{"lat": -7.947825, "lng":  112.625181}],
            "point_markers": [{"lat": -7.942905, "lng": 112.620851}]
        },
    }

    # Cek apakah rute ada dalam logika
    route_key = (start, end)
    if route_key not in route_logic:
        return jsonify({"error": "Mohon maaf rute tidak tersedia"}), 500

    # Ambil logika rute
    logic = route_logic[route_key]
    video_url = end_location["videoSource"]
    vehicle_count = get_vehicle_count(video_url)

    if vehicle_count is None:
        return jsonify({"error": "Gagal memeriksa kepadatan lalu lintas"}), 500

    # Tentukan apakah perlu menghindari kemacetan
    avoid_traffic = vehicle_count > logic["threshold"]
    print(f"Total kendaraan yang ada di database adalah {vehicle_count}")

    # Persiapkan waypoints dan point markers
    waypoints = logic["waypoints"] if avoid_traffic else []
    point_markers = [
        {**marker, "videoSource": video_url} for marker in logic["point_markers"]
    ] if avoid_traffic else []

    # Siapkan respons
    response = {
        "start": start_location,
        "end": end_location,
        "waypoints": waypoints,
        "point_marker": point_markers,
        "origin": {
            "lat": start_location["lat"],
            "lng": start_location["lng"]
        },
        "destination": {
            "lat": end_location["lat"],
            "lng": end_location["lng"]
        },
        "vehicle": vehicle_count
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

# Shutdown scheduler saat aplikasi dihentikan
atexit.register(lambda: scheduler.shutdown())

def main():
    # app.run(host="0.0.0.0", port=5000, debug=True)  # Jalankan server Flask
    app.run(debug=True) #run web dilokal

if __name__ == "__main__":
    main()
