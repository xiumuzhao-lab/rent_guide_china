# 链家租房数据采集与地理分析工具

上海租房市场数据采集与可视化分析工具，聚焦浦东区域（张江、金桥、唐镇、川沙）及长宁区。通过 Playwright 浏览器自动化采集链家租房数据，结合腾讯位置服务 API 生成通勤距离单价地图。

## 主要功能

### lianjia_scraper.py — 数据采集与分析

- **多区域爬取** — 支持张江、金桥、唐镇、川沙、长宁 5 个区域
- **反检测机制** — 模拟人类滚动/鼠标移动、动态延迟、浏览器指纹伪装
- **验证码自动处理** — 集成超级鹰自动识别极验验证码（最多 9 次），失败后通知手动处理
- **断点续爬** — 中断后重新运行自动从上次位置继续
- **数据去重与保存** — 输出 JSON + CSV，自动计算单价、添加经纬度
- **数据分析** — 生成 8 张统计图表 + 控制台摘要报告

### community_geo_map.py — 地图生成器

- **通勤距离地图** — 以工作地点为圆心，按距离分层（3/5/8/10/15km）展示小区
- **单价热力映射** — 圆点颜色映射单价（绿=便宜，红=贵）
- **地理编码** — 腾讯位置服务 API 获取精确坐标，结果自动缓存到本地
- **双格式输出** — 高清 PNG 静态图（5600x4400 像素）+ HTML 交互地图
- **控制台报告** — 按距离分层打印各小区均价、单价统计

## 快速开始

### 环境要求

- Python 3.10
- macOS（浏览器模式需要系统 Chrome）

### 安装依赖

```bash
# 核心依赖
python3.10 -m pip install playwright matplotlib folium
python3.10 -m playwright install chromium

# 可选依赖
python3.10 -m pip install adjustText              # 标签防重叠（推荐）
python3.10 -m pip install browser-use langchain-openai  # AI Agent 模式
```

### 配置腾讯地图 API

地理编码需要腾讯位置服务密钥。不配置也能运行，系统会回退到哈希散布算法生成近似坐标。

```bash
cp .env.example .env
```

编辑 `.env` 填入：

```
TENCENT_MAP_KEY=你的密钥
TENCENT_MAP_SK=你的签名密钥
```

