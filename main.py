import streamlit as st
import av
import numpy as np

st.set_page_config(page_title="MP3読み込みテスト", layout="centered")
st.title("🧪 MP3読み込み検証アプリ（PyAV）")

uploaded_file = st.file_uploader("MP3ファイルをアップロード", type=["mp3"])

def read_mp3_with_pyav(file_like, max_frames=1000):
    try:
        file_like.seek(0)
        container = av.open(file_like)
        stream = next(s for s in container.streams if s.type == 'audio')
        samples = []

        for packet in container.demux(stream):
            for frame in packet.decode():
                if len(samples) >= max_frames:
                    break
                samples.append(frame.to_ndarray().flatten())

        if not samples:
            raise ValueError("MP3から音声データを取得できませんでした。")

        audio = np.concatenate(samples).astype(np.float32) / 32768.0
        sr = stream.rate
        return audio, sr
    except av.AVError as e:
        raise RuntimeError(f"PyAV エラー（AVError）: {e}")
    except Exception as e:
        raise RuntimeError(f"MP3読み込みエラー: {e}")

if uploaded_file is not None:
    st.write("📂 ファイルを受け取りました。読み込み開始...")

    try:
        audio, sr = read_mp3_with_pyav(uploaded_file)
        st.success("✅ MP3読み込み成功！")
        st.write(f"🔢 サンプル数: {len(audio)}")
        st.write(f"🎧 サンプリングレート: {sr}")
    except Exception as e:
        st.error(f"❌ エラー: {e}")
