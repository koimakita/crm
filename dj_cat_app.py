import streamlit as st
import asyncio
import sys
import os
import json
import re
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from youtube_dj_tracker import (
    get_youtube_video_info,
    extract_tracks_from_chapters,
    extract_tracks_from_description,
    search_apple_music,
    _get_audio_stream_url,
    _extract_segment_ffmpeg,
    _seconds_to_timestamp,
)

st.set_page_config(
    page_title="DJ CAT 🐱",
    page_icon="🐱",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #08080f !important;
}
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at top, #1a0533 0%, #08080f 60%) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #0d0d1a !important; }

h1, h2, h3 { font-family: 'Orbitron', sans-serif !important; }

.cat-wrapper {
    display: flex;
    justify-content: center;
    margin: 0 auto 8px;
    filter: drop-shadow(0 0 24px #a855f7) drop-shadow(0 0 48px #7c3aed);
    animation: float 3s ease-in-out infinite;
}
@keyframes float {
    0%,100% { transform: translateY(0px); }
    50%      { transform: translateY(-10px); }
}

.app-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 2.2em;
    font-weight: 900;
    text-align: center;
    background: linear-gradient(90deg, #a855f7, #06b6d4, #f472b6, #a855f7);
    background-size: 300%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 4s linear infinite;
    letter-spacing: 2px;
    margin-bottom: 4px;
}
.app-sub {
    text-align: center;
    color: #7c6a8e;
    font-size: 0.9em;
    margin-bottom: 24px;
    font-family: 'Inter', sans-serif;
}
@keyframes shimmer {
    0%   { background-position: 0% }
    100% { background-position: 300% }
}

div[data-testid="stTextInput"] input {
    background: #12102a !important;
    border: 1.5px solid #3d1f6e !important;
    border-radius: 10px !important;
    color: #e0d0f0 !important;
    font-family: 'Inter', sans-serif !important;
    padding: 12px 16px !important;
    transition: border-color .2s;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 3px rgba(168,85,247,.2) !important;
}
div[data-testid="stTextInput"] label {
    color: #9d7fc0 !important;
    font-family: 'Inter', sans-serif !important;
}

div[data-testid="stSlider"] label { color: #9d7fc0 !important; }

div[data-testid="stButton"] > button {
    width: 100%;
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Orbitron', sans-serif !important;
    font-size: 1em !important;
    font-weight: 700 !important;
    letter-spacing: 2px !important;
    padding: 14px !important;
    cursor: pointer !important;
    transition: all .2s !important;
    box-shadow: 0 0 20px rgba(168,85,247,.4) !important;
}
div[data-testid="stButton"] > button:hover {
    box-shadow: 0 0 35px rgba(168,85,247,.7) !important;
    transform: translateY(-2px) !important;
}

.track-card {
    background: linear-gradient(135deg, #120824, #0e1628);
    border: 1px solid #3d1f6e;
    border-radius: 14px;
    padding: 16px 20px;
    margin: 10px 0;
    transition: all .2s;
    box-shadow: 0 2px 12px rgba(168,85,247,.15);
}
.track-card:hover {
    border-color: #a855f7;
    box-shadow: 0 0 20px rgba(168,85,247,.35);
    transform: translateX(4px);
}
.track-num {
    color: #5b3a8a;
    font-family: 'Orbitron', sans-serif;
    font-size: .8em;
}
.track-ts {
    background: #1e1040;
    color: #06b6d4;
    font-family: 'Orbitron', sans-serif;
    font-size: .75em;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid #0e7490;
}
.track-title {
    color: #f0e8ff;
    font-weight: 600;
    font-size: 1em;
    font-family: 'Inter', sans-serif;
    margin: 6px 0 2px;
}
.track-genre {
    color: #f472b6;
    font-size: .8em;
    font-family: 'Inter', sans-serif;
}
.track-link a {
    color: #a855f7 !important;
    font-size: .85em;
    font-family: 'Inter', sans-serif;
    text-decoration: none;
}
.track-link a:hover { text-decoration: underline; }
.no-result {
    color: #4a3060;
    font-size: .8em;
    font-style: italic;
    font-family: 'Inter', sans-serif;
}
.stat-box {
    background: #120824;
    border: 1px solid #3d1f6e;
    border-radius: 10px;
    padding: 12px 16px;
    text-align: center;
    color: #c084fc;
    font-family: 'Orbitron', sans-serif;
    font-size: .9em;
}

div[data-testid="stDownloadButton"] > button {
    width: 100%;
    background: transparent !important;
    color: #a855f7 !important;
    border: 1.5px solid #a855f7 !important;
    border-radius: 10px !important;
    font-family: 'Orbitron', sans-serif !important;
    font-size: .85em !important;
    letter-spacing: 1px !important;
    transition: all .2s !important;
}
div[data-testid="stDownloadButton"] > button:hover {
    background: #1a0533 !important;
    box-shadow: 0 0 15px rgba(168,85,247,.4) !important;
}

div[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #7c3aed, #06b6d4) !important;
}
</style>
""", unsafe_allow_html=True)

CAT_SVG = """
<svg width="160" height="180" viewBox="0 0 160 180" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="2.5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="bg" cx="50%" cy="45%">
      <stop offset="0%" stop-color="#3d1f6e"/>
      <stop offset="100%" stop-color="#1a0a2e"/>
    </radialGradient>
  </defs>
  <!-- Ears -->
  <polygon points="42,52 28,14 64,44" fill="#1a0a2e" stroke="#a855f7" stroke-width="1.5"/>
  <polygon points="118,52 132,14 96,44" fill="#1a0a2e" stroke="#a855f7" stroke-width="1.5"/>
  <polygon points="44,49 33,21 61,43" fill="#c084fc" opacity=".7"/>
  <polygon points="116,49 127,21 99,43" fill="#c084fc" opacity=".7"/>
  <!-- Head -->
  <ellipse cx="80" cy="80" rx="42" ry="40" fill="url(#bg)" stroke="#a855f7" stroke-width="1.5"/>
  <!-- Headphone arc -->
  <path d="M40,76 Q42,38 80,36 Q118,38 120,76"
        stroke="#06b6d4" stroke-width="3.5" fill="none" filter="url(#glow)"/>
  <!-- Headphone pads -->
  <rect x="32" y="70" width="16" height="20" rx="5" fill="#0a1628" stroke="#06b6d4" stroke-width="2" filter="url(#glow)"/>
  <rect x="112" y="70" width="16" height="20" rx="5" fill="#0a1628" stroke="#06b6d4" stroke-width="2" filter="url(#glow)"/>
  <!-- Sunglasses -->
  <rect x="54" y="74" width="20" height="13" rx="6.5" fill="#0a0515" stroke="#a855f7" stroke-width="1.8" filter="url(#glow)"/>
  <rect x="86" y="74" width="20" height="13" rx="6.5" fill="#0a0515" stroke="#a855f7" stroke-width="1.8" filter="url(#glow)"/>
  <line x1="74" y1="80" x2="86" y2="80" stroke="#a855f7" stroke-width="1.8"/>
  <line x1="57" y1="77" x2="62" y2="82" stroke="#c084fc" stroke-width="1" opacity=".5"/>
  <line x1="89" y1="77" x2="94" y2="82" stroke="#c084fc" stroke-width="1" opacity=".5"/>
  <!-- Nose -->
  <ellipse cx="80" cy="94" rx="3.5" ry="2.5" fill="#f472b6"/>
  <!-- Mouth -->
  <path d="M75,97 Q80,102 85,97" stroke="#f472b6" stroke-width="1.5" fill="none"/>
  <!-- Whiskers -->
  <line x1="38" y1="92" x2="68" y2="95" stroke="#555" stroke-width="1" opacity=".7"/>
  <line x1="38" y1="98" x2="68" y2="98" stroke="#555" stroke-width="1" opacity=".7"/>
  <line x1="92" y1="95" x2="122" y2="92" stroke="#555" stroke-width="1" opacity=".7"/>
  <line x1="92" y1="98" x2="122" y2="98" stroke="#555" stroke-width="1" opacity=".7"/>
  <!-- Body -->
  <ellipse cx="80" cy="148" rx="38" ry="34" fill="url(#bg)" stroke="#a855f7" stroke-width="1.5"/>
  <!-- Paws -->
  <ellipse cx="45" cy="158" rx="16" ry="9" fill="#1a0a2e" stroke="#a855f7" stroke-width="1.2" transform="rotate(-25,45,158)"/>
  <ellipse cx="115" cy="158" rx="16" ry="9" fill="#1a0a2e" stroke="#a855f7" stroke-width="1.2" transform="rotate(25,115,158)"/>
  <!-- Vinyl records -->
  <circle cx="38" cy="172" r="14" fill="#0d0820" stroke="#a855f7" stroke-width="1.5"/>
  <circle cx="38" cy="172" r="6" fill="#1a0a2e" stroke="#7c3aed" stroke-width="1"/>
  <circle cx="38" cy="172" r="2.5" fill="#a855f7" filter="url(#glow)"/>
  <circle cx="122" cy="172" r="14" fill="#0d0820" stroke="#a855f7" stroke-width="1.5"/>
  <circle cx="122" cy="172" r="6" fill="#1a0a2e" stroke="#7c3aed" stroke-width="1"/>
  <circle cx="122" cy="172" r="2.5" fill="#a855f7" filter="url(#glow)"/>
  <!-- Floating notes -->
  <text x="136" y="48" font-size="14" fill="#a855f7" opacity=".9" filter="url(#glow)">♪</text>
  <text x="14" y="42" font-size="11" fill="#06b6d4" opacity=".8" filter="url(#glow)">♫</text>
  <text x="142" y="78" font-size="9" fill="#f472b6" opacity=".7">♩</text>
</svg>
"""


async def run_shazam_with_progress(video_url: str, duration: int, interval: int):
    try:
        from shazamio import Shazam
    except ImportError:
        st.error("pip install shazamio が必要です")
        return []

    shazam = Shazam()
    tracks = []
    seen: set[str] = set()
    sample_times = list(range(30, max(31, duration - 30), interval))

    status_text = st.empty()
    progress_bar = st.progress(0)
    log_area = st.empty()
    log_lines = []

    status_text.markdown("🎵 **音声URLを取得中...**")
    stream_url = _get_audio_stream_url(video_url)
    if not stream_url:
        st.error("音声URLの取得に失敗しました")
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, start_sec in enumerate(sample_times):
            ts = _seconds_to_timestamp(start_sec)
            pct = (i + 1) / len(sample_times)
            status_text.markdown(f"🐱 **[{i+1}/{len(sample_times)}] {ts} を解析中...**")
            progress_bar.progress(pct)

            seg_file = os.path.join(tmpdir, f"seg_{i}.mp3")
            seg_file = _extract_segment_ffmpeg(stream_url, start_sec, 20, seg_file)

            if not seg_file:
                log_lines.append(f"  `{ts}` → 切り出し失敗")
                log_area.markdown("\n".join(log_lines))
                continue

            try:
                result = await shazam.recognize(seg_file)
            except Exception:
                log_lines.append(f"  `{ts}` → 認識エラー")
                log_area.markdown("\n".join(log_lines))
                continue

            if not result or "track" not in result:
                log_lines.append(f"  `{ts}` → 認識不可")
                log_area.markdown("\n".join(log_lines))
                continue

            track = result["track"]
            title = track.get("title", "")
            artist = track.get("subtitle", "")
            key = f"{title}|{artist}".lower()

            if not title or key in seen:
                log_lines.append(f"  `{ts}` → 既出 or 不明")
                log_area.markdown("\n".join(log_lines))
                continue

            seen.add(key)
            apple = search_apple_music(f"{artist} {title}")
            apple_url = apple["apple_music_url"] if apple else ""
            genre = apple["genre"] if apple else ""

            tracks.append({
                "timestamp": ts,
                "title": title,
                "artist": artist,
                "apple_music_url": apple_url,
                "genre": genre,
            })
            log_lines.append(f"  `{ts}` → ✅ **{artist} - {title}**")
            log_area.markdown("\n".join(log_lines))
            await asyncio.sleep(0.5)

    progress_bar.empty()
    status_text.empty()
    log_area.empty()
    return tracks


def build_txt(video_title: str, channel: str, tracks: list) -> str:
    lines = [
        "=" * 60,
        f"動画: {video_title}",
        f"チャンネル: {channel}",
        "取得方法: Shazam",
        "=" * 60,
        f"\n全{len(tracks)}曲\n",
    ]
    for i, t in enumerate(tracks, 1):
        ts = f"[{t['timestamp']}] " if t.get("timestamp") else ""
        lines.append(f"{i:02d}. {ts}{t.get('artist', '')} - {t.get('title', '')}")
        if t.get("genre"):
            lines.append(f"    ジャンル: {t['genre']}")
        if t.get("apple_music_url"):
            lines.append(f"    Apple Music: {t['apple_music_url']}")
        else:
            lines.append("    Apple Music: 見つかりませんでした")
        lines.append("")
    return "\n".join(lines)


# ── UI ──────────────────────────────────────────────
st.markdown(f'<div class="cat-wrapper">{CAT_SVG}</div>', unsafe_allow_html=True)
st.markdown('<p class="app-title">DJ CAT TRACKER</p>', unsafe_allow_html=True)
st.markdown('<p class="app-sub">YouTube DJ動画から曲を解析 → Apple Musicリンクを一覧表示</p>',
            unsafe_allow_html=True)

url = st.text_input("", placeholder="🔗  YouTube URL を貼り付けてください", label_visibility="collapsed")

interval = st.select_slider(
    "サンプリング間隔（短いほど多くの曲を検出、時間もかかる）",
    options=[60, 90, 120, 180, 240, 300],
    value=180,
    format_func=lambda x: f"{x//60}分おき",
)

run = st.button("🎧  EXTRACT TRACKS")

if run and url:
    st.divider()

    with st.spinner("動画情報を取得中..."):
        try:
            info = get_youtube_video_info(url)
        except Exception as e:
            st.error(f"動画情報の取得に失敗しました: {e}")
            st.stop()

    col1, col2 = st.columns([1, 3])
    with col1:
        if info.get("thumbnail"):
            st.image(info["thumbnail"], use_column_width=True)
    with col2:
        st.markdown(f"### {info.get('title','')}")
        st.markdown(f"<span style='color:#7c6a8e'>チャンネル: {info.get('channel','')}</span>",
                    unsafe_allow_html=True)
        dur = info.get("duration", 0)
        if dur:
            st.markdown(f"<span style='color:#7c6a8e'>長さ: {_seconds_to_timestamp(dur)}</span>",
                        unsafe_allow_html=True)

    # チャプター / 説明文からトラックを取得
    raw_tracks = extract_tracks_from_chapters(info.get("chapters", []))
    method = "チャプター"
    if not raw_tracks:
        raw_tracks = extract_tracks_from_description(info.get("description", ""))
        method = "説明文"

    result_tracks = []

    if raw_tracks:
        st.success(f"{method}から **{len(raw_tracks)}曲** を検出しました")
        prog = st.progress(0)
        for i, t in enumerate(raw_tracks):
            prog.progress((i + 1) / len(raw_tracks))
            apple = search_apple_music(t.get("title", ""))
            result_tracks.append({
                "timestamp": t.get("timestamp", ""),
                "title": apple["track_name"] if apple else t.get("title", ""),
                "artist": apple["artist_name"] if apple else "",
                "genre": apple.get("genre", "") if apple else "",
                "apple_music_url": apple["apple_music_url"] if apple else "",
            })
            time.sleep(0.2)
        prog.empty()
    else:
        st.info("説明文にトラックリストがありません。Shazam音声認識で解析します 🎵")
        result_tracks = asyncio.run(
            run_shazam_with_progress(url, info.get("duration", 0), interval)
        )

    st.divider()

    if not result_tracks:
        st.warning("曲が見つかりませんでした。")
    else:
        st.markdown(f'<div class="stat-box">🎵 {len(result_tracks)} 曲 を検出しました</div>',
                    unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        for i, t in enumerate(result_tracks, 1):
            ts_badge = (f'<span class="track-ts">{t["timestamp"]}</span> '
                        if t.get("timestamp") else "")
            genre_line = (f'<div class="track-genre">🎼 {t["genre"]}</div>'
                          if t.get("genre") else "")
            if t.get("apple_music_url"):
                link_line = (f'<div class="track-link">'
                             f'<a href="{t["apple_music_url"]}" target="_blank">'
                             f'🍎 Apple Musicで開く</a></div>')
            else:
                link_line = '<div class="no-result">Apple Music: 見つかりませんでした</div>'

            name = f'{t.get("artist","")} - {t.get("title","")}' if t.get("artist") else t.get("title", "")

            st.markdown(f"""
<div class="track-card">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <span class="track-num">#{i:02d}</span>
    {ts_badge}
  </div>
  <div class="track-title">{name}</div>
  {genre_line}
  {link_line}
</div>""", unsafe_allow_html=True)

        # txt ダウンロード
        txt = build_txt(info.get("title", ""), info.get("channel", ""), result_tracks)
        safe = re.sub(r'[\\/:*?"<>|]', "_", info.get("title", "track"))[:50]
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            "📄  TXTをダウンロード",
            data=txt.encode("utf-8"),
            file_name=f"{safe}.txt",
            mime="text/plain",
        )

elif run and not url:
    st.warning("URLを入力してください")
