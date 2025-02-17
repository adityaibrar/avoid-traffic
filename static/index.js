let map,
  directionsService,
  directionsRenderer,
  trafficLayer,
  waypointsMarkers = [];

const locationData = { locations, toJson };

// Initialize the map
function initMap() {
  map = new google.maps.Map(document.getElementById("map"), {
    center: { lat: -7.79558, lng: 110.36949 }, // Default location
    zoom: 14,
  });

  directionsService = new google.maps.DirectionsService();
  directionsRenderer = new google.maps.DirectionsRenderer({
    map: map,
  });
}

// Clear existing markers
function clearWaypointsMarkers() {
  waypointsMarkers.forEach((marker) => marker.setMap(null));
  waypointsMarkers = [];
}

// Add markers for waypoints
function addWaypointMarker(location, text, videoSource) {
  const marker = new google.maps.Marker({
    position: location,
    map: map,
  });

  // Add click listener to show modal
  marker.addListener("click", () => {
    loadVideo(videoSource);
  });

  waypointsMarkers.push(marker);
}

function loadVideo(videoSource) {
  const imageElement = document.getElementById("trafficImage");
  const objectCountElement = document.getElementById("objectCount");
  const totalObjectsElement = document.getElementById("total");
  const loader = document.getElementById("videoLoading");

  // Tampilkan loading
  loader.classList.remove("hidden");
  imageElement.style.display = "none";

  // Set src untuk video feed
  imageElement.src = `/video_feed?video_url=${encodeURIComponent(videoSource)}`;

  // Event listener untuk mengetahui kapan video selesai dimuat
  imageElement.onload = () => {
    loader.classList.add("hidden");
    imageElement.style.display = "block";
  };

  // Menampilkan modal
  const modal = new bootstrap.Modal(document.getElementById("infoModal"));
  modal.show();

  // Update jumlah objek setiap 2 detik
  setInterval(async () => {
    const response = await fetch(
      `/object_count?video_url=${encodeURIComponent(videoSource)}`
    );
    const objectCounts = await response.json();

    // Tampilkan jumlah objek di modal
    if (!objectCounts.error) {
      const totalObjects = Object.values(objectCounts).reduce(
        (sum, count) => sum + count,
        0
      );
      objectCountElement.innerHTML = Object.entries(objectCounts)
        .map(([label, count]) => `<h6>${label}: ${count}</h6>`)
        .join("");
      totalObjectsElement.innerHTML = totalObjects;
    } else {
      objectCountElement.innerHTML = "<p>Tidak dapat mendeteksi objek</p>";
    }
  }, 2000);

  const historicalContainer = document.getElementById("historicalData");
  historicalContainer.innerHTML = `
        <div class="text-center loading-historical">
            <div class="spinner-border text-primary"></div>
            <p class="mt-2 mb-0">Memuat data historis...</p>
        </div>`;

  fetch(`/historical_averages?video_url=${encodeURIComponent(videoSource)}`)
    .then((response) => response.json())
    .then((data) => {
      if (data.length === 0) {
        historicalContainer.innerHTML =
          '<p class="text-muted text-center">Belum ada data historis</p>';
        return;
      }

      historicalContainer.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-sm table-hover">
                        <thead>
                            <tr>
                                <th>Waktu</th>
                                <th>Mobil</th>
                                <th>Motor</th>
                                <th>Bus</th>
                                <th>Truk</th>
                                <th>Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data
                              .map(
                                (entry) => `
                                <tr>
                                    <td>${entry.timestamp}</td>
                                    <td>${entry.car}</td>
                                    <td>${entry.motorcycle}</td>
                                    <td>${entry.bus}</td>
                                    <td>${entry.truck}</td>
                                    <td class="fw-bold">${entry.total}</td>
                                </tr>
                            `
                              )
                              .join("")}
                        </tbody>
                    </table>
                </div>`;
    })
    .catch((error) => {
      historicalContainer.innerHTML =
        '<p class="text-danger text-center">Gagal memuat data historis</p>';
    });
}

document.getElementById("infoModal").addEventListener("hidden.bs.modal", () => {
  const video = document.getElementById("trafficImage");

  // Hentikan video dan reset
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }

  // Bersihkan backdrop jika tertinggal
  const backdrops = document.querySelectorAll(".modal-backdrop");
  backdrops.forEach((backdrop) => backdrop.remove());

  // Pastikan scroll aktif kembali
  document.body.classList.remove("modal-open");
  document.body.style.overflow = "";
});

// Update fungsi calculateRoute untuk mencegah auto refresh
async function calculateRoute() {
  // disableButtonFor1Minute();
  const locationData = JSON.parse(
    document.getElementById("locationData").dataset.locations
  );
  const start = document.getElementById("start").value;
  const end = document.getElementById("end").value;

  if (start === end) {
    alert(
      "Start Location dan End Location tidak boleh sama. Silakan pilih lokasi yang berbeda."
    );
    return;
  }

  showFunc();

  try {
    if (!start || !end) {
      alert("Please select both start and end locations.");
      return;
    }

    // Reset directions renderer dan marker
    directionsRenderer.setMap(null);
    directionsRenderer = new google.maps.DirectionsRenderer({ map });
    clearWaypointsMarkers();

    // Panggil endpoint untuk menghitung rute
    const response = await fetch("/calculate_route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start, end }),
    });

    if (!response.ok) {
      const error = await response.json();
      alert(error.error || "Failed to calculate route");
      return;
    }

    const routeData = await response.json();

    const request = {
      origin: new google.maps.LatLng(routeData.start.lat, routeData.start.lng),
      destination: new google.maps.LatLng(routeData.end.lat, routeData.end.lng),
      travelMode: google.maps.TravelMode.DRIVING,
      waypoints: routeData.waypoints.map((wp) => ({
        location: new google.maps.LatLng(wp.lat, wp.lng),
        stopover: false,
      })),
    };

    directionsService.route(request, (result, status) => {
      if (status === google.maps.DirectionsStatus.OK) {
        directionsRenderer.setDirections(result);

        routeData.point_marker.forEach((wp) => {
          addWaypointMarker(
            { lat: wp.lat, lng: wp.lng },
            "Waypoint",
            wp.videoSource
          );
        });
        moveToMap();
      } else {
        alert("Could not calculate route: " + status);
        hideFunc();
      }
    });

    let waypointsForMaps =
      routeData.waypoints.length > 0
        ? routeData.waypoints.map((wp) => `${wp.lat},${wp.lng}`).join("|")
        : "";

    const mapsUrl = `https://www.google.com/maps/dir/?api=1&origin=${routeData.start.lat},${routeData.start.lng}&destination=${routeData.end.lat},${routeData.end.lng}&waypoints=${waypointsForMaps}`;

    // Perbarui href tombol tanpa menyebabkan refresh
    const mapsButton = document.getElementById("openMapsButton");
    mapsButton.href = mapsUrl;
    document.getElementById("mapsButtonContainer").style.display = "block";
  } catch (error) {
    alert(error.message);
  } finally {
    hideFunc();
    setTimeout(rebuildModal, 100);
  }
}

