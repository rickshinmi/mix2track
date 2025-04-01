import time
import base64
import hashlib
import hmac
import requests
import io
import streamlit as st
from pydub import AudioSegment
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
        return response.json()
    except Exception as e:
        return {"status": {"msg": "Request failed", "code": "N/A"}}

# === Streamlit UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ")

uploaded_file = st.file_uploader("DJミックスのMP3をアップロード", type=["mp3"])

if uploaded_file is not None:
    st.write("⏳ 音源を解析中...")

    # Use BytesIO to handle the file-like object
    with io.BytesIO(uploaded_file.read()) as f:
        # Load the MP3 file using pydub
        audio = AudioSegment.from_file(f)
        audio = audio.set_channels(1).set_frame_rate(44100)  # Mono and 44100 Hz for consistency

    duration = len(audio)  # in milliseconds
    segment_length_ms = 30 * 1000  # 30 seconds
    segment_length_samples = segment_length_ms  # works with pydub directly

    raw_results = []
    progress = st.progress(0)

    # List to store previously displayed titles and artists
    displayed_titles = []

    for i in range(0, duration, segment_length_ms):
        segment = audio[i:i + segment_length_ms]
        buffer = io.BytesIO()

        # Export the segment to WAV and pass it to the recognition API
        segment.export(buffer, format="wav")
        buffer.seek(0)
        result = recognize(buffer)

        if result.get("status", {}).get("msg") == "Success":
            metadata = result['metadata']['music'][0]
            title = metadata.get("title", "Unknown").strip()
            artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()

            # Check if the song has already been displayed
            if (title, artist) not in displayed_titles:
                raw_results.append((i // 1000, title, artist))  # Convert ms to seconds
                displayed_titles.append((title, artist))  # Add to displayed titles list

                # Display results as they come in
                mmss = seconds_to_mmss(i // 1000)
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")

        # Update progress bar (not exceeding 1.0)
        progress_value = min((i + segment_length_ms) / duration, 1.0)
        progress.progress(progress_value)

        # Display completion message when progress reaches 100%
        if progress_value == 1.0:
            st.success("🎉 解析完了！")

    # === Results Display (remove duplicates and show sequentially) ===
    if not raw_results:
        st.write("⚠️ 有効なトラックは見つかりませんでした。")
    else:
        filtered_results = []
        prev_title, prev_artist = None, None
        for t, title, artist in raw_results:
            if (title, artist) != (prev_title, prev_artist):
                filtered_results.append((t, title, artist))
                prev_title, prev_artist = title, artist

        # Show results in plain text
        for t, title, artist in filtered_results:
            mmss = seconds_to_mmss(t)
            st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
