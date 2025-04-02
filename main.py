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

st.set_page_config(page_title="🎧 DJミックス識別（MP3/WAV対応・堅牢）", layout="centered")
st.title("🎧 DJミックス識別アプリ")

uploaded_file = st.file_uploader("DJミックスファイルをアップロード（MP3またはWAV）", type=["mp3", "wav"])

# === ACRCloudヘルパー ===
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

def process_segment(segment_index, segment, sr, shown, results, stride_sec):
    mmss = seconds_to_mmss(segment_index * stride_sec)
    buf = io.BytesIO()
    sf.write(buf, segment, sr, format="WAV", subtype="FLOAT")
    buf.seek(0)

    if segment_index == 0:
        st.info("🧪 最初のセグメントをWAVで確認できます")
        st.audio(buf.getvalue(), format="audio/wav")
        st.download_button(
            label="⬇️ 最初のセグメントをダウンロード",
            data=buf.getvalue(),
            file_name="segment_00_00.wav",
            mime="audio/wav"
        )

    with st.spinner(f"🕒 {mmss} を識別中..."):
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

# === メイン処理 ===
if uploaded_file is not None:
    st.write("📥 ファイルを受け取りました。解析を開始します...")
    file_ext = uploaded_file.name.split('.')[-1].lower()
    sr = 44100
    segment_duration_sec = 20
    stride_sec = 30
    segment_len = sr * segment_duration_sec
    buffer_samples = []
    segment_index = 0
    results = []
    shown = []

    progress = st.progress(0)

    try:
        if file_ext == "wav":
            st.write("🔍 WAVファイルとして読み込みます")
            try:
                audio_data, sr_in = sf.read(uploaded_file)
            except Exception as e:
                st.error(f"❌ WAV読み込みに失敗しました: {e}")
                st.stop()

            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)  # モノラル化

            if sr_in != sr:
                st.error(f"⚠️ サンプリングレートが {sr_in}Hz です。44100Hz のみ対応しています。")
                st.stop()

            buffer_samples = audio_data.tolist()
            total_len = len(buffer_samples)

            while len(buffer_samples) >= segment_len:
                segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
                buffer_samples = buffer_samples[sr * stride_sec:]
                process_segment(segment_index, segment, sr, shown, results, stride_sec)
                segment_index += 1
                progress.progress(min((segment_index * stride_sec * sr) / total_len, 1.0))

        elif file_ext == "mp3":
            st.write("🔍 MP3ファイルとして読み込みます（ストリーミング処理）")
            try:
                file_like = io.BytesIO(uploaded_file.read())
                container = av.open(file_like)
                stream = next(s for s in container.streams if s.type == 'audio')
                resampler = AudioResampler(format="flt", layout="mono", rate=sr)
            except Exception as e:
                st.error(f"❌ MP3読み込みに失敗しました: {e}")
                st.stop()

            total_samples = 0
            for packet in container.demux(stream):
                for frame in packet.decode():
                    try:
                        resampled = resampler.resample(frame)
                    except Exception as e:
                        st.warning(f"⚠️ リサンプル中にエラー: {e}")
                        continue
                    for mono_frame in resampled:
                        try:
                            samples = mono_frame.to_ndarray().flatten()
                        except Exception as e:
                            st.warning(f"⚠️ ndarray変換中にエラー: {e}")
                            continue
                        buffer_samples.extend(samples)
                        total_samples += len(samples)

                        while len(buffer_samples) >= segment_len:
                            segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
                            buffer_samples = buffer_samples[sr * stride_sec:]
                            process_segment(segment_index, segment, sr, shown, results, stride_sec)
                            segment_index += 1
                            progress.progress(min((segment_index * stride_sec * sr) / total_samples, 1.0))

        # 最後のセグメントも処理（5秒以上あれば）
        if len(buffer_samples) >= sr * 5:
            segment = np.array(buffer_samples[:segment_len], dtype=np.float32)
            process_segment(segment_index, segment, sr, shown, results, stride_sec)

        st.success("🎉 識別完了！")

        if results:
            st.write("✅ 識別されたトラック一覧：")
            for mmss, title, artist in results:
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
        else:
            st.write("⚠️ トラックは識別されませんでした。")

    except Exception as e:
        st.error(f"❌ 処理全体で予期しないエラーが発生しました: {e}")
