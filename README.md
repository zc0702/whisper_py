## WhisperX Python 说明

封装基于 **FastAPI** 的 `whisperx` 语音识别服务，替代 PHP 命令行调用的方式，提高性能和稳定性。

---

### 1. 目录与核心文件

- `app.py`：FastAPI 应用。
- `requirements.txt`：Python 依赖。
- `start.sh`：启动服务脚本（包含环境变量设置）。
- `stop.sh`：停止服务脚本。

> 说明：脚本默认假设部署路径为 `/opt/whisperx_py`，请按实际情况修改。

---

### 2. 环境准备（Ubuntu + conda）

1. 将代码部署到服务器（示例）：

```bash
mkdir -p /opt/whisperx_py
cd /opt/whisperx_py
# 把本项目下的文件（app.py、requirements.txt、*.sh 等）同步到此目录
```

2. 确保已安装 conda，并有名为 `whisperx` 的环境且已安装 whisperx：

```bash
conda activate whisperx
pip install -r requirements.txt
```

3. 确认 GPU / CUDA 可用（可选）：

```bash
conda activate whisperx
python -c "import torch; print('cuda_available=', torch.cuda.is_available(), 'count=', torch.cuda.device_count()); \
print('name=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

出现 `cuda_available=True` 且名称为 NVIDIA A10 即可使用 GPU。

---

### 3. 启动脚本说明（start.sh）

- 指定项目目录、conda 安装路径、环境名：

```bash
PROJECT_DIR="/opt/whisperx_py"
CONDA_BASE="/root/miniconda3"
CONDA_ENV_NAME="whisperx"
```

- whisperx 服务相关环境变量：

```bash
export AUDIO_ROOT="/var/www/html/uploadfile/temp"
export WHISPER_MODEL_NAME="${WHISPER_MODEL_NAME:-medium}"   # 可改 large-v2 / large-v3
export WHISPER_DEVICE="${WHISPER_DEVICE:-cuda}"
export WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-float16}"
export WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-zh}"
```

- uvicorn 运行参数：

```bash
HOST="0.0.0.0"
PORT="8000"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"
```

启动方式：

```bash
cd /opt/whisperx_py
chmod +x start.sh stop.sh
./start.sh
```

脚本会：

- 初始化 conda，激活 `whisperx` 环境；
- 后台启动 uvicorn：

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
```

- 把进程 PID 写入 `whisperx_service.pid`；
- 控制台日志输出到 `whisperx_service.out`。

---

### 4. 停止脚本说明（stop_whisperx_service.sh）

脚本通过 `PID_FILE` 找到 uvicorn 进程并优雅停止：

```bash
PROJECT_DIR="/opt/whisperx_py"
PID_FILE="${PROJECT_DIR}/whisperx_service.pid"
```

使用方式：

```bash
cd /opt/whisperx_py
./stop.sh
```

逻辑：

- 若存在 `whisperx_service.pid`：
  - 读取 PID，发送 `kill` 信号；
  - 最多等待 10 秒，若仍未退出则发送 `kill -9`；
  - 最后删除 PID 文件。

---

### 5. 接口说明

服务启动后，默认监听 `http://<服务器IP>:8000`。

#### 5.1 健康检查

- **方法**：`GET /health`
- **返回**：

```json
{ "status": "ok" }
```

#### 5.2 语音转写

- **方法**：`POST /transcribe`
- **请求体（JSON）**：

方式一：直接传完整路径

```json
{
  "filepath": "/var/www/html/uploadfile/temp/test.wav"
}
```

方式二：只传文件名（会自动拼接到 `AUDIO_ROOT` 下）

```json
{
  "filename": "test.wav"
}
```

可选参数：

```json
{
  "filename": "test.wav",
  "language": "zh"
}
```

- `language` 优先级：请求体 > `WHISPER_LANGUAGE` 环境变量 > 自动识别（`None`）。

**成功返回示例**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "language": "zh",
    "segments": [
      {
        "id": 0,
        "start": 0.0,
        "end": 3.5,
        "text": "你好，这是一个测试。",
        "words": [
          { "word": "你好", "start": 0.1, "end": 0.8 },
          { "word": "，", "start": 0.8, "end": 0.9 }
        ]
      }
    ]
  }
}
```

**错误返回示例**：

- 文件不存在：

```json
{
  "code": 1,
  "message": "file not found: /var/www/html/uploadfile/temp/test.wav",
  "data": null
}
```

- 参数错误：

```json
{
  "code": 2,
  "message": "`filepath` 和 `filename` 不能同时为空",
  "data": null
}
```

- 内部错误：

```json
{
  "code": 500,
  "message": "internal error",
  "data": null
}
```

---

### 6. PHP 调用示例

```php
$audioFile = "/var/www/html/uploadfile/temp/xxx.wav";

$payload = json_encode([
    'filepath' => $audioFile,
    // 'language' => 'zh', // 可选
]);

$ch = curl_init('http://127.0.0.1:8000/transcribe');
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "POST");
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
    'Content-Length: ' . strlen($payload),
]);

$response = curl_exec($ch);
if ($response === false) {
    $error = curl_error($ch);
    curl_close($ch);
    // 记录日志 / 抛异常
} else {
    curl_close($ch);
    $data = json_decode($response, true);
    if ($data['code'] === 0) {
        // 成功，从 $data['data']['segments'] 中读取转写结果
    } else {
        // 根据 $data['code'] / $data['message'] 做错误处理
    }
}
```

---

### 7. 常见调整点

- **模型大小**：`WHISPER_MODEL_NAME` 可在 `medium`、`large-v2`、`large-v3` 之间切换：
  - `medium`：显存占用更小，速度较快；
  - `large-v2/large-v3`：精度更高但更占显存。
- **并发数**：`WORKERS` 默认 1，有充足显存时可提高到 2。
- **日志**：服务日志在 `whisperx_service.out`，可根据需要接入 logrotate 或系统日志。

