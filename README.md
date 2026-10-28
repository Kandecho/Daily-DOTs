# Daily DOTs

全球晚间新闻：每晚一期，最多 5 条主新闻加 1 条探索位，在手机上横向翻页、一条一页地读。这首先是我自己每天看的日报，公开只是为了方便阅读和维护。

**阅读：<https://kandecho.github.io/Daily-DOTs/>**

## 它做什么

把已经写好并核实过的 Markdown 原稿，确定性地排成一个单文件 HTML。字体子集、地图、样式和脚本都内嵌在文件里，下载后可以离线阅读。

- 不抓新闻，不做事实核查，不改正文；排版只由程序和共用模板决定。
- 数字和日期的强调、地图、正文回读核对都由程序计算，见 [排版约定](docs/排版约定.md)。
- 静态站点，没有后端、账号、统计或跟踪。

## 目录

```text
editions/YYYY-MM-DD/   Git 只存原稿_YYYY-MM-DD.md；本地可保留单期 HTML
_site/                 全部期次 HTML 和首页，只用于检查和发布，不入 Git
tools/                 生成程序、模板、样式、地图底图（daily.py 是入口）
tests/                 测试（Python，另有一个 Node 脚本）
docs/                  排版约定、工作流程
AGENTS.md              给维护 agent 的入口
```

## 本地生成与发布

环境：Python 3.12 和 [`requirements.txt`](requirements.txt) 里的 fontTools；Node.js 只在跑测试时需要。两份字体不入 Git，版本和 SHA-256 见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。

```sh
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python tools/fetch_fonts.py                                    # 缺失时下载，已有/缓存也验 SHA-256

python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md    # 单期 HTML 本地留档，不提交
python tools/site.py --build                                   # 全部原稿 → _site/，离线校验字体与成品
python -m unittest discover -s tests                           # 改了程序或模板时
```

打开 `_site/index.html` 检查。统一构建不写回原稿目录；全部通过才替换 `_site`，失败保留上一份。单期 HTML 仍可下载离线读。

日常只提交原稿到 `main`；[Actions](.github/workflows/pages.yml) 构建全部期次和首页，再发布 Pages，也可手动触发。失败不发布。首次迁移在 Settings → Pages 把 Source 设为 **GitHub Actions**；推送后确认构建和部署成功。

已有克隆首次拉取迁移提交前，先另存旧 HTML；Git 应用删除记录时会移除原先跟踪的文件。本地留档和既有 Git 历史不清理。

日期只取 `issue_date`。单期命令遇到不同内容拒绝覆盖，同一期修订才加 `--overwrite`；退出码 1 是输入或环境问题，2 是成品核对失败。完整构建失败统一返回 1。

同样的原稿、字体和依赖得到同样的 HTML。字节级一致还要求相同的 zlib：Windows 上的 Python 3.14 用 zlib-ng，压出的字体字节不同（字形相同）。

## 维护

日常由 agent 维护，不绑定某一个。改动之前先读 [AGENTS.md](AGENTS.md) 和 [工作流程](docs/工作流程.md)。

## 许可

原创代码、模板、文档和编辑内容暂不授予开源许可。字体（SIL OFL 1.1）和地图（Natural Earth，公有领域）按各自许可，见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。新闻来源链接不代表获得了来源网站内容的再授权。
