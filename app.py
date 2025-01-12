import cv2
from flask import Flask, render_template, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Mengizinkan akses dari domain lain

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

@app.route("/")
def index():
    return render_template('index.html')  # File HTML frontend

@app.route("/video_feed")
def video_feed():
    return Response(video_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

def main():
    app.run(debug=True)  # Jalankan server Flask

if __name__ == "__main__":
    main()
