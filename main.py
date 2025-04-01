import os
import time
import base64
import hashlib
import hmac
import requests
import io
import streamlit as st
import librosa
import numpy as np

# === ACRCloud Credentials ===
access_key = st.secrets["api_keys"]["access_key"]
access_secret = st.secrets["api_keys"]["access_secret"]
host = "identify-ap-southeast-1.acrcloud.com"
requrl = f"https://{host}/v1/identify"

# === Helper Functions ===
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

    # librosaで音声ファイルを読み込み、データをnumpy配列として取得
    audio, sr = librosa.load(uploaded_file, sr=44100)  # sr=44100で読み込む
    duration = len(audio) / sr  # サンプリングレートで音声の長さを計算
    segment_length_ms = 30 * 1000  # 30秒で固定
    segment_length_samples = int(segment_length_ms / 1000 * sr)  # サンプル数に変換

    raw_results = []
    progress = st.progress(0)

    # 以前に表示した曲を保存するリスト
    displayed_titles = []

    for i in range(0, len(audio), segment_length_samples):
        segment = audio[i:i + segment_length_samples]
        buffer = io.BytesIO()

        # ここでnumpy配列をWAV形式に変換して、バッファに保存
        librosa.output.write_wav(buffer, segment, sr)  # librosaでWAV形式に保存
        buffer.seek(0)
        result = recognize(buffer)

        if result.get("status", {}).get("msg") == "Success":
            metadata = result['metadata']['music'][0]
            title = metadata.get("title", "Unknown").strip()
            artist = metadata.get("artists", [{}])[0].get("name", "Unknown").strip()

            # 同じ曲が表示されていないかチェック
            if (title, artist) not in displayed_titles:
                raw_results.append((i // sr, title, artist))  # サンプル数を時間に変換
                displayed_titles.append((title, artist))  # 表示した曲をリストに追加

                # 逐次結果表示
                mmss = seconds_to_mmss(i / sr)
                st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")

        # 更新進捗バー（1.0を超えないように）
        progress_value = min((i + segment_length_samples) / len(audio), 1.0)
        progress.progress(progress_value)

        # 進捗が100%になったタイミングで「解析完了！」メッセージを表示
        if progress_value == 1.0:
            st.success("🎉 解析完了！")

    # === 結果表示（重複なし、逐次表示のみ）
    if not raw_results:
        st.write("⚠️ 有効なトラックは見つかりませんでした。")
    else:
        # 重複を除いて表示
        filtered_results = []
        prev_title, prev_artist = None, None
        for t, title, artist in raw_results:
            if (title, artist) != (prev_title, prev_artist):
                filtered_results.append((t, title, artist))
                prev_title, prev_artist = title, artist

        # 結果表示（平文）
        for t, title, artist in filtered_results:
            mmss = seconds_to_mmss(t)
            st.write(f"🕒 {mmss} → 🎵 {title} / {artist}")
