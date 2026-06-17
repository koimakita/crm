"""
YouTube DJ Track Extractor
指定したYouTubeのDJ動画から曲リストを取得し、Apple Musicのリンクを表示する
"""

import yt_dlp
import requests
import re
import json
import argparse
import sys
import time
from urllib.parse import quote_plus


def get_youtube_video_info(url: str) -> dict:
    """yt-dlpを使ってYouTube動画の情報を取得する"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": False,
        "extract_flat": False,
        "skip_download": True,
        "no_playlist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "chapters": info.get("chapters", []),
        "channel": info.get("channel", ""),
        "upload_date": info.get("upload_date", ""),
        "duration": info.get("duration", 0),
    }


def extract_tracks_from_chapters(chapters: list) -> list[dict]:
    """チャプター情報からトラックリストを抽出する"""
    tracks = []
    for ch in chapters:
        title = ch.get("title", "").strip()
        if title:
            tracks.append(
                {
                    "title": title,
                    "timestamp": _seconds_to_timestamp(ch.get("start_time", 0)),
                }
            )
    return tracks


def extract_tracks_from_description(description: str) -> list[dict]:
    """動画説明文からトラックリストを抽出する"""
    tracks = []
    lines = description.split("\n")

    # タイムスタンプ付きパターン: 00:00 Artist - Track Name
    timestamp_pattern = re.compile(
        r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—:．]?\s*(.+)$"
    )

    # 番号付きパターン: 01. Artist - Track
    numbered_pattern = re.compile(r"^\d{1,2}[.)]\s+(.+)$")

    # "Music in this video" セクションの開始を検出
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

        # タイムスタンプパターンはセクション外でも有効
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


def _seconds_to_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def search_apple_music(track_query: str) -> dict | None:
    """iTunes Search APIでApple Musicのリンクを検索する"""
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
                "preview_url": result.get("previewUrl", ""),
            }
    except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
        print(f"  [警告] iTunes検索エラー ({track_query}): {e}", file=sys.stderr)

    return None


def process_video(url: str, delay: float = 0.5) -> dict:
    """YouTube動画からトラックリストを取得してApple Musicリンクを付ける"""
    print(f"動画情報を取得中: {url}")
    info = get_youtube_video_info(url)

    print(f"動画タイトル: {info['title']}")
    print(f"チャンネル: {info['channel']}")

    # チャプターからトラックを取得（優先）
    tracks = extract_tracks_from_chapters(info["chapters"])

    if tracks:
        print(f"\nチャプターから {len(tracks)} 曲を検出しました")
    else:
        # 説明文からトラックを取得
        tracks = extract_tracks_from_description(info["description"])
        if tracks:
            print(f"\n説明文から {len(tracks)} 曲を検出しました")
        else:
            print("\n曲情報が見つかりませんでした。説明文を確認してください:")
            print(info["description"][:500])
            return {"video_info": info, "tracks": []}

    # Apple Musicリンクを検索
    print("\nApple Musicリンクを検索中...")
    results = []
    for i, track in enumerate(tracks, 1):
        title = track.get("title", "")
        timestamp = track.get("timestamp", "")

        print(f"  [{i}/{len(tracks)}] {title}")
        apple_info = search_apple_music(title)

        results.append(
            {
                "timestamp": timestamp,
                "original_title": title,
                "apple_music": apple_info,
            }
        )

        if delay > 0 and i < len(tracks):
            time.sleep(delay)

    return {"video_info": info, "tracks": results}


def print_results(result: dict):
    """結果を見やすく表示する"""
    info = result["video_info"]
    tracks = result["tracks"]

    print("\n" + "=" * 60)
    print(f"動画: {info['title']}")
    print(f"チャンネル: {info['channel']}")
    print("=" * 60)

    if not tracks:
        print("トラックが見つかりませんでした。")
        return

    print(f"\n全{len(tracks)}曲\n")
    for i, track in enumerate(tracks, 1):
        ts = track.get("timestamp", "")
        original = track.get("original_title", "")
        apple = track.get("apple_music")

        ts_str = f"[{ts}] " if ts else ""
        print(f"{i:02d}. {ts_str}{original}")

        if apple:
            print(f"    アーティスト: {apple['artist_name']}")
            print(f"    曲名: {apple['track_name']}")
            print(f"    Apple Music: {apple['apple_music_url']}")
        else:
            print("    Apple Music: 見つかりませんでした")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="YouTube DJ動画からトラックリストを取得してApple Musicリンクを表示する"
    )
    parser.add_argument("url", help="YouTube動画のURL")
    parser.add_argument(
        "--json",
        action="store_true",
        help="結果をJSON形式で出力する",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Apple Music API呼び出し間の待機時間（秒）",
    )
    args = parser.parse_args()

    result = process_video(args.url, delay=args.delay)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_results(result)


if __name__ == "__main__":
    main()
