#!/bin/bash

# Nama virtual environment
VENV_DIR="myenv"

# Cek apakah venv sudah ada, jika belum maka buat
if [ ! -d "$VENV_DIR" ]; then
    echo "Membuat virtual environment..."
    python3 -m venv $VENV_DIR
fi

# Aktifkan venv
source $VENV_DIR/bin/activate

which pip

# Pastikan pip terbaru
pip install --upgrade pip

# Install dependencies dari requirements.txt
pip install -r requirements.txt

echo "Semua dependensi telah diinstal dan virtual environment telah aktif!"
