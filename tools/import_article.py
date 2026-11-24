#!/usr/bin/env python3
"""把一篇定稿 md（+图片目录）导入为 content/<slug>/article.md + img/。

用法：import_article.py 定稿.md --slug bond-casting [--images 目录 ...] [--title ..] [--date YYYY-MM-DD]
                        [--summary ..] [--cover 文件名] [--original 公众号链接] [--force]
- md 自带 front matter 时以其为准，命令行参数覆盖。
- 无 front matter：标题取第一个 "# " 标题（并从正文移除），日期取文件名里的 YYYYMMDD。
- 正文里的图片（![](x) 或 <img src=x>）按 md 所在目录、再按 --images 目录（按文件名）查找，
  复制并压缩到 img/，引用改写成 img/<文件名>。找不到图片直接报错，不会静默丢图。
"""
import argparse, re, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MAXW = 1600


def die(m):
    print(f"[import] 错误：{m}", file=sys.stderr); sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md"); ap.add_argument("--slug", required=True)
    ap.add_argument("--images", action="append", default=[])
    for k in ("title", "date", "summary", "cover", "original"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的同 slug 文章")
    a = ap.parse_args()
    src = Path(a.md).expanduser().resolve()
    if not src.exists(): die(f"找不到 {src}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.slug): die("slug 只能小写字母数字和连字符")
    dest = ROOT / "content" / a.slug
    if (dest / "article.md").exists() and not a.force:
        die(f"content/{a.slug} 已存在；更新请加 --force")
    text = src.read_text(encoding="utf-8")
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1); meta[k.strip()] = v.strip().strip('"').strip("'")
        text = text[m.end():]
    if not meta.get("title"):
        h = re.search(r"^#\s+(.+?)\s*$", text, re.M)
        if h:
            meta["title"] = h.group(1).strip(); text = text[:h.start()] + text[h.end():]
    if not meta.get("date"):
        d = re.search(r"(20\d\d)(\d\d)(\d\d)", src.name)
        if d: meta["date"] = f"{d.group(1)}-{d.group(2)}-{d.group(3)}"
    for k in ("title", "date", "summary", "cover", "original"):
        if getattr(a, k): meta[k] = getattr(a, k)
    if not meta.get("title") or not meta.get("date"): die("缺标题或日期，请用 --title/--date 指定")

    search = [src.parent] + [Path(p).expanduser().resolve() for p in a.images]
    img_dir = dest / "img"; img_dir.mkdir(parents=True, exist_ok=True)

    def find(ref):
        p = (src.parent / ref)
        if p.is_file(): return p
        for d in search:
            q = d / Path(ref).name
            if q.is_file(): return q
        return None

    def copy(ref):
        if ref.startswith(("http://", "https://", "data:")): die(f"正文含外链图片 {ref}，请先下载到图片目录")
        p = find(ref)
        if not p: die(f"找不到图片 {ref}（已查 {', '.join(map(str, search))}）")
        name = re.sub(r"[^A-Za-z0-9._-]", "-", p.name)
        out = img_dir / name
        im = Image.open(p)
        if im.width > MAXW:
            im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
        if p.suffix.lower() in (".jpg", ".jpeg"):
            im.convert("RGB").save(out, "JPEG", quality=84, optimize=True, progressive=True)
        else:
            im.save(out, optimize=True)
        return f"img/{name}"

    text = re.sub(r"(!\[[^\]]*\]\()([^)\s]+)", lambda mm: mm.group(1) + copy(mm.group(2)), text)
    text = re.sub(r'(<img[^>]+src=")([^"]+)', lambda mm: mm.group(1) + copy(mm.group(2)), text)
    if meta.get("cover"):
        if not meta["cover"].startswith("img/"): meta["cover"] = copy(meta["cover"])
    else:
        first = re.search(r"!\[[^\]]*\]\((img/[^)\s]+)", text)
        if first: meta["cover"] = first.group(1)
    order = ["title", "date", "summary", "cover", "original"]
    fm = "\n".join(f"{k}: {meta[k]}" for k in order if meta.get(k))
    (dest / "article.md").write_text(f"---\n{fm}\n---\n\n{text.strip()}\n", encoding="utf-8")
    print(f"[import] 已导入 content/{a.slug}（{len(list(img_dir.iterdir()))} 张图）")


if __name__ == "__main__":
    main()
