# readcine-articles

「观影导览」公众号定稿文章的自有存档站：<https://blog.readcine.com>

- `content/<slug>/article.md` + `img/`：每篇定稿（front matter：title / date / summary / cover / original）
- `tools/import_article.py`：把定稿 md（+图片目录）导入为 `content/<slug>/`
- `tools/build.py`：生成 `site/`（列表页、文章页、sitemap），并扫描网盘/磁力/密钥，命中即中止
- `site/`：纯静态产物，部署到 ECS `/var/www/readcine-articles`（nginx `blog.readcine.com`）

一键发布脚本：`~/workspace/goals/readcine/publish-article.sh`（盒子），副本在 Agent-Mine `dev-projects/readcine-articles/`。

## SEO

每页 canonical、og/twitter、JSON-LD（文章 BlogPosting+BreadcrumbList，首页 WebSite+Blog）；`/feed.xml` 全文 RSS；`sitemap.xml` 含 lastmod 与图片扩展；IndexNow key 在 `tools/indexnow.key`（公开文件，按协议放在站点根），发布脚本自动提交。改稿时在 front matter 加 `updated: YYYY-MM-DD` 更新 dateModified。
