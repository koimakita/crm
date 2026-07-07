"""
YouTube DJ Track Extractor
YouTube DJ動画から曲リストを取得し、Apple Musicのリンクを表示する
説明文にトラックリストがない場合はShazam音声認識で自動識別する
"""

import yt_dlp
import requests
import re
import json
import argparse
import sys
import time
import asyncio
import os
import subprocess
import tempfile
from urllib.parse import quote_plus


def _clean_youtube_url(url: str) -> str:
    """プレイリスト・ラジオなどの余分なパラメータを除去して動画URLだけにする"""
    import re
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def get_youtube_video_info(url: str) -> dict:
    url = _clean_youtube_url(url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "no_playlist": True,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "chapters": info.get("chapters") or [],
        "channel": info.get("channel", ""),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail", ""),
    }


def _is_song_chapter(title: str) -> bool:
    """チャプタータイトルが曲名らしいかどうかを判定する"""
    # 末尾が時刻パターン (例: "18:00", "20:30") → イベントスケジュール
    if re.search(r'\d{1,2}:\d{2}\s*$', title):
        return False
    # 曜日・毎週などのキーワードを含む → イベント告知
    if re.search(r'(毎週|月曜|火曜|水曜|木曜|金曜|土曜|日曜|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)', title, re.IGNORECASE):
        return False
    return True


