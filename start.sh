#!/bin/bash
# =============================================================
# START SCRIPT — jalankan bot + dashboard bersamaan
# =============================================================

echo "Starting Molty Royale Multi-Agent + Dashboard..."

# Buat folder yang dibutuhkan
mkdir -p logs data

# Jalankan dashboard di background
echo "Starting dashboard on port ${DASHBOARD_PORT:-8080}..."
cd /app
python dashboard/app.py &
DASH_PID=$!

# Jalankan bot utama
echo "Starting bot agents..."
python main_multi.py &
BOT_PID=$!

echo "Dashboard PID: $DASH_PID"
echo "Bot PID: $BOT_PID"

# Tunggu salah satu proses mati, lalu restart keduanya
wait -n $DASH_PID $BOT_PID
echo "One process died, exiting to trigger Railway restart..."
exit 1
