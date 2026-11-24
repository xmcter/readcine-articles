#!/usr/bin/env python3
"""ReadCine 观影导览文章存档：content/<slug>/article.md -> site/ 静态页。

article.md 头部是 front matter（--- 包裹的 key: value），正文是 Markdown。
必填：title, date(YYYY-MM-DD)。可选：summary, cover(相对 img/ 路径), original(公众号原文链接),
updated(YYYY-MM-DD 或 ISO 时间，改稿时填，用于 dateModified)。

SEO：每页 canonical / og / twitter / JSON-LD（文章 BlogPosting，首页 WebSite+Blog），
RSS /feed.xml（全文），sitemap.xml（含 lastmod 与 image 扩展），IndexNow key 文件。
"""
import html, json, re, shutil, sys
from datetime import date, datetime
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"
BASE = "https://blog.readcine.com"
SITE_NAME = "观影导览"
SITE_DESC = "观影导览：新片观影指南、IMAX 等影厅制式选择、选角新闻解读与电影奖项盘点，公众号「观影导览」文章存档。"
ICP = "湘ICP备2026041550号-1"
ASSET_VER = "20261124b"
TZ = ZoneInfo("Asia/Shanghai")
LOGO = f"{BASE}/assets/icon.png"
INDEXNOW_KEY = (ROOT / "tools" / "indexnow.key").read_text().strip()

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