def extract_tracks_from_chapters(chapters: list) -> list:
    return [
        {
            "title": ch.get("title", "").strip(),
            "timestamp": _seconds_to_timestamp(ch.get("start_time", 0)),
        }
        for ch in chapters
        if ch.get("title", "").strip() and _is_song_chapter(ch.get("title", "").strip())
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
            tracks.append({
                "timestamp": ts_match.group(1),
                "title": ts_match.group(2).strip(),
            })
            in_music_section = True
            continue
        if in_music_section:
            num_match = numbered_pattern.match(line)
            if num_match:
                tracks.append({"title": num_match.group(1).strip()})
    return tracks


def _seconds_to_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def search_apple_music(track_query: str) -> dict | None:
    url = "https://itunes.apple.com/search"
    params = {"term": track_query, "entity": "song", "limit": 1, "media": "music"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            r = data["results"][0]
            return {
                "track_name": r.get("trackName", ""),
                "artist_name": r.get("artistName", ""),
                "album": r.get("collectionName", ""),
                "apple_music_url": r.get("trackViewUrl", ""),
                "genre": r.get("primaryGenreName", ""),
            }
    except Exception:
        pass
    return None


def _download_audio(video_url: str, out_dir: str, progress_hook=None) -> str | None:
    """yt-dlpで音声全体を一度だけダウンロードする（ストリーム切り出しの失敗対策）"""
    out_tmpl = os.path.join(out_dir, "audio.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_tmpl,
        "socket_timeout": 30,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([_clean_youtube_url(video_url)])
        for f in os.listdir(out_dir):
            if f.startswith("audio."):
                return os.path.join(out_dir, f)
    except Exception as e:
        print(f"音声ダウンロードエラー: {e}", file=sys.stderr)
    return None


def _get_audio_stream_url(video_url: str) -> str | None:
    """yt-dlpで音声ストリームの直接URLを取得する（一度だけ呼ぶ）"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "skip_download": True,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            # フォーマットリストから音声URLを取得
            if "url" in info:
                return info["url"]
            for fmt in reversed(info.get("formats", [])):
                if fmt.get("acodec") != "none" and fmt.get("url"):
                    return fmt["url"]
    except Exception as e:
        print(f"音声URL取得エラー: {e}", file=sys.stderr)
    return None


def _extract_segment_ffmpeg(stream_url: str, start_sec: int, duration: int, out_path: str) -> str | None:
    """ffmpegで音声ストリームから指定時間のセグメントを切り出す"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", stream_url,
        "-t", str(duration),
        "-ac", "1",
        "-ar", "44100",
        "-f", "mp3",
        out_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        # 空・極小ファイルは無音や失敗とみなす（10KB ≒ 数秒未満の音声）
        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
            return out_path
    except Exception as e:
        print(f"    ffmpegエラー: {e}", file=sys.stderr)
    return None


async def identify_tracks_shazam(url: str, duration: int, interval: int = 300) -> list:
    """Shazam音声認識でトラックを特定する"""
    try:
        from shazamio import Shazam
    except ImportError:
        print("\n[エラー] shazamioが必要です:")
        print("  pip install shazamio")
        return []

    shazam = Shazam()
    tracks = []
    seen: set[str] = set()

    # 最初の30秒と最後の30秒を除いてサンプリング
    sample_times = list(range(30, max(31, duration - 30), interval))
    seg_duration = 20  # 15秒より長めにして認識率を上げる

    print(f"\nShazam音声認識で解析します（{len(sample_times)}箇所 × {seg_duration}秒）")
    print("音声をダウンロード中...（一度だけ・数十MB程度）")

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_file = _download_audio(url, tmpdir)
        if not audio_file:
            print("音声のダウンロードに失敗しました。")
            return []
        print("ダウンロード完了。解析を開始します。\n")

        for i, start_sec in enumerate(sample_times):
            ts = _seconds_to_timestamp(start_sec)
            print(f"[{i+1}/{len(sample_times)}] {ts} を解析中...", end=" ", flush=True)

            seg_file = os.path.join(tmpdir, f"seg_{i}.mp3")
            seg_file = _extract_segment_ffmpeg(audio_file, start_sec, seg_duration, seg_file)

            if not seg_file:
                print("切り出し失敗")
                continue

            try:
                result = await shazam.recognize(seg_file)
            except Exception as e:
                print(f"認識エラー: {e}")
                continue

            if not result or "track" not in result:
                print("認識不可")
                continue

            track = result["track"]
            title = track.get("title", "")
            artist = track.get("subtitle", "")
            key = f"{title}|{artist}".lower()

            if not title or key in seen:
                print("既出 or 不明")
                continue

            seen.add(key)

            # iTunes APIで music.apple.com のページリンクを取得
            apple = search_apple_music(f"{artist} {title}")
            apple_url = apple["apple_music_url"] if apple else ""

            tracks.append({
                "timestamp": ts,
                "title": title,
                "artist": artist,
                "apple_music_url": apple_url,
            })
            print(f"✓ {artist} - {title}")
            await asyncio.sleep(0.5)

    return tracks


def process_video(url: str, use_shazam: bool = True, interval: int = 300) -> dict:
    print(f"動画情報を取得中: {url}")
    info = get_youtube_video_info(url)
    print(f"動画タイトル: {info['title']}")
    print(f"チャンネル: {info['channel']}")

    # 1. チャプターから取得（最速）
    raw_tracks = extract_tracks_from_chapters(info["chapters"])
    method = "チャプター"

    # 2. 説明文から取得
    if not raw_tracks:
        raw_tracks = extract_tracks_from_description(info["description"])
        method = "説明文"

    if raw_tracks:
        print(f"\n{method}から {len(raw_tracks)} 曲を検出しました")
        print("Apple Musicリンクを検索中...")
        results = []
        for i, t in enumerate(raw_tracks, 1):
            title = t.get("title", "")
            print(f"  [{i}/{len(raw_tracks)}] {title}")
            apple = search_apple_music(title)
            results.append({
                "timestamp": t.get("timestamp", ""),
                "original_title": title,
                "apple": apple,
            })
            time.sleep(0.3)
        return {"video_info": info, "tracks": results, "method": method}

    # 3. Shazam音声認識
    print("\n説明文にトラックリストが見つかりませんでした。")
    if not use_shazam:
        return {"video_info": info, "tracks": [], "method": "none"}

    shazam_tracks = asyncio.run(
        identify_tracks_shazam(url, info["duration"], interval=interval)
    )
    results = [
        {
            "timestamp": t["timestamp"],
            "original_title": f"{t['artist']} - {t['title']}",
            "apple": {
                "track_name": t["title"],
                "artist_name": t["artist"],
                "album": "",
                "apple_music_url": t["apple_music_url"],
            },
        }
        for t in shazam_tracks
    ]
    return {"video_info": info, "tracks": results, "method": "Shazam"}


def format_results(result: dict) -> str:
    info = result["video_info"]
    tracks = result["tracks"]
    method = result.get("method", "")

    lines = []
    lines.append("=" * 60)
    lines.append(f"動画: {info['title']}")
    lines.append(f"チャンネル: {info['channel']}")
    if method:
        lines.append(f"取得方法: {method}")
    lines.append("=" * 60)

    if not tracks:
        lines.append("\nトラックが見つかりませんでした。")
        return "\n".join(lines)

    lines.append(f"\n全{len(tracks)}曲\n")
    for i, track in enumerate(tracks, 1):
        ts = track.get("timestamp", "")
        apple = track.get("apple")
        ts_str = f"[{ts}] " if ts else ""

        if apple and apple.get("artist_name") and apple.get("track_name"):
            lines.append(f"{i:02d}. {ts_str}{apple['artist_name']} - {apple['track_name']}")
        else:
            lines.append(f"{i:02d}. {ts_str}{track.get('original_title', '')}")

        if apple:
            if apple.get("genre"):
                lines.append(f"    ジャンル: {apple['genre']}")
            if apple.get("apple_music_url"):
                lines.append(f"    Apple Music: {apple['apple_music_url']}")
        else:
            lines.append("    Apple Music: 見つかりませんでした")
        lines.append("")

    return "\n".join(lines)


def save_txt(result: dict, filepath: str):
    text = format_results(result)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nテキストファイルに保存しました: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube DJ動画からトラックリストを取得してApple Musicリンクを表示する"
    )
    parser.add_argument("url", help="YouTube動画のURL")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--no-shazam", action="store_true", help="Shazam音声認識を使わない")
    parser.add_argument(
        "--interval", type=int, default=300,
        help="サンプリング間隔（秒）デフォルト: 300（5分おき）"
    )
    parser.add_argument("--output", "-o", help="保存先のテキストファイル名（例: tracklist.txt）")
    args = parser.parse_args()

    result = process_video(args.url, use_shazam=not args.no_shazam, interval=args.interval)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        text = format_results(result)
        print("\n" + text)

        # --output 指定があればそのファイル名、なければ自動生成
        if args.output:
            filepath = args.output
        else:
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", result["video_info"]["title"])[:50]
            filepath = f"{safe_title}.txt"

        save_txt(result, filepath)


if __name__ == "__main__":
    main()
