#!/usr/bin/env python3
"""ReadCine 观影导览文章存档：content/<slug>/article.md -> site/ 静态页。

article.md 头部是 front matter（--- 包裹的 key: value），正文是 Markdown。
必填：title, date(YYYY-MM-DD)。可选：summary, cover(相对 img/ 路径), original(公众号原文链接),
updated(YYYY-MM-DD 或 ISO 时间，改稿时填，用于 dateModified)。

SEO：每页 canonical / og / twitter / JSON-LD（文章 BlogPosting，首页 WebSite+Blog），
RSS /feed.xml（全文），sitemap.xml（含 lastmod 与 image 扩展），IndexNow key 文件。

构建时为正文图和封面生成 720w / 1080w WebP（只缩小不放大，原 JPG/PNG 保留作回退），
文章页用 <picture>，首图与列表首张封面优先加载。OG / Twitter / JSON-LD / sitemap / RSS enclosure
仍指向原图，保证社交抓取和结构化数据兼容。
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
ASSET_VER = "20261127-ipad"
TZ = ZoneInfo("Asia/Shanghai")
LOGO = f"{BASE}/assets/icon.png"
INDEXNOW_KEY = (ROOT / "tools" / "indexnow.key").read_text().strip()
WEBP_WIDTHS = (720, 1080)
WEBP_QUALITY = 78
ARTICLE_SIZES = "(max-width: 760px) calc(100vw - 40px), 720px"
CARD_SIZES = "(max-width: 640px) calc(100vw - 40px), (max-width: 980px) calc(50vw - 32px), 310px"

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


def planned_variants(src: Path):
    """计划生成的 WebP 宽度与文件名。只缩小不放大；原图窄于 720 时按原宽出一张。"""
    size = img_size(src)
    if not size:
        return []
    w = size[0]
    targets = [tw for tw in WEBP_WIDTHS if tw <= w] or [w]
    return [(tw, f"{src.stem}-{tw}w.webp") for tw in targets]


def write_webp_variants(src: Path, dest_dir: Path, variants):
    if not variants:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            frame = im.convert("RGBA")
        else:
            frame = im.convert("RGB")
        for tw, name in variants:
            if tw > w:
                continue
            th = h if tw == w else max(1, round(h * tw / w))
            canvas = frame if tw == w else frame.resize((tw, th), Image.Resampling.LANCZOS)
            canvas.save(dest_dir / name, "WEBP", quality=WEBP_QUALITY, method=6)


def picture(src_url, variants, size, alt, class_name="", eager=False, sizes=ARTICLE_SIZES, zoom=False):
    """variants: [(width, url)]，与 src_url 使用同一套路径前缀。"""
    e = html.escape
    loading = ' loading="eager" fetchpriority="high" decoding="async"' if eager else ' loading="lazy" decoding="async"'
    cls = f' class="{class_name}"' if class_name else ""
    wh = f' width="{size[0]}" height="{size[1]}"' if size else ""
    img = f'<img{cls} src="{e(src_url)}" alt="{e(alt)}"{wh}{loading}>'
    inner = img
    if variants:
        srcset = ", ".join(f"{url} {w}w" for w, url in variants)
        inner = f'<picture><source type="image/webp" srcset="{e(srcset)}" sizes="{e(sizes)}">{img}</picture>'
    if zoom:
        label = f"查看大图：{alt}" if alt else "查看大图"
        return f'<button type="button" class="zoom" aria-label="{e(label)}" data-full="{e(src_url)}">{inner}</button>'
    return inner


def abs_attr_urls(fragment: str, base_url: str) -> str:
    """把 src / srcset 里的相对路径改成文章绝对地址（RSS 全文用）。"""
    def rewrite(val: str) -> str:
        parts = []
        for item in val.split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            src = bits[0]
            if not src.startswith(("http://", "https://", "/", "data:")):
                bits[0] = base_url + src
            parts.append(" ".join(bits))
        return ", ".join(parts)

    def repl(m):
        return f'{m.group(1)}="{rewrite(m.group(2))}"'

    return re.sub(r'\b(src|srcset)="([^"]+)"', repl, fragment)


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
<a class="brand" href="/"><img class="brand__icon" src="/assets/icon.png" width="36" height="36" alt=""><span>{SITE_NAME}</span></a>
<a class="iconbtn" href="https://readcine.com/" aria-label="返回 ReadCine 首页" title="返回 ReadCine 首页"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v11h4.5v-6h4v6h4.5V9"/></svg></a>
</div></header>
{body}
<footer class="foot"><a class="foot__home" href="https://readcine.com/"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v11h4.5v-6h4v6h4.5V9"/></svg><span>回 ReadCine 首页</span></a><span class="foot__spacer"></span><span>© {date.today().year} ReadCine</span><a href="https://beian.miit.gov.cn/" rel="noopener" target="_blank">{ICP}</a></footer>
<button type="button" class="totop" hidden aria-label="回到顶部">
<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M5 14.5 12 8l7 6.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
</button>
<script src="/assets/site.js?v={ASSET_VER}" defer></script>
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


def pager_link(meta, slug, direction):
    e = html.escape
    label = "上一篇" if direction == "prev" else "下一篇"
    extra = " pager__link--next" if direction == "next" else ""
    return (f'<a class="pager__link{extra}" href="/{slug}/">'
            f'<span class="pager__dir">{label}</span>'
            f'<span class="pager__title">{e(meta["title"])}</span></a>')


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
        # 每张源图对应的 WebP 变体（文件名）
        var_map = {}
        img_dir = d / "img"
        if img_dir.is_dir():
            for src in sorted(img_dir.iterdir()):
                if src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and src.is_file():
                    if re.search(r"-\d+w\.webp$", src.name):
                        continue
                    var_map[src.name] = planned_variants(src)
        h = markdown.markdown(body, extensions=["extra", "sane_lists"], output_format="html5")
        img_i = [0]

        def fix_img(m, _meta=meta, _d=d, _var_map=var_map, _img_i=img_i):
            tag = m.group(0)
            src = re.search(r'src="([^"]+)"', tag).group(1)
            alt_m = re.search(r'alt="([^"]*)"', tag)
            alt = (alt_m.group(1) if alt_m else "") or _meta["title"]
            size = img_size(_d / src)
            key = Path(src).name
            variants = [(w, str(Path(src).parent / name)) for w, name in _var_map.get(key, [])]
            _img_i[0] += 1
            return picture(src, variants, size, alt, eager=_img_i[0] == 1, sizes=ARTICLE_SIZES, zoom=True)

        h = re.sub(r"<img [^>]+>", fix_img, h)
        meta["summary"] = meta.get("summary") or auto_summary(body)
        meta["published"] = iso(meta["date"])
        meta["modified"] = iso(meta["updated"]) if meta.get("updated") else meta["published"]
        meta["images"] = list(dict.fromkeys(([meta["cover"]] if meta.get("cover") else []) + refs))
        arts.append((meta, slug, h, d, var_map))

    arts.sort(key=lambda a: (a[0]["date"], a[1]), reverse=True)
    keep = {"assets"}  # 只对多余的文章目录做提示；站点根的验证文件（googleec182282ff6b202b.html 等）手动放、不会被删除
    for slug_dir in SITE.iterdir():
        if slug_dir.is_dir() and slug_dir.name not in keep and slug_dir.name not in {a[1] for a in arts}:
            print(f"[build] 提示：site/{slug_dir.name} 已无对应 content，未删除（需要下线请手动处理）")
    e = html.escape
    for i, (meta, slug, h, d, var_map) in enumerate(arts):
        out = SITE / slug
        out.mkdir(parents=True, exist_ok=True)
        dest_img = out / "img"
        if (d / "img").is_dir():
            shutil.copytree(d / "img", dest_img, dirs_exist_ok=True)
            written = set()
            for src in (d / "img").iterdir():
                if src.name in var_map:
                    write_webp_variants(src, dest_img, var_map[src.name])
                    written.update(name for _, name in var_map[src.name])
            if dest_img.is_dir():
                for p in dest_img.glob("*.webp"):
                    if re.search(r"-\d+w\.webp$", p.name) and p.name not in written:
                        p.unlink()
        url = f"{BASE}/{slug}/"
        og_img = (f"{url}{meta['cover']}", img_size(d / meta["cover"])) if meta.get("cover") else None
        ld = {
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": meta["title"], "description": meta["summary"],
            "image": [f"{url}{im}" for im in meta["images"]] or [LOGO],
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
        # 按日期正序：上一篇 = 更早，下一篇 = 更新（arts 已按日期从新到旧）
        older = arts[i + 1] if i + 1 < len(arts) else None
        newer = arts[i - 1] if i > 0 else None
        pager_parts = []
        if older:
            pager_parts.append(pager_link(older[0], older[1], "prev"))
        if newer:
            pager_parts.append(pager_link(newer[0], newer[1], "next"))
        pager = f'<nav class="pager" aria-label="上下篇文章">{"".join(pager_parts)}</nav>' if pager_parts else ""
        body = f"""<main class="article">
