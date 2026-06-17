"""
DJ Track Extractor - Streamlitページ
YouTube DJ動画からトラックリストを取得し、Apple Musicリンクを表示する
"""

import streamlit as st
import time
import re
import json
import requests
import sys


def _seconds_to_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def get_youtube_video_info(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError:
        st.error("yt-dlpが必要です。`pip install yt-dlp` でインストールしてください。")
        return {}

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "no_playlist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "chapters": info.get("chapters", []),
            "channel": info.get("channel", ""),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration", 0),
        }
    except Exception as e:
        st.error(f"YouTube動画の取得に失敗しました: {e}")
        return {}


def extract_tracks_from_chapters(chapters: list) -> list:
    return [
        {
            "title": ch.get("title", "").strip(),
            "timestamp": _seconds_to_timestamp(ch.get("start_time", 0)),
        }
        for ch in chapters
        if ch.get("title", "").strip()
    ]


def extract_tracks_from_description(description: str) -> list:
    tracks = []
    lines = description.split("\n")

    timestamp_pattern = re.compile(
        r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—:．]?\s*(.+)$"
    )
    numbered_pattern = re.compile(r"^\d{1,2}[.)]\s+(.+)$")
    music_section_headers = re.compile(
        r"(track\s*list|tracklist|music\s+in\s+this\s+video|使用曲|楽曲|曲目|playlist|set\s*list)",
        re.IGNORECASE,
    )

    in_music_section = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if music_section_headers.search(line):
            in_music_section = True
            continue

        ts_match = timestamp_pattern.match(line)
        if ts_match:
            tracks.append(
                {
                    "timestamp": ts_match.group(1),
                    "title": ts_match.group(2).strip(),
                }
            )
            in_music_section = True
            continue

        if in_music_section:
            num_match = numbered_pattern.match(line)
            if num_match:
                tracks.append({"title": num_match.group(1).strip()})

    return tracks


def search_apple_music(track_query: str) -> dict | None:
    url = "https://itunes.apple.com/search"
    params = {
        "term": track_query,
        "entity": "song",
        "limit": 1,
        "media": "music",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            result = data["results"][0]
            return {
                "track_name": result.get("trackName", ""),
                "artist_name": result.get("artistName", ""),
                "album": result.get("collectionName", ""),
                "apple_music_url": result.get("trackViewUrl", ""),
                "artwork_url": result.get("artworkUrl100", "").replace(
                    "100x100", "300x300"
                ),
            }
    except Exception:
        pass
    return None


def show_dj_tracker_page():
    st.title("🎧 DJ Track Extractor")
    st.markdown("YouTube DJ動画から曲リストを取得し、Apple Musicのリンクを表示します。")

    url = st.text_input(
        "YouTube URL",
        placeholder="https://www.youtube.com/watch?v=...",
    )

    if not url:
        st.info("YouTubeのDJ動画URLを入力してください。")
        return

    if st.button("トラックリストを取得", type="primary"):
        with st.spinner("動画情報を取得中..."):
            info = get_youtube_video_info(url)

        if not info:
            return

        st.subheader(info.get("title", ""))
        col1, col2 = st.columns([1, 3])
        if info.get("thumbnail"):
            with col1:
                st.image(info["thumbnail"], use_container_width=True)
        with col2:
            st.write(f"**チャンネル:** {info.get('channel', '')}")
            duration = info.get("duration", 0)
            if duration:
                st.write(f"**長さ:** {_seconds_to_timestamp(duration)}")

        # トラック抽出
        tracks = extract_tracks_from_chapters(info.get("chapters", []))
        source = "チャプター"
        if not tracks:
            tracks = extract_tracks_from_description(info.get("description", ""))
            source = "説明文"

        if not tracks:
            st.warning("曲情報が見つかりませんでした。")
            with st.expander("動画の説明文を確認する"):
                st.text(info.get("description", "（説明文なし）"))
            return

        st.success(f"{source}から **{len(tracks)}曲** を検出しました")

        # Apple Music検索
        progress = st.progress(0, text="Apple Musicを検索中...")
        results = []

        for i, track in enumerate(tracks):
            progress.progress(
                (i + 1) / len(tracks),
                text=f"検索中... ({i + 1}/{len(tracks)}) {track.get('title', '')}",
            )
            apple = search_apple_music(track.get("title", ""))
            results.append(
                {
                    "timestamp": track.get("timestamp", ""),
                    "original_title": track.get("title", ""),
                    "apple": apple,
                }
            )
            if i < len(tracks) - 1:
                time.sleep(0.3)

        progress.empty()

        # 結果表示
        st.subheader("トラックリスト")
        for i, r in enumerate(results, 1):
            ts = r["timestamp"]
            title = r["original_title"]
            apple = r["apple"]

            with st.container():
                cols = st.columns([0.5, 1, 3, 2])
                with cols[0]:
                    st.write(f"**{i:02d}**")
                with cols[1]:
                    if ts:
                        st.code(ts, language=None)
                with cols[2]:
                    if apple:
                        st.write(f"**{apple['track_name']}**")
                        st.caption(f"{apple['artist_name']} / {apple['album']}")
                    else:
                        st.write(f"**{title}**")
                        st.caption("Apple Musicで見つかりませんでした")
                with cols[3]:
                    if apple and apple.get("apple_music_url"):
                        st.link_button(
                            "Apple Musicで開く",
                            apple["apple_music_url"],
                            use_container_width=True,
                        )

        # JSON出力
        with st.expander("JSONデータをダウンロード"):
            export_data = {
                "video_title": info.get("title", ""),
                "channel": info.get("channel", ""),
                "url": url,
                "tracks": [
                    {
                        "number": i + 1,
                        "timestamp": r["timestamp"],
                        "original_title": r["original_title"],
                        "apple_music_track": r["apple"]["track_name"]
                        if r["apple"]
                        else None,
                        "apple_music_artist": r["apple"]["artist_name"]
                        if r["apple"]
                        else None,
                        "apple_music_url": r["apple"]["apple_music_url"]
                        if r["apple"]
                        else None,
                    }
                    for i, r in enumerate(results)
                ],
            }
            st.json(export_data)
            st.download_button(
                "JSONをダウンロード",
                data=json.dumps(export_data, ensure_ascii=False, indent=2),
                file_name="dj_tracklist.json",
                mime="application/json",
            )


if __name__ == "__main__":
    show_dj_tracker_page()