function moveToMap() {
  var scroll = document.getElementById("mapsButtonContainer");
  scroll.scrollIntoView();
}

function moveToHeader() {
  var scroll = document.getElementById("locationData");
  scroll.scrollIntoView();
}

function showFunc() {
  const loadingModalElement = document.getElementById("loadingModal");
  if (loadingModalElement) {
    const loadingModal = new bootstrap.Modal(loadingModalElement, {
      backdrop: "static",
      keyboard: false,
    });
    loadingModal.show();
  } else {
    console.log("Modal tidak ditemukan!");
  }
}

// Fungsi untuk menutup modal
function hideFunc() {
  console.log("Menutup modal...");

  const loadingModalElement = document.getElementById("loadingModal");

  if (loadingModalElement) {
    const loadingModal = bootstrap.Modal.getInstance(loadingModalElement);

    if (loadingModal) {
      loadingModal.hide(); // Menutup modal
      loadingModal.dispose(); // Menghapus instance modal dari memori
      console.log("Modal berhasil ditutup dan di-dispose.");
    } else {
      console.log("Instance modal tidak ditemukan, coba hapus manual.");
    }

    // Hapus modal dari DOM setelah animasi selesai
    setTimeout(() => {
      loadingModalElement.remove();
      console.log("Modal telah dihapus dari DOM.");
    }, 100);
  } else {
    console.log("Element modal tidak ditemukan!");
  }

  // Hapus backdrop jika masih ada
  document
    .querySelectorAll(".modal-backdrop")
    .forEach((backdrop) => backdrop.remove());

  // Pastikan body tidak terkunci
  document.body.classList.remove("modal-open");
  document.body.style.overflow = "auto";
}

function rebuildModal() {
  const modalHTML = `
  <div class="modal fade" id="loadingModal" tabindex="-1" data-bs-backdrop="static" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content border-0">
              <div class="modal-body text-center py-5">
                  <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                      <span class="visually-hidden">Loading...</span>
                  </div>
                  <h5 class="mt-3 mb-0">Analyzing Traffic Conditions...</h5>
                  <p class="text-muted mt-2">This may take a few seconds</p>
              </div>
          </div>
      </div>
  </div>`;

  document.body.insertAdjacentHTML("beforeend", modalHTML);
  console.log("Modal berhasil dibangun ulang.");
}
