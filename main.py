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

# === UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ")

try:
    uploaded_file = st.file_uploader("DJミックスのMP3をアップロード", type=["mp3"])
    if uploaded_file is not None:
        st.write(f"📄 ファイル名: {uploaded_file.name} / MIME: {uploaded_file.type}")
        st.write("⏳ 読み込み中...")

        try:
            audio_bytes = uploaded_file.read()
            print(f"[DEBUG] File size: {len(audio_bytes)} bytes")
            with io.BytesIO(audio_bytes) as f:
                audio, sr = sf.read(f)
            print(f"[DEBUG] 読み込み成功: {len(audio)} samples, {sr} Hz")
        except Exception as e:
            st.error(f"❌ 音声ファイルの読み込み失敗: {e}")
            print("[ERROR] sf.read failed:", e)
            st.stop()

        segment_length_sec = 30
        segment_len_samples = int(segment_length_sec * sr)
        total_samples = len(audio)
        raw_results = []
        displayed_titles = []
        progress = st.progress(0)

        for i in range(0, total_samples, segment_len_samples):
            try:
                segment = audio[i:i + segment_len_samples]
                buffer = io.BytesIO()
                sf.write(buffer, segment, sr, format="WAV")
                buffer.seek(0)
                result = recognize(buffer)

                if result.get("status", {}).get("msg") == "Success":
                    metadata = result['metadata']['music'][0]
                    title = metadata.get("title", "Unknown").strip()
                    artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()
                    if (title, artist) not in displayed_titles:
                        t_sec = i // sr
                        raw_results.append((t_sec, title, artist))
                        displayed_titles.append((title, artist))
                        mmss = seconds_to_mmss(t_sec)
                        st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
                else:
                    msg = result.get("status", {}).get("msg", "Unknown")
                    print(f"[DEBUG] No match at {i//sr}s → {msg}")

            except Exception as e:
                st.error(f"❌ セグメント処理失敗: {e}")
                print(f"[ERROR] Segment at {i//sr}s failed: {e}")

            progress.progress(min((i + segment_len_samples) / total_samples, 1.0))

        st.success("🎉 解析完了！")
        if not raw_results:
            st.write("⚠️ 有効なトラックは見つかりませんでした。")

except Exception as e:
    st.error(f"❌ アプリ全体でのエラー: {e}")
    print("[FATAL] Top-level error:", e)
