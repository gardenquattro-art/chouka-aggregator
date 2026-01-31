#!/usr/bin/env python3
"""
日振島 釣果アグリゲーター - スクレイパー
渡船屋から釣果情報（日付・画像・テキスト）を収集する
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def fetch(url, verify=True):
    """ページ取得"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=verify)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text
    except requests.exceptions.SSLError:
        if url.startswith("https://"):
            return fetch(url.replace("https://", "http://"), verify=False)
        raise


def normalize_date(text):
    """様々な日付形式を YYYY-MM-DD に正規化"""
    if not text:
        return None
    # YYYY/MM/DD or YYYY-MM-DD
    m = re.search(r'(20\d{2})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # '26年1月27日（全角対応）
    t = text.translate(str.maketrans('０１２３４５６７８９＇', "0123456789'"))
    m = re.search(r"'?(\d{2})年(\d{1,2})月(\d{1,2})日", t)
    if m:
        return f"20{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    # 2026年1月27日
    m = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', t)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return None


# ─────────────────────────────────────────────
# 1. よしだ屋 (yoshida-tosen.jp)
# ─────────────────────────────────────────────
def scrape_yoshida():
    results = []
    base = "https://yoshida-tosen.jp"
    html = fetch(f"{base}/blog_surffishing/")
    soup = BeautifulSoup(html, "html.parser")

    article_links = []
    for a in soup.find_all("a", href=re.compile(r"/blog_surffishing/\d{8}-\d+")):
        href = urljoin(base, a.get("href", ""))
        if href not in article_links:
            article_links.append(href)

    for url in article_links[:15]:
        try:
            art_soup = BeautifulSoup(fetch(url), "html.parser")

            # 日付（URLから）
            dm = re.search(r'/(\d{8})-', url)
            if not dm:
                continue
            d = dm.group(1)
            date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

            # タイトル
            h = art_soup.find("h3") or art_soup.find("h2")
            title = h.get_text(strip=True) if h else ""
            # 駐車場情報等は除外
            if "駐車場" in title:
                continue

            # 画像
            images = []
            for img in art_soup.find_all("img"):
                src = img.get("src", "")
                if "/article/" in src and "logo" not in src:
                    full = urljoin(base, src)
                    # サムネイルをフルサイズに
                    full = re.sub(r'/\d+_\d+_\d+_\w+/$', '/1000_700_2_ffffff/', full)
                    if full not in images:
                        images.append(full)

            # 本文
            body = "\n".join(
                p.get_text(strip=True)
                for p in art_soup.find_all("p")
                if p.get_text(strip=True) and len(p.get_text(strip=True)) > 5
            )[:400]

            results.append({
                "source": "よしだ屋",
                "date": date_str,
                "title": title,
                "images": images,
                "body": body,
                "url": url,
            })
        except Exception as e:
            print(f"  [WARN] よしだ屋: {e}")
    return results


# ─────────────────────────────────────────────
# 2. 三浦渡船 (Blogger)
# ─────────────────────────────────────────────
def scrape_miura():
    results = []
    url = "https://miura-tosen-chouka.blogspot.com/"
    soup = BeautifulSoup(fetch(url), "html.parser")

    # 日付ヘッダーごとにグループ化
    current_date = None
    for el in soup.find_all(["h2", "div"]):
        cls = " ".join(el.get("class", []))

        if "date-header" in cls:
            current_date = normalize_date(el.get_text())
            continue

        if "post" in cls and "post-outer" not in cls and "post-body" not in cls:
            title_tag = el.find(["h3", "h4"])
            title = title_tag.get_text(strip=True) if title_tag else ""

            # 日付（ヘッダー or タイトルから）
            date_str = current_date or normalize_date(title)
            if not date_str:
                continue

            # 画像（BloggerのUIアイコンを除外）
            images = []
            for img in el.find_all("img"):
                src = img.get("src", "")
                if src and len(src) > 30 and "icon18_edit" not in src and "blogblog.com" not in src:
                    src = re.sub(r'/s\d+/', '/s800/', src)
                    if src not in images:
                        images.append(src)

            # 本文
            body_el = el.find("div", class_="post-body")
            body = body_el.get_text(strip=True)[:300] if body_el else ""

            # URL
            a = el.find("a", class_="timestamp-link")
            if not a and title_tag:
                a = title_tag.find("a")
            post_url = a.get("href", url) if a else url

            # タイトルも本文も画像もない記事は除外
            if not title and not body and not images:
                continue
            # タイトルがない場合、本文の先頭を使用
            if not title and body:
                title = body[:50]

            results.append({
                "source": "三浦渡船",
                "date": date_str,
                "title": title,
                "images": images,
                "body": body,
                "url": post_url,
            })

    return results[:15]


# ─────────────────────────────────────────────
# 3. わかしお渡船 (Ameba Blog - RSS)
# ─────────────────────────────────────────────
def scrape_wakashio():
    return _scrape_ameblo_rss("wakashio5011", "わかしお渡船")


def _scrape_ameblo_rss(blog_id, source_name):
    """Ameba Blog RSSからデータ取得"""
    results = []
    rss_url = f"https://rssblog.ameba.jp/{blog_id}/rss20.xml"
    xml = fetch(rss_url)
    soup = BeautifulSoup(xml, "xml")

    for item in soup.find_all("item"):
        title = item.find("title").text if item.find("title") else ""
        link = item.find("link").text if item.find("link") else ""
        pub = item.find("pubDate")
        desc = item.find("description").text if item.find("description") else ""

        # 日付
        date_str = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub.text)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = normalize_date(pub.text)

        # 画像（descriptionのHTMLから）
        images = re.findall(r'src=["\']([^"\']+user_images[^"\']+)["\']', desc)
        # Instagram/Facebook CDN画像も
        images += re.findall(r'src=["\']([^"\']+(?:cdninstagram|fbcdn)[^"\']+)["\']', desc)
        # SVGアイコンを除外
        images = [img for img in images if not img.endswith('.svg')]

        # 本文（HTMLタグ除去）
        body = BeautifulSoup(desc, "html.parser").get_text(strip=True)[:300]

        if date_str:
            results.append({
                "source": source_name,
                "date": date_str,
                "title": title,
                "images": images,
                "body": body,
                "url": link,
            })

    return results


