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
from av.audio.resampler import AudioResampler

# === ACRCloud credentials from secrets ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

st.set_page_config(page_title="DJミックス識別ループ", layout="centered")
st.title("🎧 DJミックス識別（30秒ごとに10秒間）")

uploaded_file = st.file_uploader("MP3ファイルをアップロード", type=["mp3"])

# === Audio decoding and resampling ===
def read_mp3_with_resampler(file_like, max_frames=20000):
    try:
        file_like.seek(0)
        container = av.open(file_like)
        stream = next(s for s in container.streams if s.type == 'audio')

        resampler = AudioResampler(format="flt", layout="mono", rate=44100)
        samples = []

        for packet in container.demux(stream):
            for frame in packet.decode():
                for resampled_frame in resampler.resample(frame):
                    arr = resampled_frame.to_ndarray().flatten()
                    samples.append(arr)
                    if len(samples) >= max_frames:
                        break

        if not samples:
            raise ValueError("MP3から音声データを取得できませんでした。")

        audio = np.concatenate(samples).astype(np.float32)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = (audio / max_val) * 0.9

        return audio, 44100
    except Exception as e:
        raise RuntimeError(f"読み込みエラー: {e}")

# === ACRCloud helper ===
def build_signature():
    http_method = "POST"
    http_uri = "/v1/identify"
    data_type = "audio"
    signature_version = "1"
    timestamp = time.time()

    string_to_sign = '\n'.join([
        http_method, http_uri, access_key,
        data_type, signature_version, str(timestamp)
    ])
    sign = base64.b64encode(
        hmac.new(
            access_secret.encode('ascii'),
            string_to_sign.encode('ascii'),
            digestmod=hashlib.sha1
        ).digest()
    ).decode('ascii')
    return sign, timestamp

def recognize(segment_bytes):
    sign, timestamp = build_signature()
    files = [('sample', ('segment.wav', segment_bytes, 'audio/wav'))]
    data = {
        'access_key': access_key,
        'sample_bytes': len(segment_bytes.getvalue()),
        'timestamp': str(timestamp),
        'signature': sign,
        'data_type': 'audio',
        'signature_version': '1'
    }

    try:
        response = requests.post(requrl, files=files, data=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}

def seconds_to_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

# === Main logic ===
if uploaded_file is not None:
    st.write("📥 ファイルを受け取りました。読み込み中...")

    try:
        audio, sr = read_mp3_with_resampler(uploaded_file)
        st.success(f"✅ 音声読み込み成功（長さ: {len(audio)/sr:.1f} 秒）")
    except Exception as e:
        st.error(str(e))
        st.stop()

    # === 30秒ごとに10秒だけサンプリング ===
    segment_duration_sec = 10
    stride_sec = 30
    segment_len = int(segment_duration_sec * sr)
    stride_len = int(stride_sec * sr)

    st.write("🎧 ACRCloud識別を開始（30秒ごとに10秒）...")
    progress = st.progress(0)
    results = []
    shown = []

    for i in range(0, len(audio), stride_len):
        segment = audio[i : i + segment_len]
        if len(segment) < segment_len:
            break  # 最後が10秒未満ならスキップ

        buffer = io.BytesIO()
        sf.write(buffer, segment, sr, format="WAV", subtype="FLOAT")
        buffer.seek(0)

        mmss = seconds_to_mmss(i / sr)
        st.write(f"🕒 {mmss} → 🔍 解析中...")
        result = recognize(buffer)

        if result.get("status", {}).get("msg") == "Success":
            music = result['metadata']['music'][0]
            title = music.get("title", "Unknown")
            artist = music.get("artists", [{}])[0].get("name", "Unknown")
            if (title, artist) not in shown:
                shown.append((title, artist))
                results.append((i / sr, title, artist))
                st.success(f"🕒 {mmss} → 🎶 {title} / {artist}")
        else:
            st.warning(f"🕒 {mmss} → ❌ 未識別")

        progress.progress(min((i + stride_len) / len(audio), 1.0))

    if not results:
        st.error("⚠️ 有効なトラックは見つかりませんでした。")
    else:
        st.write("✅ 識別されたトラック一覧（重複除去）：")
        for t, title, artist in results:
            st.write(f"🕒 {seconds_to_mmss(t)} → 🎵 {title} / {artist}")
