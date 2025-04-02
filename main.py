import streamlit as st
import av
import numpy as np
import soundfile as sf
import io
from av.audio.resampler import AudioResampler

st.set_page_config(page_title="MP3 → WAV（安定リサンプル）", layout="centered")
st.title("🎧 安定版 MP3 → WAV（AudioResampler対応）")

uploaded_file = st.file_uploader("MP3ファイルをアップロード", type=["mp3"])

def read_mp3_with_stable_resampler(file_like, max_frames=1000):
    try:
        file_like.seek(0)
        container = av.open(file_like)
        stream = next(s for s in container.streams if s.type == 'audio')

        # 🎯 PyAVが安定する推奨設定：mono, float, 44100Hz
        resampler = AudioResampler(format="flt", layout="mono", rate=44100)
        samples = []

        for packet in container.demux(stream):
            for frame in packet.decode():
                frame = resampler.resample(frame)
                arr = frame.to_ndarray().flatten()  # 既にmono + float
                if len(samples) == 0:
                    st.write("🧪 最初のフレーム shape:", arr.shape)
                    st.write("🔍 最初のフレーム 値（先頭10個）:", arr[:10])
                if len(samples) >= max_frames:
                    break
                samples.append(arr)

        if not samples:
            raise ValueError("MP3から音声データを取得できませんでした。")

        audio = np.concatenate(samples).astype(np.float32)
        max_val = np.max(np.abs(audio))
        st.write("🔊 最大音量値（正規化前）:", max_val)

        if max_val > 0:
            audio = (audio / max_val) * 0.9

        return audio, 44100  # resamplerで固定済み
    except Exception as e:
        raise RuntimeError(f"リサンプル処理中のエラー: {e}")

if uploaded_file is not None:
    st.write("📂 ファイルを受け取りました。PyAVで読み込み中...")

    try:
        audio, sr = read_mp3_with_stable_resampler(uploaded_file)
        st.success(f"✅ MP3読み込み成功！サンプル数: {len(audio)}, サンプリングレート: {sr}")
    except Exception as e:
        st.error(f"❌ 読み込み失敗: {e}")
        st.stop()

    st.write("✂️ 最初の30秒分を切り出して、WAVセグメントに変換します...")

    try:
        segment = audio[:int(30 * sr)]
        buffer = io.BytesIO()
        sf.write(buffer, segment, sr, format="WAV", subtype="FLOAT")
        st.success("✅ WAVセグメント書き出し成功！（float32）")
        st.download_button("⬇️ セグメントをダウンロード", buffer.getvalue(), file_name="segment.wav", mime="audio/wav")
    except Exception as e:
        st.error(f"❌ 書き出し失敗: {e}")
