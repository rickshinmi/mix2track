import streamlit as st
import av
import numpy as np
import io
import requests
import base64
import hashlib
import hmac
import time
import soundfile as sf

# === ACRCloud Credentials ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

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
        st.error(f"❌ APIエラー: {e}")
        print("ACRCloud error:", e)
        return {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}

# === Streamlit UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ")

uploaded_file = st.file_uploader("DJミックスのMP3をアップロード", type=["mp3"])

if uploaded_file is not None:
    st.write("⏳ 音源を解析中...")
    try:
        # MP3をavで読み込む
        container = av.open(uploaded_file)
        audio_stream = next(s for s in container.streams if s.type == 'audio')
        pcm_data = []
        for frame in container.decode(audio=0):
            pcm_data.append(frame.to_ndarray())

        audio = np.concatenate(pcm_data).astype(np.float32)
        sr = int(audio_stream.rate)

        segment_length_sec = 30
        segment_samples = sr * segment_length_sec
        raw_results = []
        displayed_titles = []
        progress = st.progress(0)

        for i in range(0, len(audio), segment_samples):
            segment = audio[i:i + segment_samples]
            if len(segment) < segment_samples:
                break  # 最後のセグメントが短すぎるとAPIで弾かれることがある

            buffer = io.BytesIO()
            sf.write(buffer, segment, sr, format="WAV")
            buffer.seek(0)
            result = recognize(buffer)

            if result.get("status", {}).get("msg") == "Success":
                metadata = result['metadata']['music'][0]
                title = metadata.get("title", "Unknown").strip()
                artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()
                if (title, artist) not in displayed_titles:
                    mmss = seconds_to_mmss(i // sr)
                    st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
                    displayed_titles.append((title, artist))

            progress.progress(min((i + segment_samples) / len(audio), 1.0))

        st.success("🎉 解析完了！")
        if not displayed_titles:
            st.write("⚠️ 有効なトラックは見つかりませんでした。")

    except Exception as e:
        st.error(f"🔴 音声処理エラー: {e}")
        print("[ERROR] Failed to decode MP3:", e)
