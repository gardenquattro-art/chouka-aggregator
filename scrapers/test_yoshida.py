#!/usr/bin/env python3
"""よしだ屋 スクレイピング検証スクリプト"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

BASE_URL = "https://yoshida-tosen.jp"
TARGET_URL = f"{BASE_URL}/blog_surffishing/"

def fetch_page(url):
    """ページを取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_articles(html):
    """記事一覧をパース"""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    # 記事要素を探索（複数パターンを試す）
    # パターン1: article タグ
    items = soup.find_all("article")
    if not items:
        # パターン2: li タグ内の記事
        items = soup.find_all("li")
    if not items:
        # パターン3: div with class containing 'post' or 'entry' or 'article'
        items = soup.find_all("div", class_=re.compile(r"(post|entry|article|blog)", re.I))

    print(f"[DEBUG] 検出要素数: {len(items)}")

    # まずページ全体の構造をダンプ
    print("\n[DEBUG] ページ内の主要タグ構造:")
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
        print(f"  {tag.name}: {tag.get_text(strip=True)[:80]}")

    print("\n[DEBUG] 画像タグ:")
    for img in soup.find_all("img")[:10]:
        src = img.get("src") or img.get("data-src") or ""
        alt = img.get("alt", "")
        print(f"  src={src[:100]}  alt={alt[:50]}")

    print("\n[DEBUG] リンク（blog_surffishing含む）:")
    for a in soup.find_all("a", href=re.compile(r"blog_surffishing")):
        href = a.get("href", "")
        text = a.get_text(strip=True)[:80]
        print(f"  href={href}  text={text}")

    # 日付パターンを探す
    print("\n[DEBUG] 日付パターン検出:")
    date_patterns = re.findall(r"20\d{2}[/\-\.]\d{1,2}[/\-\.]\d{1,2}", soup.get_text())
    for d in date_patterns[:10]:
        print(f"  {d}")

    # 記事ごとのデータ抽出を試みる
    for item in items[:5]:  # 最初の5件
        text = item.get_text(strip=True)
        if len(text) < 20:
            continue

        # 日付抽出
        date_match = re.search(r"(\d{2,4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", text)
        date_str = ""
        if date_match:
            y, m, d = date_match.groups()
            if len(y) == 2:
                y = "20" + y
            date_str = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

        # 画像URL抽出
        images = []
        for img in item.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and "logo" not in src.lower() and "icon" not in src.lower():
                if not src.startswith("http"):
                    src = BASE_URL + src
                images.append(src)

        # タイトル
        title_tag = item.find(["h2", "h3", "h4", "h5"])
        title = title_tag.get_text(strip=True) if title_tag else text[:60]

        if date_str or images:
            articles.append({
                "date": date_str,
                "title": title,
                "images": images,
                "text_preview": text[:200]
            })

    return articles

def main():
    print("=" * 60)
    print("よしだ屋 スクレイピング検証")
    print("=" * 60)

    print(f"\n[1] ページ取得: {TARGET_URL}")
    html = fetch_page(TARGET_URL)
    print(f"    取得成功: {len(html)} bytes")

    print(f"\n[2] 記事パース中...")
    articles = parse_articles(html)

    print(f"\n[3] 抽出結果: {len(articles)} 件")
    print("=" * 60)
    for i, art in enumerate(articles):
        print(f"\n--- 記事 {i+1} ---")
        print(f"  日付: {art['date']}")
        print(f"  タイトル: {art['title']}")
        print(f"  画像数: {len(art['images'])}")
        for img in art['images'][:3]:
            print(f"    {img}")
        print(f"  テキスト: {art['text_preview'][:100]}...")

    # JSON出力
    output_path = "/Users/keisukeharada/Downloads/chouka-aggregator/data/test_yoshida.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n[4] JSON保存: {output_path}")

if __name__ == "__main__":
    main()