<h1 class="title">{e(meta['title'])}</h1>
<div class="meta"><time datetime="{meta['published']}">{cn_date(meta['date'])}</time> · {SITE_NAME}{orig}</div>
<article class="prose">
{h}
</article>
{pager}
<div class="back"><a class="pill" href="/">← 全部文章</a></div>
</main>"""
        (out / "index.html").write_text(page(f"{meta['title']} · {SITE_NAME}", meta["summary"], url, body, og_img, "article", extra), encoding="utf-8")

    # 列表页
    cards = []
    for idx, (meta, slug, _, d, var_map) in enumerate(arts):
        img = ""
        if meta.get("cover"):
            sz = img_size(d / meta["cover"])
            cover_name = Path(meta["cover"]).name
            variants = [(w, f"/{slug}/{Path(meta['cover']).parent.as_posix()}/{name}") for w, name in var_map.get(cover_name, [])]
            img = picture(f"/{slug}/{e(meta['cover'])}", variants, sz, meta["title"],
                          class_name="card__img", eager=(idx == 0), sizes=CARD_SIZES, zoom=False)
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
    first = next(((f"{BASE}/{s}/{m['cover']}", img_size(d / m["cover"])) for m, s, _, d, _ in arts if m.get("cover")), None)
    latest = max((m["modified"] for m, *_ in arts), default=iso(date.today().isoformat()))
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "@id": BASE + "/#website", "name": SITE_NAME,
               "url": BASE + "/", "description": SITE_DESC, "inLanguage": "zh-CN", "publisher": ORG}
    blog_ld = {"@context": "https://schema.org", "@type": "Blog", "@id": BASE + "/#blog", "name": SITE_NAME,
               "url": BASE + "/", "description": SITE_DESC, "inLanguage": "zh-CN", "publisher": ORG,
               "dateModified": latest,
               "blogPost": [{"@type": "BlogPosting", "headline": m["title"], "url": f"{BASE}/{s}/",
                             "datePublished": m["published"], "dateModified": m["modified"],
                             "image": f"{BASE}/{s}/{m['cover']}" if m.get("cover") else LOGO,
                             "author": {"@type": "Organization", "name": SITE_NAME}} for m, s, *_ in arts]}
    (SITE / "index.html").write_text(page(f"{SITE_NAME} · 新片观影指南与电影资讯解读", SITE_DESC, BASE + "/", body, first, "website", jsonld(site_ld) + jsonld(blog_ld)), encoding="utf-8")
    (SITE / "404.html").write_text(page(f"页面不存在 · {SITE_NAME}", SITE_DESC, BASE + "/", '<main class="wrap"><section class="hero"><h1>页面不存在</h1></section><a class="pill" href="/">← 全部文章</a></main>', robots="noindex"), encoding="utf-8")

    # sitemap（含 image 扩展，仍指向原 JPG/PNG）
    urls = [f"  <url><loc>{BASE}/</loc><lastmod>{latest}</lastmod></url>"]
    for m, s, *_ in arts:
        imgs = "".join(f"<image:image><image:loc>{BASE}/{s}/{im}</image:loc></image:image>" for im in m["images"])
        urls.append(f"  <url><loc>{BASE}/{s}/</loc><lastmod>{m['modified']}</lastmod>{imgs}</url>")
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SITE / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")

    # RSS 2.0（全文，图片转绝对地址；enclosure 仍用原图）
    def rfc822(isostr):
        return format_datetime(datetime.fromisoformat(isostr))
    items = []
    for m, s, h, *_ in arts:
        url = f"{BASE}/{s}/"
        full = abs_attr_urls(h, url)
        enc = ""
        if m.get("cover"):
            p = SITE / s / m["cover"]
            suffix = Path(m["cover"]).suffix.lower()
            mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
            enc = f'<enclosure url="{url}{m["cover"]}" length="{p.stat().st_size if p.exists() else 0}" type="{mime}"/>'
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
    (ROOT / "articles.json").write_text(json.dumps([{"slug": s, "title": m["title"], "date": m["date"], "url": f"{BASE}/{s}/"} for m, s, *_ in arts], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[build] 完成：{len(arts)} 篇 -> {SITE}")
    for m, s, *_ in arts:
        print(f"  {BASE}/{s}/  {m['title']}")


if __name__ == "__main__":
    build()
