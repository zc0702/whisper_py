#!/usr/bin/env bash

# 停止 whisperx FastAPI 服务
# 使用方法（在服务器上）：
#   chmod +x stop.sh
#   ./stop.sh

set -e

# === 根据实际路径修改这里，需与 start_whisperx_service.sh 保持一致 ===
PROJECT_DIR="/opt/whisperx_py"
PID_FILE="${PROJECT_DIR}/whisperx_service.pid"

echo "==== Stopping WhisperX FastAPI service ===="

if [ ! -f "${PID_FILE}" ]; then
  echo "PID file not found: ${PID_FILE}"
  echo "可能服务本身没有启动，或已通过其他方式停止。"
  exit 0
fi

PID=$(cat "${PID_FILE}")

if ps -p "${PID}" > /dev/null 2>&1; then
  echo "Killing process pid=${PID}..."
  kill "${PID}" || true

  # 等待最多 10 秒看看是否退出
  for i in $(seq 1 10); do
    if ps -p "${PID}" > /dev/null 2>&1; then
      echo "Process still running, wait ${i}s..."
      sleep 1
    else
      break
    fi
  done

  if ps -p "${PID}" > /dev/null 2>&1; then
    echo "Process still alive, sending SIGKILL..."
    kill -9 "${PID}" || true
  fi

  echo "WhisperX service (pid=${PID}) stopped."
else
  echo "No running process with pid=${PID}, just removing pid file."
fi

rm -f "${PID_FILE}"

