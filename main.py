import time
import base64
import hashlib
import hmac
import requests
import io
import streamlit as st
import numpy as np
import soundfile as sf
import av
from av.audio.resampler import AudioResampler

# === ACRCloud Credentials ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

# === Helper ===
def seconds_to_mmss(seconds):
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes:02d}:{sec:02d}"

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
    files = [
        ('sample', ('segment.wav', segment_bytes, 'audio/wav'))
    ]
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
        return response.json()
    except Exception as e:
        return {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}

def read_mp3_with_resampler(file_like, max_frames=None):
    file_like.seek(0)
    container = av.open(file_like)
    stream = next(s for s in container.streams if s.type == 'audio')
    resampler = AudioResampler(format="flt", layout="mono", rate=44100)
    samples = []

    for packet in container.demux(stream):
        for frame in packet.decode():
            resampled_frames = resampler.resample(frame)
            for mono_frame in resampled_frames:
                arr = mono_frame.to_ndarray().flatten()
                samples.append(arr)
                if max_frames and len(samples) >= max_frames:
                    break
        if max_frames and len(samples) >= max_frames:
            break

    if not samples:
        raise ValueError("MP3から音声データを取得できませんでした。")

    audio = np.concatenate(samples).astype(np.float32)
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = (audio / max_val) * 0.9
    return audio, 44100

# === Streamlit UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ（高音質版）")

uploaded_file = st.file_uploader("DJミックスのMP3をアップロード", type=["mp3"])

if uploaded_file is not None:
    st.write("⏳ 音源を解析中...")

    try:
        audio, sr = read_mp3_with_resampler(uploaded_file)
    except Exception as e:
        st.error(f"❌ 音声読み込み失敗: {e}")
        st.stop()

    segment_length_samples = sr * 30
    duration = len(audio) / sr

    raw_results = []
    displayed_titles = []
    progress = st.progress(0)

    for i in range(0, len(audio), segment_length_samples):
        segment = audio[i:i + segment_length_samples]
        buffer = io.BytesIO()
        sf.write(buffer, segment, sr, format="WAV", subtype="FLOAT")
        buffer.seek(0)
        result = recognize(buffer)

        if result.get("status", {}).get("msg") == "Success":
            metadata = result['metadata']['music'][0]
            title = metadata.get("title", "Unknown").strip()
            artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()

            if (title, artist) not in displayed_titles:
                raw_results.append((i // sr, title, artist))
                displayed_titles.append((title, artist))

                mmss = seconds_to_mmss(i // sr)
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")

        progress.progress(min((i + segment_length_samples) / len(audio), 1.0))

    if raw_results:
        st.success("🎉 解析完了！")
        st.subheader("🔁 全体のトラック一覧")
        prev = None
        for t, title, artist in raw_results:
            if prev != (title, artist):
                mmss = seconds_to_mmss(t)
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
                prev = (title, artist)
    else:
        st.warning("⚠️ 有効なトラックは見つかりませんでした。")
