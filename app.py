import os
import logging
from typing import Optional, List, Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse

import torch
import whisperx


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whisperx_service")


class TranscribeRequest(BaseModel):
    filepath: Optional[str] = None
    filename: Optional[str] = None
    language: Optional[str] = None  # "zh" / "en" / "auto"


class WordItem(BaseModel):
    word: str
    start: Optional[float] = None
    end: Optional[float] = None


class SegmentItem(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: Optional[List[WordItem]] = None


class TranscribeResponseData(BaseModel):
    language: Optional[str] = None
    segments: List[SegmentItem]


class ApiResponse(BaseModel):
    code: int
    message: str
    data: Optional[TranscribeResponseData] = None


app = FastAPI(title="WhisperX Service", version="1.0.0")


# 全局模型变量，服务启动时加载
whisper_model = None
align_model = None
align_metadata = None
device = "cpu"


def load_models() -> None:
    """
    启动时加载 whisperx 模型（以及可选的对齐模型）。
    使用环境变量控制模型与设备：
      WHISPER_MODEL_NAME: 模型名，默认 "large-v2"
      WHISPER_DEVICE: "cuda" / "cpu"，默认自动探测
      WHISPER_COMPUTE_TYPE: 默认 "float16"（GPU）或 "int8"（CPU）
      AUDIO_ROOT: 音频根目录
    """
    global whisper_model, align_model, align_metadata, device

    model_name = os.getenv("WHISPER_MODEL_NAME", "large-v2")

    if os.getenv("WHISPER_DEVICE"):
        device = os.getenv("WHISPER_DEVICE")
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if device == "cuda":
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    else:
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    logger.info("Loading whisperx model '%s' on device '%s' (compute_type=%s)", model_name, device, compute_type)
    whisper_model = whisperx.load_model(model_name, device=device, compute_type=compute_type)

    # 可选：加载对齐模型（word-level timestamps）
    try:
        logger.info("Loading alignment model for word-level timestamps...")
        align_model, align_metadata = whisperx.load_align_model(language_code=None, device=device)
    except Exception as e:
        logger.warning("Failed to load alignment model: %s", e)
        align_model = None
        align_metadata = None


@app.on_event("startup")
def on_startup() -> None:
    """
    FastAPI 启动钩子：预加载模型。
    """
    load_models()
    logger.info("WhisperX service started and models loaded.")


def build_audio_path(body: TranscribeRequest) -> str:
    """
    根据 filepath / filename 计算最终音频绝对路径。
    优先使用 filepath；如果只提供 filename，则拼接 AUDIO_ROOT。
    """
    if not body.filepath and not body.filename:
        raise ValueError("`filepath` 和 `filename` 不能同时为空")

    # 如果传的是 filepath，优先用它
    if body.filepath:
        path = body.filepath
        # 如果是相对路径，则拼接 AUDIO_ROOT
        if not os.path.isabs(path):
            audio_root = os.getenv("AUDIO_ROOT", "/var/www/html/uploadfile/temp")
            path = os.path.join(audio_root, path)
    else:
        # 只传了 filename
        audio_root = os.getenv("AUDIO_ROOT", "/var/www/html/uploadfile/temp")
        path = os.path.join(audio_root, body.filename)  # type: ignore[arg-type]

    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise FileNotFoundError(f"file not found: {path}")

    return path


def normalize_result_to_segments(result: Dict[str, Any]) -> TranscribeResponseData:
    """
    将 whisperx 的输出结果统一转换为 TranscribeResponseData。
    兼容是否做了对齐（words 字段可能不存在）。
    """
    language = result.get("language")
    segments_raw = result.get("segments") or []

    segments: List[SegmentItem] = []
    for idx, seg in enumerate(segments_raw):
        seg_id = seg.get("id", idx)
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        text = seg.get("text", "")

        words_data = seg.get("words") or []
        words: List[WordItem] = []
        for w in words_data:
            word_text = str(w.get("word", ""))
            word_start = w.get("start")
            word_end = w.get("end")
            words.append(
                WordItem(
                    word=word_text,
                    start=float(word_start) if word_start is not None else None,
                    end=float(word_end) if word_end is not None else None,
                )
            )

        segment_item = SegmentItem(
            id=int(seg_id),
            start=start,
            end=end,
            text=text,
            words=words or None,
        )
        segments.append(segment_item)

    return TranscribeResponseData(language=language, segments=segments)


@app.post("/transcribe", response_model=ApiResponse)
def transcribe(body: TranscribeRequest) -> JSONResponse:
    """
    语音转写接口。

    请求示例：
    {
      "filepath": "/var/www/html/uploadfile/temp/test.wav"
    }
    或
    {
      "filename": "test.wav"
    }
    """
    try:
        if whisper_model is None:
            raise RuntimeError("whisperx model is not loaded")

        audio_path = build_audio_path(body)
        logger.info("Start transcribe: %s", audio_path)

        # 读取音频
        audio = whisperx.load_audio(audio_path)

        # 语言设置：优先请求中传的 language，其次环境变量，最后 None 表示 auto
        lang = body.language or os.getenv("WHISPER_LANGUAGE")
        if lang == "auto":
            lang = None

        # 推理（得到 segment 级别结果）
        result = whisper_model.transcribe(audio, language=lang)

        # 如 align_model 存在，则进一步对齐到词级
        if align_model is not None and align_metadata is not None:
            try:
                logger.info("Running alignment for word-level timestamps...")
                result = whisperx.align(
                    result["segments"],
                    align_model,
                    align_metadata,
                    audio,
                    device=device,
                )
            except Exception as e:
                logger.warning("alignment failed, return non-aligned result: %s", e)

        data = normalize_result_to_segments(result)

        resp = ApiResponse(code=0, message="success", data=data)
        return JSONResponse(content=resp.dict())

    except FileNotFoundError as e:
        logger.warning("file not found: %s", e)
        resp = ApiResponse(code=1, message=str(e), data=None)
        return JSONResponse(status_code=400, content=resp.dict())

    except ValueError as e:
        logger.warning("bad request: %s", e)
        resp = ApiResponse(code=2, message=str(e), data=None)
        return JSONResponse(status_code=400, content=resp.dict())

    except Exception as e:
        logger.exception("internal error: %s", e)
        resp = ApiResponse(code=500, message="internal error", data=None)
        return JSONResponse(status_code=500, content=resp.dict())


@app.get("/health")
def health() -> dict:
    """
    健康检查接口，可用于探活。
    """
    return {"status": "ok"}