API 密钥申请：[腾讯位置服务控制台](https://lbs.qq.com/)

### 典型工作流程

```bash
# 一键完成：爬取 + 分析 + 生成地图
python3.10 run_all.py --areas all --workplace 张江国创

# 仅生成地图（使用已有数据）
python3.10 run_all.py --skip-scrape --workplace 金桥

# 仅爬取分析（不生成地图）
python3.10 run_all.py --areas zhangjiang --skip-map
```

也可以分步执行：

```bash
python3.10 lianjia_scraper.py --areas all
python3.10 community_geo_map.py --workplace 张江国创
```

## 操作手册

### 零、一键运行 (run_all.py)

串行调用爬虫和地图生成器，一个命令完成全流程。

```bash
# 完整流程
python3.10 run_all.py --areas all --workplace 张江国创

# 指定数据文件生成地图
python3.10 run_all.py --skip-scrape --data output/lianjia_all_xxx.json --workplace 金桥

# 多工作地点对比
python3.10 run_all.py --skip-scrape --workplace 张江国创
python3.10 run_all.py --skip-scrape --workplace 金桥 --max-distance 10
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--areas` | `all` | 爬取区域 |
| `--max-pages` | `100` | 每区域最大页数 |
| `--mode` | `browser` | 爬取模式 |
| `--format` | `both` | 输出格式 |
| `--workplace` | `张江国创` | 工作地点 |
| `--max-distance` | `15` | 最大距离 km |
| `--max-labels` | `200` | 标注小区数 |
| `--skip-scrape` | — | 跳过爬取，仅生成地图 |
| `--skip-map` | — | 跳过地图，仅爬取分析 |
| `--data` | 自动查找 | 指定数据文件 |

### 一、数据采集 (lianjia_scraper.py)

#### 支持区域

| slug | 中文名 |
|------|--------|
| `zhangjiang` | 张江 |
| `jinqiao` | 金桥 |
| `tangzhen` | 唐镇 |
| `chuansha` | 川沙 |
| `changning` | 长宁 |

#### 常用命令

```bash
# 爬取所有区域
python3.10 lianjia_scraper.py --areas all

# 爬取指定区域，限制页数
python3.10 lianjia_scraper.py --areas zhangjiang,jinqiao --max-pages 20

# 仅分析已有数据（不爬取）
python3.10 lianjia_scraper.py --analyze output/lianjia_all_20260422_143000.json

# AI Agent 模式（需要 OPENAI_API_KEY）
OPENAI_API_KEY="sk-xxx" python3.10 lianjia_scraper.py --mode agent --areas all

# 仅输出 CSV
python3.10 lianjia_scraper.py --areas zhangjiang --format csv
```

#### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mode` | `browser` | 爬取模式：`browser`（浏览器）或 `agent`（AI） |
| `--areas` | `all` | 区域，逗号分隔，或 `all` |
| `--max-pages` | `100` | 每区域最大页数 |
| `--format` | `both` | 输出格式：`json` / `csv` / `both` |
| `--model` | `gpt-4o` | Agent 模式使用的 LLM |
| `--analyze` | — | 仅分析模式，指定 JSON 文件路径 |

#### 输出文件

```
output/
├── lianjia_zhangjiang_20260422_143000.json   # 单区域数据
├── lianjia_all_20260422_143000.json           # 合并数据
├── lianjia_all_20260422_143000.csv            # CSV 格式
├── lianjia_zhangjiang.partial.json            # 断点文件（完成后自动删除）
├── scraper.log                                # 运行日志
└── charts/
    ├── 1_price_by_region.png                  # 各区域价格箱线图
    ├── 2_price_histogram.png                  # 整体价格直方图
    ├── 3_rooms_by_region.png                  # 户型分布
    ├── 4_avg_area_by_region.png               # 各区域平均面积
    ├── 5_top_communities.png                  # 热门小区 TOP15
    ├── 6_rent_type_pie.png                    # 租赁类型饼图
    ├── 7_price_vs_area.png                    # 价格 vs 面积散点图
    └── 8_direction_by_region.png              # 朝向分布
```

#### 数据字段

| 字段 | 说明 |
|------|------|
| `region` | 区域 slug |
| `title` | 房源标题 |
| `rent_type` | 租赁类型（整租/合租等） |
| `community` | 小区名称 |
| `area` | 面积（㎡） |
| `rooms` | 户型（如 2室1厅） |
| `direction` | 朝向 |
| `floor` | 楼层信息 |
| `price` | 月租金（元） |
| `unit_price` | 单价（元/㎡/月） |
| `tags` | 标签（近地铁等） |
| `source` | 来源品牌 |
| `url` | 原始链接 |
| `scraped_at` | 采集时间 |
| `lat` / `lng` | 经纬度 |

### 二、地图生成 (community_geo_map.py)

#### 预定义工作地点

| 名称 | 拼音 key | 地址 |
|------|----------|------|
| 张江国创中心 | `zhangjiang` | 丹桂路899号 |
| 张江国创二期 | `zhangjiang_2` | 张江国创中心二期 |
| 金桥开发区 | `jinqiao` | 金桥经济技术开发区 |
| 唐镇 | `tangzhen` | 唐镇中心 |
| 川沙 | `chuansha` | 川沙新镇 |

支持中文模糊匹配（如输入"张江"匹配"张江国创中心"），也支持直接传入经纬度坐标。

#### 常用命令

```bash
# 默认以张江国创为中心，15km 范围
python3.10 community_geo_map.py

# 指定工作地点（支持中文名模糊匹配）
python3.10 community_geo_map.py --workplace 张江国创
python3.10 community_geo_map.py --workplace 金桥
python3.10 community_geo_map.py --workplace 唐镇 --max-distance 15

# 自定义坐标
python3.10 community_geo_map.py --workplace "31.22,121.54" --workplace-name "我的公司"

# 仅控制台报告（不生成图片）
python3.10 community_geo_map.py --dry-run

# 强制刷新所有小区坐标
python3.10 community_geo_map.py --refresh-geo

# 标注全部小区
python3.10 community_geo_map.py --max-labels 0

# 指定数据文件
python3.10 community_geo_map.py --data output/lianjia_all_20260422_143000.json
```

#### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--workplace` | `张江国创` | 工作地点：中文名/拼音key/经纬度 |
| `--workplace-name` | — | 自定义显示名 |
| `--data` | 自动查找最新 | 数据文件路径 |
| `--max-distance` | `15` | 最大距离（km） |
| `--max-labels` | `200` | 图片标注小区数，0=全部 |
| `--dry-run` | — | 仅打印报告，不生成图片 |
| `--refresh-geo` | — | 清除坐标缓存，重新获取 |

#### 输出文件

```
output/
├── community_geo_cache.json                        # 地理编码缓存
├── community_map_张江国创中心_20260422_143000.png   # 高清静态地图
└── community_map_张江国创中心_20260422_143000.html  # 交互式 HTML 地图
```

#### 距离环说明

| 距离 | 颜色 | 含义 |
|------|------|------|
| 0-3km | 绿色 | 步行可达 |
| 3-5km | 深绿 | 骑行/短途 |
| 5-8km | 橙色 | 短途公交 |
| 8-10km | 深橙 | 公交 |
| 10-15km | 红色 | 需地铁 |

## 项目结构

```
lianjia/
├── run_all.py                  # 一键运行脚本（爬取 + 分析 + 地图）
├── lianjia_scraper.py          # 数据采集脚本（爬虫 + 分析）
├── community_geo_map.py        # 地图生成脚本（PNG + HTML）
├── requirements.txt            # Python 依赖
├── scripts/
│   └── prepare_data.js         # 前端数据准备（复制 JSON 到 frontend/public）
├── frontend/                   # React 前端可视化项目
│   ├── src/
│   │   ├── App.jsx             # 主布局
│   │   ├── components/         # 图表、地图、表格等组件
│   │   └── utils/              # 工具函数（距离计算、统计聚合）
│   ├── public/data/            # 静态数据文件
│   └── package.json
├── .env                        # API 密钥配置（不入库）
├── .env.example                # API 密钥配置模板
├── .browser_data/              # 浏览器持久化数据（不入库）
├── output/                     # 输出目录
│   ├── lianjia_*.json/csv      # 爬取数据
│   ├── community_map_*.png     # 静态地图
│   ├── community_map_*.html    # 交互地图
│   ├── community_geo_cache.json # 地理编码缓存
│   ├── scraper.log             # 运行日志
│   └── charts/                 # 统计图表
└── README.md                   # 本文件
```

## 前端可视化

基于 React + Ant Design + ECharts + Leaflet 的交互式可视化前端。

### 快速启动

```bash
# 1. 准备数据（将最新爬取数据复制到前端 public 目录）
node scripts/prepare_data.js

# 2. 启动开发服务器
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

### 前端功能

- **工作地点选择** — 预定义地点 + 自定义坐标
- **总览卡片** — 房源总数、小区数、平均月租、平均单价
- **交互式地图** — Leaflet 距离环 + 小区散点（颜色=单价，大小=房源数）
- **距离表格** — 按距离分层，支持排序和筛选
- **8 张统计图表** — 价格分布、户型、热门小区、租赁类型等

## 注意事项

1. **爬取频率**：浏览器模式已内置人类行为模拟和动态延迟，请勿过于频繁运行
2. **验证码**：若触发验证码，需在弹出的浏览器窗口中手动完成；已配置超级鹰（`chaojiying.py`）则自动识别
3. **浏览器数据**：`.browser_data/` 保存登录状态，删除后需重新登录
4. **API 配额**：腾讯地图 API 有调用限制，已通过缓存机制（`community_geo_cache.json`）最小化调用次数
5. **数据隐私**：`.env` 文件含 API 密钥，已配置 `.gitignore` 不提交到仓库
