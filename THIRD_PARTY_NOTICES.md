# 第三方资源与许可

本文件只说明第三方组件，不为项目原创代码、模板、文档或新闻编辑内容选择许可证。原创部分许可由仓库所有者另行确定。

## Noto CJK 字体

- 官方来源与下载指南：[notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)。
- 许可：SIL Open Font License 1.1，全文保存在 [`tools/fonts/OFL.txt`](tools/fonts/OFL.txt)。
- 完整 TTC 留在本地，不入 Git；生成器提取简体中文字体，子集化为 WOFF，改名 Daily Serif SC / Daily Sans SC，并把许可嵌入 HTML。
- 需要以下 TTC 集合，不是单字体 OTF 或变量字体。要求字节级复现时还应使用相同字体校验值和 `requirements.txt` 依赖版本。

| 文件 | 版本 | SHA-256 |
| --- | --- | --- |
| `NotoSerifCJK-Bold.ttc` | 2.003 | `1505ee3b9c0890fae6302ee0e9c6fd74d690f4a55a6ace1d9944f3f6352d622d` |
| `NotoSansCJK-Regular.ttc` | 2.004 | `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a` |

固定版本下载：[Serif 2.003](https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/OTC/NotoSerifCJK-Bold.ttc)、[Sans 2.004](https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/OTC/NotoSansCJK-Regular.ttc)。`python tools/fetch_fonts.py` 下载缺失文件，并校验所有文件（包括缓存）；校验失败不替换已有文件。

两份完整字体共 46,881,836 字节（约 44.7 MiB）。不入 Git 是体积取舍，不改变字体许可；本地字体和离线生成能力保留。更新字体可能改变子集字节和排版细节，需重新验证。

## Natural Earth 地图

- 文件：`tools/data/ne_110m_countries.geojson`。
- 数据集：Natural Earth 1:110m Admin 0 Countries，GeoJSON 简化国界底图。
- 来源：[Natural Earth](https://www.naturalearthdata.com/)。
- [官方使用条款](https://www.naturalearthdata.com/about/terms-of-use/)说明其网站提供的矢量与栅格数据属于公有领域（public domain）。保留出处便于复核和协作。
- 只用于国家级定位示意，不作测绘、导航或精确疆界依据。每日生成使用仓库中的底图，不在线拉取。

## fontTools

运行时依赖，通过 `requirements.txt` 安装，未复制其源码。字体子集遵循字体自身许可；升级依赖后运行完整测试并重建示例。

## 新闻来源

原稿与 HTML 保留公开报道链接。链接说明新闻依据，不表示来源网站将版权或再授权权利转让给本项目。
