#!/bin/bash
set -e
cd "$(dirname "$0")"

APP_URL="http://127.0.0.1:8765"

if curl -fsS "$APP_URL/" >/dev/null 2>&1; then
  open "$APP_URL/"
  exit 0
fi

echo "正在启动 Stockup…"
python3 server.py &
SERVER_PID=$!

for attempt in {1..30}; do
  if curl -fsS "$APP_URL/" >/dev/null 2>&1; then
    open "$APP_URL/"
    echo "Stockup 已启动。关闭此窗口或按 Control+C 可停止服务。"
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 0.3
done

echo "Stockup 未能启动。请检查是否已安装 Python 3，或端口 8765 是否被占用。"
wait "$SERVER_PID"
