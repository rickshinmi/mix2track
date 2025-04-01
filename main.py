import streamlit as st
import soundfile as sf

st.title("テスト: WAVファイル読み込み")

uploaded_file = st.file_uploader("WAVファイルを選択", type=["wav"])

if uploaded_file:
    try:
        audio, sr = sf.read(uploaded_file)
        st.success(f"読み込み成功！長さ: {len(audio)/sr:.2f} 秒, サンプリングレート: {sr}")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
