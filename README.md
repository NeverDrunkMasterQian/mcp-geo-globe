# GeoGlobe Intelligence — MCP + Skill 双核架构

> **MCP 插件（手脚）** 抓新闻、存数据、生成 3D 地球 HTML
> **Skill（大脑）** 分析新闻、归纳因果、判断叙事冲突
> **输出** 浏览器自动打开左右分屏 HTML — 左 3D 地球带光柱脉冲，右时间轴信息流瀑布

---

## 架构

```
用户指令
   │
   ├──► MCP 插件 (server.py)  ← 手脚：干活
   │      ├─ generate_globe()      抓取+渲染+打开浏览器
   │      ├─ fetch_raw_news()      纯数据获取（供Skill分析）
   │      └─ render_with_annotations()  用分析结论重新渲染带标签的地球
   │
   └──► GeoGlobe Analyst Skill  ← 大脑：思考
          ├─ 矛盾链追踪  比对同事件不同信源的措辞差异
          ├─ 叙事冲突标定 找出各方对"事件起因"解释的矛盾点
          └─ 输出 "事件：A方称X，B方称Y，争议焦点为Z"
```

## 文件结构

```
mcp-geo-globe/
├── server.py              # MCP 主程序（FastMCP + Three.js HTML 生成）
├── requirements.txt       # fastmcp, requests, feedparser, geopy
└── README.md              # 本文件
```

## 数据源

| 媒体 | RSS |
|------|-----|
| CGTN | world.xml |
| BBC World | news/world/rss.xml |
| Al Jazeera | xml/rss/all.xml |
| NHK World | cat0.xml |
| China Daily | world_rss.xml |
| Reuters World | worldNews |

> 部分源在国内可能无法直连，已做 try-except 容错，失败不影响其他源。

## 地理编码策略

1. **预置城市字典优先**（覆盖 80+ 地缘热点，快且准，规避 Nominatim 限速）
2. **geopy Nominatim 兜底**（带 1 req/s 限速 + 缓存）
3. 匹配不到 → 坐标置空（信息流仍显示，地球仪不标点）

## 3D 地球技术栈

- **Three.js 0.160**（CDN importmap，免 token，比 Cesium 更轻量）
- 地球纹理：three-globe 蓝色弹珠（CDN），加载失败退化程序绘制
- 标记：小球 + 光柱（CylinderGeometry）+ 顶端光晕，正弦脉冲动画
- 大气光晕：自定义 ShaderMaterial
- 星空背景：2500 个随机点
- 经纬网格线框
- OrbitControls：拖拽旋转 + 滚轮缩放
- 浮动分析标签：3D 坐标投影到屏幕，跟随地球自转，背面自动隐藏

## 交互

- 点击右侧卡片 → 地球飞行到对应坐标
- 点击地球光柱 → 卡片高亮 + 滚动到视图
- 地球自转 + 光柱脉冲

## 安装与运行

### 1. 依赖已安装到独立 venv

```
venv: C:\Users\Administrator\.workbuddy\binaries\python\envs\geo-globe
```

### 2. MCP 已注册

已写入 `~/.workbuddy/mcp.json` 的 `geo-globe` 条目。
在 WorkBuddy 连接器管理页点击「Trust」启用。

### 3. 在 WorkBuddy 中使用

**生成地球仪：**
> 用 geo-globe 的 generate_globe 工具生成过去 24 小时的地球仪

**获取数据并分析：**
> 用 geo-globe 的 fetch_raw_news 获取原始数据，套用 GeoGlobe Analyst Skill 进行分析，
> 然后用 render_with_annotations 把分析结论以浮动标签形式标注在地球仪上

## 工具 API

| 工具 | 参数 | 返回 |
|------|------|------|
| `generate_globe` | `hours_back=24`, `annotations=""` | `{status, message, file, count}` |
| `fetch_raw_news` | `hours_back=24`, `keywords=""` | `[{source,title,summary,link,time,lat,lon,place}]` |
| `render_with_annotations` | `news_data(str)`, `annotations(str)` | `{status, file, labels}` |

### annotations 格式

```json
[
  {
    "title": "加沙冲突",
    "lat": 31.5017,
    "lon": 34.4668,
    "place": "加沙",
    "conflict": "以色列称自卫反击，半岛台称屠杀平民，焦点：伤亡定性"
  }
]
```
