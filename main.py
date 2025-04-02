import time
import base64
import hashlib
import hmac
import requests
import io
import av
import numpy as np
import streamlit as st
import soundfile as sf

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

# === PyAVでMP3を読み込む関数（修正版＋ログ） ===
def read_mp3_with_pyav(file_like):
    try:
        container = av.open(file_like)
        stream = next(s for s in container.streams if s.type == 'audio')
        samples = []

        for packet in container.demux(stream):
            for frame in packet.decode():
                data = frame.to_ndarray().flatten()  # shape 統一
                samples.append(data)

        if not samples:
            raise ValueError("MP3から音声データを取得できませんでした。")

        audio = np.concatenate(samples).astype(np.float32) / 32768.0
        sr = stream.rate
        return audio, sr
    except Exception as e:
        raise RuntimeError(f"MP3読み込みエラー: {e}")

# === Streamlit UI ===
st.set_page_config(page_title="MP3対応 DJミックス識別アプリ", layout="centered")
st.title("🎧 MP3対応 DJ mix トラック識別アプリ")

uploaded_file = st.file_uploader("DJミックスのMP3ファイルをアップロード", type=["mp3"])

if uploaded_file is not None:
    try:
        st.write("📥 ファイルをアップロードしました。PyAVで読み込みを開始します...")

        audio, sr = read_mp3_with_pyav(uploaded_file)
        st.write(f"✅ 読み込み成功！サンプル数: {len(audio)}, サンプリングレート: {sr}")

        if audio.ndim > 1:
            st.write("🎚 ステレオ音源をモノラルに変換中...")
            audio = audio.mean(axis=1)

        # 残りの処理（分割、認識）...

    except Exception as e:
        st.error(f"❌ アプリ実行中にエラーが発生しました: {e}")
        st.stop()

    st.write(f"⏱ 音声長: {len(audio)/sr:.2f} 秒")
    st.write("🔄 30秒ごとに分割して解析を開始します...")

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
        else:
            st.write(f"🕒 {seconds_to_mmss(i // sr)} → ❌ 認識失敗")

        progress_value = min((i + segment_length_samples) / len(audio), 1.0)
        progress.progress(progress_value)

        if progress_value == 1.0:
            st.success("🎉 解析完了！")

    if not raw_results:
        st.write("⚠️ 有効なトラックは見つかりませんでした。")
    else:
        st.write("✅ 重複を除いた認識結果一覧：")
        filtered_results = []
        prev_title, prev_artist = None, None
        for t, title, artist in raw_results:
            if (title, artist) != (prev_title, prev_artist):
                filtered_results.append((t, title, artist))
                prev_title, prev_artist = title, artist

        for t, title, artist in filtered_results:
            mmss = seconds_to_mmss(t)
            st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