# ─────────────────────────────────────────────
# 4. 清家渡船 (さくらブログ)
# ─────────────────────────────────────────────
def scrape_seike():
    results = []
    url = "http://newchouka.sblo.jp/"
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  [WARN] 清家渡船 取得失敗: {e}")
        return results

    soup = BeautifulSoup(html, "html.parser")

    for blog_div in soup.find_all("div", class_="blog"):
        # 日付はblogbody内のh2やテキストから
        text = blog_div.get_text(strip=True)
        date_str = normalize_date(text)
        if not date_str:
            continue

        # タイトル（記事のテキスト概要）
        text_div = blog_div.find("div", class_="text")
        title = text_div.get_text(strip=True)[:80] if text_div else text[:80]
        if not title or title == date_str.replace("-", ""):
            continue

        # 画像（aタグのhrefからフルサイズ画像を取得、HTTPSに統一）
        images = []
        for a_tag in blog_div.find_all("a"):
            href = a_tag.get("href", "")
            if "sblo_files" in href and any(href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                full = href.replace("http://", "https://")
                if full not in images:
                    images.append(full)
        # aタグに画像がない場合、imgのサムネイルをHTTPS化して使用
        if not images:
            for img in blog_div.find_all("img"):
                src = img.get("src", "")
                if "sblo_files" in src or "newchouka" in src:
                    full = src.replace("http://", "https://")
                    if full not in images:
                        images.append(full)

        # 記事URL
        a = blog_div.find("a")
        post_url = a.get("href", url) if a else url

        results.append({
            "source": "清家渡船",
            "date": date_str,
            "title": title,
            "images": images,
            "body": title,
            "url": post_url,
        })

    return results[:20]


# ─────────────────────────────────────────────
# 5. はまかぜ渡船 (Instagram via imginn.com)
# ─────────────────────────────────────────────
def scrape_hamakaze():
    """はまかぜ渡船の釣果情報をInstagram経由で取得（画像はローカル保存）"""
    results = []
    url = "https://imginn.com/hamakaze_tosen/"
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  [WARN] はまかぜ渡船 取得失敗: {e}")
        return results

    soup = BeautifulSoup(html, "html.parser")
    img_dir = os.path.join(os.path.dirname(DATA_DIR), "docs", "img", "hamakaze")
    os.makedirs(img_dir, exist_ok=True)

    for a_tag in soup.find_all("a", href=re.compile(r"/p/")):
        img = a_tag.find("img")
        if not img:
            continue

        src = img.get("src", "")
        alt = img.get("alt", "")
        post_url = "https://www.instagram.com" + a_tag.get("href", "")

        if "profile" in alt.lower() or "avatar" in alt.lower():
            continue

        caption = alt[:200] if alt else ""

        # 日付抽出
        date_str = None
        m = re.search(r'(\d{1,2})月(\d{1,2})日', caption)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            now = datetime.now()
            year = now.year
            if month > now.month + 1:
                year -= 1
            date_str = f"{year}-{month:02d}-{day:02d}"

        if not date_str:
            continue

        title = caption.split('\n')[0][:60] if caption else ""

        # 画像をローカルにダウンロード（CORS回避）
        local_images = []
        if src:
            fname = f"{date_str}.jpg"
            fpath = os.path.join(img_dir, fname)
            if not os.path.exists(fpath):
                try:
                    img_resp = requests.get(src, headers={
                        **HEADERS, "Referer": "https://imginn.com/"
                    }, timeout=10)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        with open(fpath, "wb") as f:
                            f.write(img_resp.content)
                        local_images.append(f"img/hamakaze/{fname}")
                except Exception as e:
                    print(f"    [WARN] 画像DL失敗: {e}")
            else:
                local_images.append(f"img/hamakaze/{fname}")

        results.append({
            "source": "はまかぜ渡船",
            "date": date_str,
            "title": title,
            "images": local_images,
            "body": caption,
            "url": post_url,
        })

    return results


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
SCRAPERS = [
    ("よしだ屋", scrape_yoshida),
    ("三浦渡船", scrape_miura),
    ("わかしお渡船", scrape_wakashio),
    ("清家渡船", scrape_seike),
    ("はまかぜ渡船", scrape_hamakaze),
]


def main():
    print("=" * 60)
    print("  日振島 釣果アグリゲーター - データ収集")
    print(f"  実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    all_results = []

    for name, fn in SCRAPERS:
        print(f"\n[{name}] 取得中...")
        try:
            items = fn()
            all_results.extend(items)
            print(f"  -> {len(items)} 件取得")
            for item in items[:3]:
                print(f"     {item['date']} | 画像{len(item['images'])}枚 | {item['title'][:40]}")
        except Exception as e:
            print(f"  -> エラー: {e}")

    # 日付ソート（新しい順）
    all_results.sort(key=lambda x: x["date"], reverse=True)

    # 重複除去（同じ渡船・同じ日付・同じタイトル）
    seen = set()
    unique = []
    for r in all_results:
        key = (r["source"], r["date"], r["title"][:30])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    all_results = unique

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    output_path = os.path.join(DATA_DIR, "chouka.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # 更新時刻も保存
    meta = {
        "updated_at": datetime.now().isoformat(),
        "total": len(all_results),
        "sources": {name: len([r for r in all_results if r["source"] == name]) for name, _ in SCRAPERS},
    }
    with open(os.path.join(DATA_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  合計: {len(all_results)} 件（重複除去後）")
    print(f"  保存先: {output_path}")
    for name, count in meta["sources"].items():
        print(f"    {name}: {count}件")
    print("=" * 60)


if __name__ == "__main__":
    main()
