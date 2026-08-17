#!/bin/bash

set -e

LOG_DIR=/root/Kone/logs
PID_DIR=/root/Kone/pids

mkdir -p "$LOG_DIR" "$PID_DIR"
mkdir -p /root/Kone/.mongo/db

echo "Starting KONE services..."

# --------------------------------------------------
# 0. Azure Payload Server
# --------------------------------------------------
cd /root/Kone/Frontend/kone-api-master

nohup npm run azure-payload \
    > "$LOG_DIR/azure-payload.log" 2>&1 &

echo $! > "$PID_DIR/azure-payload.pid"
echo "Azure Payload Server started: PID $(cat "$PID_DIR/azure-payload.pid")"


# --------------------------------------------------
# 1. MongoDB
# --------------------------------------------------
nohup mongod \
    --dbpath /root/Kone/.mongo/db \
    --bind_ip 127.0.0.1 \
    --port 27017 \
    > "$LOG_DIR/mongodb.log" 2>&1 &

echo $! > "$PID_DIR/mongodb.pid"
echo "MongoDB started: PID $(cat "$PID_DIR/mongodb.pid")"


# Give MongoDB a moment to bind
sleep 2


# --------------------------------------------------
# 2. Python Logic Server + FireRed
# --------------------------------------------------
cd /root/Kone

nohup /root/Kone/start_logic_with_firered.sh \
    > "$LOG_DIR/logic-firered.log" 2>&1 &

echo $! > "$PID_DIR/logic-firered.pid"
echo "Logic + FireRed started: PID $(cat "$PID_DIR/logic-firered.pid")"


# --------------------------------------------------
# 3. API Server
# --------------------------------------------------
cd /root/Kone/Frontend/kone-api-master

nohup env \
    PATH=/workspace/Kone/.local/node/node-v20.19.5-linux-x64/bin:$PATH \
    NODE_ENV=development \
    PORT=4000 \
    LOGIC_URL=http://127.0.0.1:8001 \
    MONGODB_URL=mongodb://127.0.0.1:27017/kone \
    JWT_SECRET=local_guest_secret \
    COMFY_AUTOSTART=true \
    COMFY_ROOT=/root/Kone/vdotest \
    COMFY_URL=http://127.0.0.1:8188 \
    COMFY_RUNNER=/root/Kone/vdotest/run_i2v_api.py \
    COMFY_START_SCRIPT=/root/Kone/vdotest/scripts/start_comfy_logged.sh \
    COMFY_PYTHON=/usr/bin/python3 \
    npm run dev \
    > "$LOG_DIR/api.log" 2>&1 &

echo $! > "$PID_DIR/api.pid"
echo "API Server started: PID $(cat "$PID_DIR/api.pid")"


# --------------------------------------------------
# 4. UI Server
# --------------------------------------------------
cd /root/Kone/Frontend/kone-ui-master

nohup env \
    PATH=/workspace/Kone/.local/node/node-v20.19.5-linux-x64/bin:$PATH \
    VITE_ENABLE_MOCK_API=false \
    VITE_API_BASE_URL=/api/v1 \
    VITE_API_TIMEOUT=120000 \
    npm run dev -- --host 0.0.0.0 --port 3000 \
    > "$LOG_DIR/ui.log" 2>&1 &

echo $! > "$PID_DIR/ui.pid"
echo "UI started: PID $(cat "$PID_DIR/ui.pid")"


echo
echo "======================================"
echo "All services launched."
echo "======================================"
echo
echo "Logs:"
echo "  Azure : $LOG_DIR/azure-payload.log"
echo "  Mongo : $LOG_DIR/mongodb.log"
echo "  Logic : $LOG_DIR/logic-firered.log"
echo "  API   : $LOG_DIR/api.log"
echo "  UI    : $LOG_DIR/ui.log"
echo