def iso(d):
    """YYYY-MM-DD 或 ISO 时间 -> 带 +08:00 的 ISO 时间。"""
    dt = datetime.fromisoformat(d) if "T" in d else datetime.fromisoformat(d + "T00:00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat()


def img_size(p: Path):
    try:
        with Image.open(p) as im:
            return im.size
    except Exception:
        return None


def jsonld(obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{s}</script>\n'


def page(title, desc, canonical, body, og_image=None, og_type="website", extra_head="", robots="index,follow,max-image-preview:large"):
    e = html.escape
    og = ""
    if og_image:
        url, size = og_image
        og += f'<meta property="og:image" content="{e(url)}">\n'
        if size:
            og += f'<meta property="og:image:width" content="{size[0]}">\n<meta property="og:image:height" content="{size[1]}">\n'
        og += f'<meta property="og:image:alt" content="{e(title)}">\n<meta name="twitter:image" content="{e(url)}">\n'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{e(canonical)}">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{BASE}/feed.xml">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="zh_CN">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
{og}{extra_head}<meta name="theme-color" content="#f5f5f7" media="(prefers-color-scheme: light)">
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


ORG = {"@type": "Organization", "name": SITE_NAME, "url": BASE + "/",
       "logo": {"@type": "ImageObject", "url": LOGO, "width": 180, "height": 180}}


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
        refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body) + re.findall(r'<img[^>]+src="([^"]+)"', body)
        for ref in refs:
            if ref.startswith(("http://", "https://")):
                die(f"{slug} 正文引用了外链图片 {ref}，请下载到 img/")
            if not (d / ref).exists():
                die(f"{slug} 引用的图片不存在：{ref}")
        h = markdown.markdown(body, extensions=["extra", "sane_lists"], output_format="html5")
        # 正文图：alt 为空时用标题，补宽高减少布局跳动
        def fix_img(m):
            tag = m.group(0)
            src = re.search(r'src="([^"]+)"', tag).group(1)
            if re.search(r'alt=""', tag):
                tag = tag.replace('alt=""', f'alt="{html.escape(meta["title"])}"')
            size = img_size(d / src)
            if size and "width=" not in tag:
                tag = tag.replace("<img ", f'<img width="{size[0]}" height="{size[1]}" ', 1)
            return tag.replace("<img ", '<img loading="lazy" decoding="async" ', 1)
        h = re.sub(r"<img [^>]+>", fix_img, h)
        meta["summary"] = meta.get("summary") or auto_summary(body)
        meta["published"] = iso(meta["date"])
        meta["modified"] = iso(meta["updated"]) if meta.get("updated") else meta["published"]
        meta["images"] = list(dict.fromkeys(([meta["cover"]] if meta.get("cover") else []) + refs))
        arts.append((meta, slug, h, d))

    arts.sort(key=lambda a: (a[0]["date"], a[1]), reverse=True)
    keep = {"assets"}  # 只对多余的文章目录做提示；站点根的验证文件（googleec182282ff6b202b.html 等）手动放、不会被删除
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
        og_img = (f"{url}{meta['cover']}", img_size(d / meta["cover"])) if meta.get("cover") else None
        ld = {
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": meta["title"], "description": meta["summary"],
            "image": [f"{url}{i}" for i in meta["images"]] or [LOGO],
            "datePublished": meta["published"], "dateModified": meta["modified"],
            "author": {"@type": "Organization", "name": SITE_NAME, "url": BASE + "/"},
            "publisher": ORG, "inLanguage": "zh-CN",
            "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url,
            "isPartOf": {"@type": "Blog", "@id": BASE + "/#blog", "name": SITE_NAME},
        }
        crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": meta["title"], "item": url}]}
        extra = (f'<meta property="article:published_time" content="{meta["published"]}">\n'
                 f'<meta property="article:modified_time" content="{meta["modified"]}">\n'
                 f'<meta property="article:author" content="{SITE_NAME}">\n' + jsonld(ld) + jsonld(crumbs))
        orig = f' · <a href="{e(meta["original"])}" rel="noopener" target="_blank">公众号原文</a>' if meta.get("original") else ""
        body = f"""<main class="article">
<h1 class="title">{e(meta['title'])}</h1>
<div class="meta"><time datetime="{meta['published']}">{cn_date(meta['date'])}</time> · {SITE_NAME}{orig}</div>
<article class="prose">
{h}
</article>
<div class="back"><a class="pill" href="/">← 全部文章</a></div>
</main>"""
        (out / "index.html").write_text(page(f"{meta['title']} · {SITE_NAME}", meta["summary"], url, body, og_img, "article", extra), encoding="utf-8")

    # 列表页
    cards = []
    for meta, slug, _, d in arts:
        img = ""
        if meta.get("cover"):
            sz = img_size(d / meta["cover"])
            wh = f' width="{sz[0]}" height="{sz[1]}"' if sz else ""
            img = f'<img class="card__img" src="/{slug}/{e(meta["cover"])}" alt="{e(meta["title"])}"{wh} loading="lazy" decoding="async">'
        cards.append(f"""<a class="card" href="/{slug}/">{img}<div class="card__body">
<h2 class="card__title">{e(meta['title'])}</h2>
<p class="card__sum">{e(meta['summary'])}</p>
<div class="meta"><time datetime="{meta['published']}">{cn_date(meta['date'])}</time></div></div></a>""")
    body = f"""<main class="wrap">
<section class="hero"><h1>{SITE_NAME}</h1></section>
<div class="grid">
{chr(10).join(cards)}
</div>
</main>"""
    first = next(((f"{BASE}/{s}/{m['cover']}", img_size(d / m["cover"])) for m, s, _, d in arts if m.get("cover")), None)
    latest = max((m["modified"] for m, *_ in arts), default=iso(date.today().isoformat()))
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "@id": BASE + "/#website", "name": SITE_NAME,
               "url": BASE + "/", "description": SITE_DESC, "inLanguage": "zh-CN", "publisher": ORG}
    blog_ld = {"@context": "https://schema.org", "@type": "Blog", "@id": BASE + "/#blog", "name": SITE_NAME,
               "url": BASE + "/", "description": SITE_DESC, "inLanguage": "zh-CN", "publisher": ORG,
               "dateModified": latest,
               "blogPost": [{"@type": "BlogPosting", "headline": m["title"], "url": f"{BASE}/{s}/",
                             "datePublished": m["published"], "dateModified": m["modified"],
                             "image": f"{BASE}/{s}/{m['cover']}" if m.get("cover") else LOGO,
                             "author": {"@type": "Organization", "name": SITE_NAME}} for m, s, _, _ in arts]}
    (SITE / "index.html").write_text(page(f"{SITE_NAME} · 新片观影指南与电影资讯解读", SITE_DESC, BASE + "/", body, first, "website", jsonld(site_ld) + jsonld(blog_ld)), encoding="utf-8")
    (SITE / "404.html").write_text(page(f"页面不存在 · {SITE_NAME}", SITE_DESC, BASE + "/", '<main class="wrap"><section class="hero"><h1>页面不存在</h1></section><a class="pill" href="/">← 全部文章</a></main>', robots="noindex"), encoding="utf-8")

    # sitemap（含 image 扩展）
    urls = [f"  <url><loc>{BASE}/</loc><lastmod>{latest}</lastmod></url>"]
    for m, s, _, _ in arts:
        imgs = "".join(f"<image:image><image:loc>{BASE}/{s}/{i}</image:loc></image:image>" for i in m["images"])
        urls.append(f"  <url><loc>{BASE}/{s}/</loc><lastmod>{m['modified']}</lastmod>{imgs}</url>")
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SITE / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")

    # RSS 2.0（全文，图片转绝对地址）
    def rfc822(isostr):
        return format_datetime(datetime.fromisoformat(isostr))
    items = []
    for m, s, h, _ in arts:
        url = f"{BASE}/{s}/"
        full = re.sub(r'src="(img/[^"]+)"', lambda mm: f'src="{url}{mm.group(1)}"', h)
        enc = ""
        if m.get("cover"):
            p = SITE / s / m["cover"]
            enc = f'<enclosure url="{url}{m["cover"]}" length="{p.stat().st_size if p.exists() else 0}" type="image/jpeg"/>'
        items.append(f"""<item><title>{e(m['title'])}</title><link>{url}</link><guid isPermaLink="true">{url}</guid>
<pubDate>{rfc822(m['published'])}</pubDate><description>{e(m['summary'])}</description>
<content:encoded><![CDATA[{full.replace(']]>', ']]]]><![CDATA[>')}]]></content:encoded>{enc}</item>""")
    (SITE / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
<channel><title>{SITE_NAME}</title><link>{BASE}/</link><description>{e(SITE_DESC)}</description><language>zh-CN</language>
<lastBuildDate>{rfc822(latest)}</lastBuildDate>
<atom:link href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>
<image><url>{LOGO}</url><title>{SITE_NAME}</title><link>{BASE}/</link></image>
{chr(10).join(items)}
</channel></rss>
""", encoding="utf-8")

    for f in [x for x in SITE.rglob("*.html") if not x.name.startswith("google")] + [SITE / "feed.xml"]:
        scan(f.read_text(encoding="utf-8"), f)
    (ROOT / "articles.json").write_text(json.dumps([{"slug": s, "title": m["title"], "date": m["date"], "url": f"{BASE}/{s}/"} for m, s, _, _ in arts], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[build] 完成：{len(arts)} 篇 -> {SITE}")
    for m, s, _, _ in arts:
        print(f"  {BASE}/{s}/  {m['title']}")


if __name__ == "__main__":
    build()
