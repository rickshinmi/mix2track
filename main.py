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

# === ACRCloudリクエスト ===
def build_signature():
    http_method = "POST"
    http_uri = "/v1/identify"
    data_type = "audio"
    signature_version = "1"
    timestamp = time.time()
    string_to_sign = '\n'.join([http_method, http_uri, access_key, data_type, signature_version, str(timestamp)])
    sign = base64.b64encode(
        hmac.new(access_secret.encode('ascii'), string_to_sign.encode('ascii'), digestmod=hashlib.sha1).digest()
    ).decode('ascii')
    return sign, timestamp

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
        return start_time_sec, {"status": {"msg": f"Request failed: {e}", "code": "N/A"}}

def seconds_to_mmss(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

# === メイン処理 ===
st.set_page_config(page_title="🎧 THE TRACKLIST GUY", layout="centered")
st.title("🎧 THE TRACKLIST GUY")

uploaded_file = st.file_uploader("DJミックスファイルをアップロード（MP3またはWAV）", type=["mp3", "wav"])

if uploaded_file is not None:
    st.write("📥 ファイルを受け取りました。セグメントを準備中...")
    file_ext = uploaded_file.name.split('.')[-1].lower()
    sr = 44100
    segment_duration_sec = 25
    stride_sec = 30
    segment_len = sr * segment_duration_sec
    segments = []
    total_duration_sec = 0

    try:
        if file_ext == "wav":
            audio_data, sr_in = sf.read(uploaded_file)
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
            if sr_in != sr:
                st.error(f"⚠️ サンプリングレートが {sr_in}Hz です。44100Hz のみ対応しています。")
                st.stop()
            total_duration_sec = len(audio_data) / sr
            buffer_samples = audio_data.tolist()
            start_time_sec = 0
            while len(buffer_samples) >= segment_len:
                segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
                segments.append((start_time_sec, segment))
                buffer_samples = buffer_samples[sr * stride_sec:]
                start_time_sec += stride_sec
            if len(buffer_samples) >= sr * 5:
                segments.append((start_time_sec, np.array(buffer_samples[:segment_len], dtype=np.float32)))

        elif file_ext == "mp3":
            raw_bytes = uploaded_file.read()
            container = av.open(io.BytesIO(raw_bytes))
            stream = next(s for s in container.streams if s.type == 'audio')
            if stream.duration is not None:
                total_duration_sec = float(stream.duration * stream.time_base)
            else:
                total_duration_sec = 0  # fallback
            resampler = AudioResampler(format="flt", layout="mono", rate=sr)
            buffer_samples = []
            start_time_sec = 0
            for packet in container.demux(stream):
                for frame in packet.decode():
                    try:
                        resampled = resampler.resample(frame)
                    except:
                        continue
                    for mono_frame in resampled:
                        try:
                            samples = mono_frame.to_ndarray().flatten()
                        except:
                            continue
                        buffer_samples.extend(samples)
                        while len(buffer_samples) >= segment_len:
                            segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
                            segments.append((start_time_sec, segment))
                            buffer_samples = buffer_samples[sr * stride_sec:]
                            start_time_sec += stride_sec
            if len(buffer_samples) >= sr * 5:
                segments.append((start_time_sec, np.array(buffer_samples[:segment_len], dtype=np.float32)))

        if total_duration_sec == 0 and segments:
            last_start = segments[-1][0]
            total_duration_sec = last_start + segment_duration_sec

        st.write(f"⏱ 再生時間: {seconds_to_mmss(total_duration_sec)}")
        st.write(f"🔢 セグメント数: {len(segments)}")
        st.write("🚀 識別処理を開始します...")

        progress = st.progress(0)
        progress_text = st.empty()
        results = []
        shown = []
        max_identified_time = 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_time = {
                executor.submit(recognize_segment, start_sec, seg, sr): start_sec
                for start_sec, seg in segments
            }

            for i, future in enumerate(as_completed(future_to_time)):
                start_time_sec, result = future.result()
                mmss = seconds_to_mmss(start_time_sec)

                if result.get("status", {}).get("msg") == "Success":
                    music = result['metadata']['music'][0]
                    title = music.get("title", "Unknown")
                    artist = music.get("artists", [{}])[0].get("name", "Unknown")
                    if (title, artist) not in shown:
                        shown.append((title, artist))
                        results.append((mmss, title, artist))
                        st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")

                # 🎯 再生時間ベース進捗
                max_identified_time = max(max_identified_time, start_time_sec)
                progress_ratio = min(max_identified_time / total_duration_sec, 1.0)
                progress.progress(progress_ratio)
                progress_text.text(f"進捗: {seconds_to_mmss(max_identified_time)} / {seconds_to_mmss(total_duration_sec)} （{progress_ratio * 100:.1f}%）")

        st.success("🎉 識別完了！")

    except Exception as e:
        st.error(f"❌ 処理エラー: {e}")
