import time
import base64
import hashlib
import hmac
import requests
import io
import streamlit as st
import soundfile as sf
import numpy as np

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
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ APIリクエスト失敗: {e}")
        return {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}
    except Exception as e:
        st.error(f"❌ その他のエラー: {e}")
        return {"status": {"msg": f"Unexpected error: {e}", "code": "N/A"}}

# === Streamlit UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ")

uploaded_file = st.file_uploader("DJミックスのWAV音源をアップロード", type=["wav"])

if uploaded_file is not None:
    st.write("⏳ 音源を解析中...")

    try:
        audio, sr = sf.read(uploaded_file)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)  # モノラルに変換
    except Exception as e:
        st.error(f"❌ 音源の読み込みに失敗しました: {e}")
        st.stop()

    duration = len(audio) / sr
    segment_length_sec = 30
    segment_length_samples = int(segment_length_sec * sr)

    raw_results = []
    progress = st.progress(0)
    displayed_titles = []

    for i in range(0, len(audio), segment_length_samples):
        segment = audio[i:i + segment_length_samples]
        buffer = io.BytesIO()

        try:
            sf.write(buffer, segment, sr, format='WAV')
            buffer.seek(0)
        except Exception as e:
            st.error(f"❌ セグメントの書き出しに失敗しました: {e}")
            continue

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

        progress_value = min((i + segment_length_samples) / len(audio), 1.0)
        progress.progress(progress_value)

        if progress_value == 1.0:
            st.success("🎉 解析完了！")

    if not raw_results:
        st.write("⚠️ 有効なトラックは見つかりませんでした。")
    else:
        filtered_results = []
        prev_title, prev_artist = None, None
        for t, title, artist in raw_results:
            if (title, artist) != (prev_title, prev_artist):
                filtered_results.append((t, title, artist))
                prev_title, prev_artist = title, artist

        for t, title, artist in filtered_results:
            mmss = seconds_to_mmss(t)
            #st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
