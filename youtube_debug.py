"""
デバッグ用：yt-dlpで取得できる全情報を確認する
"""
import yt_dlp
import json
import sys

url = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/bgT4l8efAhM"

ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "no_playlist": True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)

print("=== 全フィールド一覧 ===")
for k, v in info.items():
    if v is None or v == [] or v == {}:
        continue
    if isinstance(v, (str, int, float, bool)):
        print(f"{k}: {str(v)[:100]}")
    else:
        print(f"{k}: [{type(v).__name__}]")

print("\n=== 説明文（全文） ===")
print(info.get("description", ""))

print("\n=== chapters ===")
print(json.dumps(info.get("chapters"), ensure_ascii=False, indent=2))

# music関連フィールドを探す
print("\n=== 'music'を含むフィールド ===")
def find_music_fields(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if "music" in k.lower() or "song" in k.lower() or "track" in k.lower():
                print(f"{new_path}: {str(v)[:200]}")
            find_music_fields(v, new_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            find_music_fields(v, f"{path}[{i}]")

find_music_fields(info)
