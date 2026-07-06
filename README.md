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
├── README.md              # 本文件
└── skills/
    └── geoglobe-analyst/
        └── SKILL.md       # Skill 大脑（矛盾链追踪 + 叙事冲突标定）
```

## 数据源

| 视角 | 媒体 | 国内可达 |
|------|------|----------|
| 中国 | CGTN / Xinhua / China Daily / 人民日报 | ✅ |
| 俄罗斯 | TASS 塔斯社 | ✅ |
| 日本 | NHK World | ✅ |
| 韩国 | Yonhap 韩联社 | ✅ |
| 伊朗 | IRNA 官方通讯社 | ✅ |
| 以色列 | Jerusalem Post | 🔸 |
| 拉美 | TeleSUR 南方电视台 | 🔸需代理 |
| 西方 | BBC / Al Jazeera / Reuters | 🔸需代理 |

> 13 个源并行抓取（ThreadPoolExecutor），国内 5 源直连可达。

## 地理编码策略

1. **预置城市字典优先**（覆盖 80+ 地缘热点，含中/英/日文关键词）
2. **两遍匹配**：先跳过发布地 → 匹配事件地，无事件地再回退发布地
3. **geopy Nominatim 兜底**（带 1 req/s 限速 + 缓存）
4. 匹配不到 → 坐标置空（信息流仍显示，地球仪不标点）

## 3D 地球技术栈

- **Three.js 0.160**（CDN importmap，免 token，比 Cesium 更轻量）
- 地球纹理：three-globe 蓝色弹珠（CDN），加载失败退化程序绘制
- 标记：彩色光柱按发布源着色（TASS红/IRNA绿/Yonhap蓝/CGTN橙/NHK紫）
- 光柱环形避让：同地多源自动环形散开，解决集中爆发地重叠
- 浮动分析标签：正面中央区显示，侧面渐淡，背面隐藏
- 大气光晕 + 星空背景 + 经纬网格
- OrbitControls：拖拽旋转 + 滚轮缩放

## 交互

- 点击右侧卡片 → 地球飞行到对应坐标
- 点击地球光柱 → 卡片高亮 + 滚动到视图
- 地球自转 + 光柱脉冲

## 安装与运行

### 1. 安装依赖

```bash
pip install fastmcp>=2.3.0 requests feedparser geopy
```

### 2. MCP 注册

将以下配置写入 `~/.workbuddy/mcp.json`：

```json
{
  "mcpServers": {
    "geo-globe": {
      "command": "<python路径>",
      "args": ["<项目路径>/server.py"]
    }
  }
}
```

在 WorkBuddy 连接器管理页点击「Trust」启用。

### 3. 安装 Skill

将 `skills/geoglobe-analyst/` 目录复制到 `{workspace}/.workbuddy/skills/`。

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
