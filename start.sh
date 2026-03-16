#!/usr/bin/env bash

# 启动 whisperx FastAPI 服务
# 使用方法（在服务器上）：
#   chmod +x start.sh
#   ./start.sh

set -e

# === 根据实际路径修改这里 ===
PROJECT_DIR="/opt/whisperx_py"          # 部署后放置 app.py 的目录
CONDA_BASE="/root/miniconda3"               # conda 安装根目录
CONDA_ENV_NAME="whisperx"                   # 已经安装 whisperx 的环境名

# === whisperx 服务运行配置（根据你的机器推荐值） ===
export AUDIO_ROOT="/var/www/html/uploadfile/temp"
export WHISPER_MODEL_NAME="large-v2"
export WHISPER_DEVICE="cuda"
export WHISPER_COMPUTE_TYPE="float16"
export WHISPER_LANGUAGE="auto"


# uvicorn 配置
HOST="0.0.0.0"
PORT="8000"
WORKERS="${WORKERS:-1}"                      # 建议先 1，确认显存情况后再调大
LOG_LEVEL="${LOG_LEVEL:-info}"

# PID 文件路径
PID_FILE="${PROJECT_DIR}/whisperx_service.pid"

echo "==== Starting WhisperX FastAPI service ===="
echo "PROJECT_DIR=${PROJECT_DIR}"
echo "CONDA_ENV_NAME=${CONDA_ENV_NAME}"
echo "AUDIO_ROOT=${AUDIO_ROOT}"
echo "WHISPER_MODEL_NAME=${WHISPER_MODEL_NAME}"
echo "WHISPER_DEVICE=${WHISPER_DEVICE}"
echo "WHISPER_COMPUTE_TYPE=${WHISPER_COMPUTE_TYPE}"
echo "WHISPER_LANGUAGE=${WHISPER_LANGUAGE}"
echo "HOST=${HOST}, PORT=${PORT}, WORKERS=${WORKERS}"

# 初始化 conda
if [ -f "${CONDA_BASE}/etc/profile.d/conda.sh" ]; then
  # shellcheck source=/dev/null
  source "${CONDA_BASE}/etc/profile.d/conda.sh"
else
  echo "ERROR: conda.sh not found at ${CONDA_BASE}/etc/profile.d/conda.sh"
  exit 1
fi

conda activate "${CONDA_ENV_NAME}"

cd "${PROJECT_DIR}"

# 如已有旧 PID，先尝试杀掉
if [ -f "${PID_FILE}" ]; then
  OLD_PID=$(cat "${PID_FILE}")
  if ps -p "${OLD_PID}" > /dev/null 2>&1; then
    echo "Found existing service (pid=${OLD_PID}), killing..."
    kill "${OLD_PID}" || true
  fi
  rm -f "${PID_FILE}"
fi

# 后台启动 uvicorn，并把 PID 写入文件
nohup uvicorn app:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --log-level "${LOG_LEVEL}" \
  > "${PROJECT_DIR}/whisperx_service.out" 2>&1 &

NEW_PID=$!
echo "${NEW_PID}" > "${PID_FILE}"

echo "WhisperX service started with PID=${NEW_PID}, listening on ${HOST}:${PORT}"
echo "Logs: ${PROJECT_DIR}/whisperx_service.out"

