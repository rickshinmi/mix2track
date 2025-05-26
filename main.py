import streamlit as st
import av
import numpy as np
import soundfile as sf
import io
import base64
import hashlib
import hmac
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from av.audio.resampler import AudioResampler

# === ACRCloud API設定 ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

# === ACRCloudリクエスト署名生成 ===
def build_signature():
    http_method = "POST"
    http_uri = "/v1/identify"
    data_type = "audio"
    signature_version = "1"
    timestamp = time.time()
    string_to_sign = '\n'.join([
        http_method,
        http_uri,
        access_key,
        data_type,
        signature_version,
        str(timestamp)
    ])
    sign = base64.b64encode(
        hmac.new(access_secret.encode('ascii'),
                 string_to_sign.encode('ascii'),
                 digestmod=hashlib.sha1).digest()
    ).decode('ascii')
    return sign, timestamp

# === 音声セグメント認識 ===
def recognize_segment(start_time_sec, segment, sr):
    buf = io.BytesIO()
    sf.write(buf, segment, sr, format="WAV", subtype="FLOAT")
    buf.seek(0)

    sign, timestamp = build_signature()
    files = [('sample', ('segment.wav', buf, 'audio/wav'))]
    data = {
        'access_key': access_key,
        'sample_bytes': len(buf.getvalue()),
        'timestamp': str(timestamp),
        'signature': sign,
        'data_type': 'audio',
        'signature_version': '1'
    }

    try:
        response = requests.post(requrl, files=files, data=data, timeout=10)
        response.raise_for_status()
        return start_time_sec, response.json()
    except Exception as e:
        return start_time_sec, {
            "status": {"msg": "error", "code": -1},
            "error": str(e)
        }
