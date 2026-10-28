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
editions/YYYY-MM-DD/   每期两个文件：原稿_YYYY-MM-DD.md、全球晚间新闻_YYYY-MM-DD_翻页.html
index.html             首页，由 tools/site.py 生成
tools/                 生成程序、模板、样式、地图底图（daily.py 是入口）
tests/                 测试（Python，另有一个 Node 脚本）
docs/                  排版约定、工作流程
AGENTS.md              给维护 agent 的入口
```

## 生成一期

环境：Python 3.12 和 [`requirements.txt`](requirements.txt) 里的 fontTools；两份 Noto CJK TTC 字体放在 `tools/fonts/`（来源和校验值见 [第三方资源说明](THIRD_PARTY_NOTICES.md)，不入 Git）；Node.js 只在跑测试时需要。

```sh
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md   # 生成这一期的 HTML
python tools/site.py                                            # 刷新首页
python -m unittest discover -s tests                            # 改了程序或模板时
```

日期只取原稿里的 `issue_date`。已有成品内容不同时拒绝覆盖，确认是同一期修订才加 `--overwrite`。退出码 1 表示输入或环境有问题，2 表示成品核对没通过。

同样的原稿、字体和依赖得到同样的 HTML。字节级一致还要求相同的 zlib：Windows 上的 Python 3.14 用 zlib-ng，压出的字体字节不同（字形相同）。

## 维护

日常由 agent 维护，不绑定某一个。改动之前先读 [AGENTS.md](AGENTS.md) 和 [工作流程](docs/工作流程.md)。

## 许可

原创代码、模板、文档和编辑内容暂不授予开源许可。字体（SIL OFL 1.1）和地图（Natural Earth，公有领域）按各自许可，见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。新闻来源链接不代表获得了来源网站内容的再授权。
