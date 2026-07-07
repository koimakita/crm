"""
Apple Music Playlist Creator
DJ Track Extractorが出力したtxtファイルから、Apple Musicにプレイリストを一括作成する

使い方:
  python3 apple_music_playlist.py トラックリスト.txt --name "プレイリスト名"

初回だけ Media User Token の設定が必要です（トークンは ~/.dj_cat_config.json に保存されます）:
  1. Safari または Chrome で https://music.apple.com を開いてログインする
  2. 開発者ツールを開く
     - Chrome: 右クリック →「検証」→ 上部タブの「ネットワーク（Network）」
     - Safari: 環境設定 → 詳細 →「メニューバーに開発メニューを表示」にチェック
       → 開発メニュー →「Webインスペクタを表示」→「ネットワーク」タブ
  3. ページを再読み込みして、一覧のリクエストをどれかクリック
     （amp-api.music.apple.com へのリクエストが確実）
  4. 「リクエストヘッダー（Request Headers）」の中の
     media-user-token: の右側の長い文字列をコピー
  5. このスクリプトを実行すると初回に入力を求められるので、貼り付ける
"""

import argparse
import json
import os
import re
import sys

import requests

CONFIG_PATH = os.path.expanduser("~/.dj_cat_config.json")
AMP_API = "https://amp-api.music.apple.com"


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_media_user_token(reset: bool = False) -> str:
    cfg = load_config()
    if not reset and cfg.get("media_user_token"):
        return cfg["media_user_token"]
    print("=" * 60)
    print("Media User Token が必要です（初回のみ）")
    print("取得方法はこのファイル冒頭のコメントを参照してください。")
    print("=" * 60)
    token = input("media-user-token を貼り付けてください: ").strip()
    if not token:
        print("トークンが入力されませんでした。")
        sys.exit(1)
    cfg["media_user_token"] = token
    save_config(cfg)
    print(f"保存しました: {CONFIG_PATH}\n")
    return token


def fetch_developer_token() -> str:
    """music.apple.com のWebプレイヤーが使う公開Bearerトークンを取得する"""
    try:
        top = requests.get("https://music.apple.com", timeout=15)
        top.raise_for_status()
        # index-*.js のパスを探す
        js_match = re.search(r'/assets/index[-.~][\w.-]*\.js', top.text)
        if not js_match:
            raise RuntimeError("Webプレイヤーのスクリプトが見つかりません")
        js_url = "https://music.apple.com" + js_match.group(0)
        js = requests.get(js_url, timeout=15)
        js.raise_for_status()
        # JWT形式のトークン（eyJ...で始まる）を探す
        token_match = re.search(r'"(eyJh[\w-]+\.[\w-]+\.[\w-]+)"', js.text)
        if not token_match:
            raise RuntimeError("Bearerトークンが見つかりません")
        return token_match.group(1)
    except Exception as e:
        print(f"開発者トークンの取得に失敗しました: {e}")
        sys.exit(1)


def parse_tracklist(path: str) -> tuple[list[dict], list[str]]:
    """txtファイルから曲ID・曲名を抜き出す。IDが無い曲はスキップリストへ"""
    with open(path, encoding="utf-8") as f:
        text = f.read()

    tracks = []
    skipped = []
    current_title = None

    for line in text.split("\n"):
        line = line.strip()
        # "01. [0:30] Artist - Title" 形式の行
        m = re.match(r"^\d{2,}\.\s*(?:\[[\d:]+\]\s*)?(.+)$", line)
        if m:
            current_title = m.group(1).strip()
            continue
        # Apple Music URL の行から曲IDを抜き出す
        url_m = re.search(r"music\.apple\.com/\S*[?&]i=(\d+)", line)
        if url_m and current_title:
            tracks.append({"id": url_m.group(1), "title": current_title})
            current_title = None
        elif "見つかりませんでした" in line and current_title:
            skipped.append(current_title)
            current_title = None

    return tracks, skipped


def create_playlist(name: str, description: str, track_ids: list[str],
                    dev_token: str, user_token: str) -> bool:
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Media-User-Token": user_token,
        "Origin": "https://music.apple.com",
        "Content-Type": "application/json",
    }
    body = {
        "attributes": {"name": name, "description": description},
        "relationships": {
            "tracks": {"data": [{"id": tid, "type": "songs"} for tid in track_ids]}
        },
    }
    resp = requests.post(
        f"{AMP_API}/v1/me/library/playlists",
        headers=headers, json=body, timeout=30,
    )
    if resp.status_code in (200, 201):
        return True
    if resp.status_code == 401:
        print("認証エラー（401）: Media User Token の期限切れの可能性があります。")
        print("  --reset-token を付けて再実行し、新しいトークンを設定してください。")
    else:
        print(f"エラー ({resp.status_code}): {resp.text[:300]}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="トラックリストtxtからApple Musicプレイリストを一括作成する"
    )
    parser.add_argument("txt_file", help="DJ Track Extractorが出力したtxtファイル")
    parser.add_argument("--name", "-n", required=True, help="プレイリスト名")
    parser.add_argument("--description", "-d", default="", help="プレイリストの説明")
    parser.add_argument("--reset-token", action="store_true",
                        help="保存済みのMedia User Tokenを設定し直す")
    args = parser.parse_args()

    if not os.path.exists(args.txt_file):
        print(f"ファイルが見つかりません: {args.txt_file}")
        sys.exit(1)

    tracks, skipped = parse_tracklist(args.txt_file)
    if not tracks:
        print("Apple MusicのURLが1件も見つかりませんでした。")
        sys.exit(1)

    print(f"追加する曲: {len(tracks)}曲")
    for i, t in enumerate(tracks, 1):
        print(f"  {i:02d}. {t['title']}")
    if skipped:
        print(f"\nApple Musicに無いためスキップ: {len(skipped)}曲")
        for s in skipped:
            print(f"  - {s}")

    user_token = get_media_user_token(reset=args.reset_token)
    print("\n開発者トークンを取得中...")
    dev_token = fetch_developer_token()

    desc = args.description or "DJ CAT TRACKER で作成"
    print(f"プレイリスト「{args.name}」を作成中...")
    ok = create_playlist(args.name, desc, [t["id"] for t in tracks],
                         dev_token, user_token)
    if ok:
        print(f"\n✅ 完了！ Apple Musicのライブラリに「{args.name}」（{len(tracks)}曲）を作成しました。")
        print("   ミュージックアプリを開いて確認してください（反映に数秒かかることがあります）。")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
