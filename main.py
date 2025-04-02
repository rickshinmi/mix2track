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
    except requests.exceptions.RequestException as e:
        st.error(f"❌ APIリクエスト失敗: {e}")
        print(f"API request error: {e}")
        return {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}
    except Exception as e:
        st.error(f"❌ 不明なエラー: {e}")
        print(f"Unexpected error: {e}")
        return {"status": {"msg": f"Unexpected error: {e}", "code": "N/A"}}

# === Streamlit UI ===
st.set_page_config(page_title="DJミックス識別アプリ", layout="centered")
st.title("🎧 DJ mix トラック識別アプリ")

try:
    uploaded_file = st.file_uploader("DJミックスのMP3をアップロード", type=["mp3"])

    if uploaded_file is not None:
        st.write(f"📄 アップロードされたファイル名: {uploaded_file.name}")
        st.write("⏳ 音源を解析中...")

        try:
            with io.BytesIO(uploaded_file.read()) as f:
                audio, sr = sf.read(f)
        except Exception as e:
            st.error(f"🔴 音声ファイルの読み込みに失敗しました: {e}")
            print(f"sf.read() error: {e}")
            st.stop()

        duration = len(audio) / sr  # 秒
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
                st.error(f"🔴 セグメントのWAV変換に失敗: {e}")
                print(f"WAV conversion error: {e}")
                continue

            result = recognize(buffer)
            status = result.get("status", {})
            if status.get("msg") == "Success":
                metadata = result['metadata']['music'][0]
                title = metadata.get("title", "Unknown").strip()
                artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()

                if (title, artist) not in displayed_titles:
                    t_sec = i // sr
                    raw_results.append((t_sec, title, artist))
                    displayed_titles.append((title, artist))
                    mmss = seconds_to_mmss(t_sec)
                    st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")

            progress_value = min((i + segment_length_samples) / len(audio), 1.0)
            progress.progress(progress_value)
            if progress_value == 1.0:
                st.success("🎉 解析完了！")

        if not raw_results:
            st.write("⚠️ 有効なトラックは見つかりませんでした。")

except Exception as e:
    st.error(f"❌ アプリケーションエラー: {e}")
    print(f"Global error: {e}")
