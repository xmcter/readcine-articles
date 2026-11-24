#!/usr/bin/env python3
"""ReadCine 观影导览文章存档：content/<slug>/article.md -> site/ 静态页。

article.md 头部是 front matter（--- 包裹的 key: value），正文是 Markdown。
必填：title, date(YYYY-MM-DD)。可选：summary, cover(相对 img/ 路径), original(公众号原文链接)。
"""
import html, json, re, shutil, sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"
BASE = "https://blog.readcine.com"
SITE_NAME = "观影导览"
ICP = "湘ICP备2026041550号-1"
ASSET_VER = "20261124"

# 不允许进入仓库 / 网页的内容：网盘、下载、磁力、密钥样式
FORBIDDEN = [
    r"pan\.quark\.cn", r"quark\.cn/s/", r"夸克网盘", r"magnet:\?", r"ed2k://", r"thunder://",
    r"pan\.baidu\.com", r"aliyundrive\.com", r"alipan\.com", r"115\.com/s/", r"123pan\.com",
    r"sk-[A-Za-z0-9]{20,}", r"gh[pousr]_[A-Za-z0-9]{30,}", r"AKIA[0-9A-Z]{16}", r"LTAI[0-9A-Za-z]{12,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]


def die(msg):
    print(f"[build] 错误：{msg}", file=sys.stderr)
    sys.exit(1)


def parse(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        die(f"{path} 缺少 front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    body = text[m.end():]
    for k in ("title", "date"):
        if not meta.get(k):
            die(f"{path} front matter 缺 {k}")
    date.fromisoformat(meta["date"])
    return meta, body


def scan(text, where):
    for pat in FORBIDDEN:
        if re.search(pat, text, re.I):
            die(f"{where} 含禁止内容（匹配 {pat}），已中止")


def page(title, desc, canonical, body, og_image=None, og_type="website"):
    e = html.escape
    og = f'<meta property="og:image" content="{e(og_image)}">\n' if og_image else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
{og}<meta name="theme-color" content="#f5f5f7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/assets/icon.png">
<link rel="apple-touch-icon" href="/assets/icon.png">
<link rel="stylesheet" href="/assets/style.css?v={ASSET_VER}">
</head>
<body>
<header class="top"><div class="top__in">
<a class="brand" href="/">{SITE_NAME}</a>
<a class="pill" href="https://readcine.com/">ReadCine</a>
</div></header>
{body}
<footer class="foot">© {date.today().year} ReadCine · <a href="https://beian.miit.gov.cn/" rel="noopener" target="_blank">{ICP}</a></footer>
</body>
</html>
"""


def cn_date(d):
    y, m, dd = d.split("-")
    return f"{int(y)}年{int(m)}月{int(dd)}日"


def strip_md(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[#>*_`|]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def auto_summary(body):
    for para in re.split(r"\n\s*\n", body):
        t = strip_md(para)
        if len(t) >= 30 and not para.lstrip().startswith(("#", "!", "|")):
            return t[:110] + ("…" if len(t) > 110 else "")
    return ""


def build():
    arts = []
    for d in sorted(p for p in CONTENT.iterdir() if p.is_dir()):
        md = d / "article.md"
        if not md.exists():
            continue
        meta, body = parse(md)
        scan(md.read_text(encoding="utf-8"), md)
        slug = d.name
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            die(f"slug 只能小写字母数字和连字符：{slug}")
        # 正文图必须都在 img/ 里
        for ref in re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body) + re.findall(r'<img[^>]+src="([^"]+)"', body):
            if ref.startswith(("http://", "https://")):
                die(f"{slug} 正文引用了外链图片 {ref}，请下载到 img/")
            if not (d / ref).exists():
                die(f"{slug} 引用的图片不存在：{ref}")
        h = markdown.markdown(body, extensions=["extra", "sane_lists"], output_format="html5")
        h = h.replace("<img ", '<img loading="lazy" decoding="async" ')
        meta["summary"] = meta.get("summary") or auto_summary(body)
        arts.append((meta, slug, h, d))

    arts.sort(key=lambda a: (a[0]["date"], a[1]), reverse=True)
    # 输出
    keep = {"assets", "index.html", "sitemap.xml", "robots.txt", "404.html"}
    for slug_dir in SITE.iterdir():
        if slug_dir.is_dir() and slug_dir.name not in keep and slug_dir.name not in {a[1] for a in arts}:
            print(f"[build] 提示：site/{slug_dir.name} 已无对应 content，未删除（需要下线请手动处理）")
    e = html.escape
    for meta, slug, h, d in arts:
        out = SITE / slug
        out.mkdir(parents=True, exist_ok=True)
        if (d / "img").is_dir():
            shutil.copytree(d / "img", out / "img", dirs_exist_ok=True)
        url = f"{BASE}/{slug}/"
        og = f"{url}{meta['cover']}" if meta.get("cover") else None
        orig = f' · <a href="{e(meta["original"])}" rel="noopener" target="_blank">公众号原文</a>' if meta.get("original") else ""
        body = f"""<main class="article">
<h1 class="title">{e(meta['title'])}</h1>
<div class="meta">{cn_date(meta['date'])} · {SITE_NAME}{orig}</div>
<article class="prose">
{h}
</article>
<div class="back"><a class="pill" href="/">← 全部文章</a></div>
</main>"""
        (out / "index.html").write_text(page(f"{meta['title']} · {SITE_NAME}", meta["summary"], url, body, og, "article"), encoding="utf-8")

    cards = []
    for meta, slug, _, _ in arts:
        img = f'<img class="card__img" src="/{slug}/{e(meta["cover"])}" alt="" loading="lazy">' if meta.get("cover") else ""
        cards.append(f"""<a class="card" href="/{slug}/">{img}<div class="card__body">
<h2 class="card__title">{e(meta['title'])}</h2>
<p class="card__sum">{e(meta['summary'])}</p>
<div class="meta">{cn_date(meta['date'])}</div></div></a>""")
    body = f"""<main class="wrap">
<section class="hero"><h1>{SITE_NAME}</h1></section>
<div class="grid">
{chr(10).join(cards)}
</div>
</main>"""
    first_cover = next((f"{BASE}/{a[1]}/{a[0]['cover']}" for a in arts if a[0].get("cover")), None)
    (SITE / "index.html").write_text(page(f"{SITE_NAME} · ReadCine", "观影导览公众号文章存档", BASE + "/", body, first_cover), encoding="utf-8")
    (SITE / "404.html").write_text(page(f"页面不存在 · {SITE_NAME}", "", BASE + "/", '<main class="wrap"><section class="hero"><h1>页面不存在</h1></section><a class="pill" href="/">← 全部文章</a></main>'), encoding="utf-8")
    urls = [f"  <url><loc>{BASE}/</loc></url>"] + [f"  <url><loc>{BASE}/{s}/</loc><lastmod>{m['date']}</lastmod></url>" for m, s, _, _ in arts]
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    for f in SITE.rglob("*.html"):
        scan(f.read_text(encoding="utf-8"), f)
    (ROOT / "articles.json").write_text(json.dumps([{"slug": s, "title": m["title"], "date": m["date"], "url": f"{BASE}/{s}/"} for m, s, _, _ in arts], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[build] 完成：{len(arts)} 篇 -> {SITE}")
    for m, s, _, _ in arts:
        print(f"  {BASE}/{s}/  {m['title']}")


if __name__ == "__main__":
    build()
