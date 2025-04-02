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

# === ACRCloud API設定 ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

st.set_page_config(page_title="🎧 DJミックス識別（ストリーミング）", layout="centered")
st.title("🎧 DJミックス識別（10秒ごとリアルタイム処理）")

uploaded_file = st.file_uploader("MP3ファイルをアップロード", type=["mp3"])

# === ACRCloud認識ヘルパー ===
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

# === メイン処理 ===
if uploaded_file is not None:
    st.write("📥 ファイルを受け取りました。ストリーミング処理を開始...")

    try:
        file_like = io.BytesIO(uploaded_file.read())
        container = av.open(file_like)
        stream = next(s for s in container.streams if s.type == 'audio')
        sr = 44100
        resampler = AudioResampler(format="flt", layout="mono", rate=sr)
        st.write("🔧 リサンプラー初期化済")

        segment_duration_sec = 20
        segment_len = sr * segment_duration_sec
        stride_sec = 60

        buffer_samples = []
        total_samples = 0
        segment_index = 0
        results = []
        shown = []

        progress = st.progress(0)

        for packet in container.demux(stream):
            for frame in packet.decode():
                resampled = resampler.resample(frame)
                for mono_frame in resampled:
                    samples = mono_frame.to_ndarray().flatten()
                    buffer_samples.extend(samples)
                    total_samples += len(samples)

                    while len(buffer_samples) >= segment_len:
                        segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
                        buffer_samples = buffer_samples[sr * stride_sec:]  # 30秒スキップ

                        mmss = seconds_to_mmss(segment_index * stride_sec)

                        buf = io.BytesIO()
                        sf.write(buf, segment, sr, format="WAV", subtype="FLOAT")
                        buf.seek(0)

                        # ✅ 最初のセグメントだけWAVで確認・DL可能
                        if segment_index == 0:
                            st.info("🧪 最初のセグメントをWAVで確認できます")
                            st.audio(buf.getvalue(), format="audio/wav")
                            st.download_button(
                                label="⬇️ 最初の10秒WAVをダウンロード",
                                data=buf.getvalue(),
                                file_name="segment_00_00.wav",
                                mime="audio/wav"
                            )

                        with st.spinner(f"{mmss} を識別中..."):
                            result = recognize(buf)

                        if result.get("status", {}).get("msg") == "Success":
                            music = result['metadata']['music'][0]
                            title = music.get("title", "Unknown")
                            artist = music.get("artists", [{}])[0].get("name", "Unknown")
                            if (title, artist) not in shown:
                                shown.append((title, artist))
                                results.append((mmss, title, artist))
                                st.success(f"🕒 {mmss} → 🎶 {title} / {artist}")
                        else:
                            st.warning(f"🕒 {mmss} → ❌ 未識別")

                        segment_index += 1
                        progress.progress(min((segment_index * stride_sec * sr) / total_samples, 1.0))

        st.success("🎉 識別完了！")

        if results:
            st.write("✅ 識別されたトラック一覧：")
            for mmss, title, artist in results:
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
        else:
            st.write("⚠️ トラックは識別されませんでした。")
    except Exception as e:
        st.error(f"❌ エラー: {e}")
