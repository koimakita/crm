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


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15")


def _validate_dev_token(token: str) -> bool:
    """カタログAPIを軽く叩いてトークンが有効か確認する"""
    try:
        resp = requests.get(
            f"{AMP_API}/v1/catalog/us/songs/1500952424",
            headers={"Authorization": f"Bearer {token}",
                     "Origin": "https://music.apple.com"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def set_developer_token_interactive() -> str:
    """開発者トークンを対話形式で設定する"""
    print("=" * 60)
    print("開発者トークン（Bearerトークン）の設定")
    print("=" * 60)
    print("1. Chromeで https://music.apple.com を開く（ログイン済みの状態）")
    print("2. 右クリック →「検証」→「ネットワーク」タブ")
    print("3. フィルター欄に amp-api と入力")
    print("4. ページを再読み込みするか、左メニューの「ライブラリ」をクリック")
    print("5. 一覧に出たリクエストをクリック →「リクエストヘッダー」の")
    print("   authorization: Bearer eyJ..... という行を探す")
    print("6. Bearer の後ろの eyJ から始まる長い文字列をコピーして貼り付け")
    print("   （Bearer ごとコピーしてしまってもOK）")
    print("=" * 60)
    token = input("authorization トークンを貼り付けてください: ").strip()
    # "Bearer " 付きや引用符付きで貼られても動くように掃除する
    token = token.strip('"\'')
    if token.lower().startswith("bearer"):
        token = token[6:].strip()
    if not token.startswith("eyJ"):
        print("eyJ から始まる文字列ではありません。コピーする場所を確認してください。")
        sys.exit(1)
    print("トークンを確認中...")
    if not _validate_dev_token(token):
        print("このトークンは無効でした。コピーし直して再実行してください。")
        sys.exit(1)
    cfg = load_config()
    cfg["developer_token"] = token
    save_config(cfg)
    print(f"保存しました: {CONFIG_PATH}\n")
    return token


def fetch_developer_token() -> str:
    """music.apple.com のWebプレイヤーが使う公開Bearerトークンを取得する"""
    # 手動設定があればそれを優先（config: developer_token）
    cfg = load_config()
    if cfg.get("developer_token"):
        if _validate_dev_token(cfg["developer_token"]):
            return cfg["developer_token"]
        print("保存済みの開発者トークンが無効になっていたため、再取得します...")

    jwt_pattern = re.compile(r"eyJh[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
    try:
        top = requests.get("https://music.apple.com", timeout=15,
                           headers={"User-Agent": _UA})
        top.raise_for_status()

        # まれにHTML自体にトークンが埋め込まれていることもある
        candidates = list(jwt_pattern.findall(top.text))

        # ページが参照している全JSファイルを順に探す（index系を優先）
        js_paths = re.findall(r'["\'](/assets/[^"\']+?\.js)["\']', top.text)
        js_paths += re.findall(r'["\'](https://music\.apple\.com/assets/[^"\']+?\.js)["\']', top.text)
        js_paths = sorted(set(js_paths), key=lambda p: ("index" not in p, p))

        for path in js_paths[:20]:
            url = path if path.startswith("http") else "https://music.apple.com" + path
            try:
                js = requests.get(url, timeout=15, headers={"User-Agent": _UA})
                if js.status_code != 200:
                    continue
                candidates += jwt_pattern.findall(js.text)
            except Exception:
                continue

        # 見つかった候補を実際に検証して、有効なものを使う
        for tok in dict.fromkeys(candidates):  # 順序を保って重複除去
            if _validate_dev_token(tok):
                cfg["developer_token"] = tok
                save_config(cfg)
                return tok

        raise RuntimeError("有効なBearerトークンが見つかりません")
    except Exception as e:
        print(f"自動取得に失敗しました（{e}）。手動で設定します。\n")
        return set_developer_token_interactive()


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
    parser.add_argument("--set-dev-token", action="store_true",
                        help="開発者トークン（Bearer）を手動で設定し直す")
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
    if args.set_dev_token:
        dev_token = set_developer_token_interactive()
    else:
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
