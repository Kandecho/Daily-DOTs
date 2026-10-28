# 全球晚间新闻 · 静态日报排版器

将已经完成来源核实的 Markdown 原稿，排成适合手机横向翻页、单条纵向阅读的 HTML 日报。全文、字体、地图和样式内嵌，下载后可离线阅读；只有主动点击新闻来源链接才需要联网。

本项目包含实际 Python 排版程序、HTML/CSS 模板、地图数据、测试，以及完整原稿和成品，不只是工作流程说明。不抓取新闻、不重新事实核查，不需要后端、数据库或前端构建工具。

## 阅读入口

打开仓库根目录的 [日报首页](index.html)，可进入最新一期和往期。首页按实际期次日期排序，不用系统日期替换旧新闻日期；本次收录从 **2026-10-27** 开始。

## 实际示例

- [2026-10-27 原稿](editions/2026-10-27/原稿_2026-10-27.md)
- [2026-10-27 翻页 HTML](editions/2026-10-27/全球晚间新闻_2026-10-27_翻页试读.html)：下载后用浏览器打开；GitHub 文件页不是阅读预览。

这是历史示例，保留日期和文件名，不把旧新闻更换日期。每期主要文件放在 `editions/YYYY-MM-DD/`：`原稿_YYYY-MM-DD.md` 和 `全球晚间新闻_YYYY-MM-DD_翻页.html`。

## 安装

- Python **3.11+**，已验证 Python 3.12.14。
- `fontTools`，版本锁定在 [`requirements.txt`](requirements.txt)。
- Noto Serif CJK Bold 和 Noto Sans CJK Regular **TTC** 字体。
- Node.js **仅用于测试**，已验证 v24.22.1；日常生成不需要 Node.js。

在项目根目录运行：

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows 可用 `.venv\Scripts\activate` 激活环境。

从 [Noto CJK 官方仓库](https://github.com/notofonts/noto-cjk)的下载指南或 Releases 获取两份 TTC，放到：

```text
tools/fonts/NotoSerifCJK-Bold.ttc
tools/fonts/NotoSansCJK-Regular.ttc
```

完整字体共约 45 MiB，不纳入 Git；已有本地字体保留，程序不会自动下载。Git 保留 `tools/fonts/OFL.txt`，成品内嵌字形子集与许可。精确版本、校验值和许可见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。

也可把两份字体放在自己的目录，生成时使用 `--font-dir 字体目录`。默认先找 `tools/fonts/`，再找 Linux 的 `/usr/share/fonts/opentype/noto/`；缺文件或缺字报错，不会静默漏字。首次准备依赖与字体后，生成可完全离线进行。

## 一条命令生成

```sh
python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md
```

日期只取原稿 `issue_date`，不取系统日期。输出与原稿同目录；已存在且内容相同可重复运行，内容不同则拒绝覆盖。

重建仓库示例到独立位置，不覆盖原成品：

```sh
python tools/daily.py editions/2026-10-27/原稿_2026-10-27.md --out _build/TEST_example/2026-10-27.html --build-dir _build/TEST_example/internal
```

其他选项：

```sh
# 断言日期正确，不替换原稿日期
python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md --date YYYY-MM-DD

# 明确确认同一期修订后，才允许替换现有 HTML
python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md --overwrite

# 使用另一个本地字体目录
python tools/daily.py editions/YYYY-MM-DD/原稿_YYYY-MM-DD.md --font-dir 字体目录
```

程序拒绝覆盖原稿、写入不同日期的期目录或文件名、覆盖另一日期 HTML。`--overwrite` 不解除跨期保护。生成检查全部通过才原子替换成品。

## 目录

```text
index.html            固定阅读入口（tools/site.py 自动生成）
.nojekyll             GitHub Pages 直接发布静态文件
editions/YYYY-MM-DD/    每期原稿与离线阅读 HTML
tools/site.py          验收后刷新最新一期与往期链接
tools/daily.py         日常入口
tools/*.py            解析、排版、地图、字体子集与核对逻辑
tools/*.html, *.css    模板与样式
tools/data/           共用 Natural Earth 底图
tools/fonts/OFL.txt    字体许可（完整字体本地准备，不入 Git）
tests/                Python/Node 测试
docs/                 排版约定与协作工作流程
requirements.txt      Python 运行依赖
THIRD_PARTY_NOTICES.md 第三方来源、许可与版本
_build/               本地中间结果与检查记录，不入 Git
archive/              本地备份，不入 Git
```

`daily.py` 仍通过 `newsfmt.py` 调用其他解析、排版模块及报纸/索引模板，因此不能只复制翻页模板或删去其他模块。日常交付的主要文件仍只有原稿和最终翻页 HTML。

## 检查

字体按上述说明放入 `tools/fonts/` 后运行：

```sh
mkdir -p _build
python -m unittest discover -s tests -v
```

生成时自动核对正文回读、标记段落与小节、完整来源 URL、导航目标、干净目录、原生回目录锚点、资源内嵌与字体缺字，记录保存在 `_build/`。退出码：`1` 为输入/依赖/构建失败，`2` 为渲染或成品核对失败。

测试涵盖少于五条主新闻、无探索位、跨年、重复构建、修订与旧期保护、链接参数、字体、地图和回目录导航合同。虚构测试数据标为 `TEST`，不作为新闻交付。自动检查不等于浏览器或真实手机验收，生成后做一次轻量排版检查，见 [工作流程](docs/工作流程.md)。

## GitHub Pages 发布

目标仓库为 [Kandecho/Daily-DOTs](https://github.com/Kandecho/Daily-DOTs)。Pages 使用 **Deploy from a branch → main → / (root)**；根目录 `.nojekyll` 保持纯静态发布，无需 Actions 工作流、后端、账号系统或另一套前端应用。仓库设置的实际启用与线上结果需在首次上传后核对，本地入口生成成功不代表已部署。

日常在原稿和 HTML 生成、自检、轻量排版验收之后，运行：

```sh
python tools/site.py
```

此命令只改根目录 `index.html`，不改日报、不联网、不提交 Git。它读取 `editions/YYYY-MM-DD/` 中完整且日期一致的一对文件，自动把最大期次日期设为最新一期，其余降序列入往期。旧期的 `翻页试读.html` 文件名保持兼容；一期开两个候选 HTML、缺文件或日期不一致都会报错并保留原首页。未完成的稿件先留在本地工作区，不放入待发布的 `editions/` 日期目录。

每次将该期两个主要文件与更新后的 `index.html` 一起提交；如修改生成器、模板、测试或公开说明，也一并提交相应变更。保持 `editions/` 为每期唯一原稿和成品位置，不复制日报到首页，不发布 `_build/`、备份、完整字体或私人工作记录。上传后分别核对远程提交、Pages 部署结果及网站首页显示的实际期次。完整顺序见 [工作流程](docs/工作流程.md)。

## 许可状态

项目原创代码、模板、文档和编辑内容的对外许可尚待仓库所有者确定；目前不默认授予 MIT 或其他开源许可。字体和地图各自许可继续适用，见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。新闻来源链接不代表本项目拥有来源网站内容的再授权权利。
