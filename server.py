"""
GeoGlobe Intelligence — MCP Server
===================================
地缘新闻 3D 地球情报台

MCP 插件（手脚）：抓取全球主流媒体 RSS，地理编码，生成交互式 3D 地球 HTML。
配合 GeoGlobe Analyst Skill（大脑）做叙事冲突分析，分析结论以浮动标签标注在地球上。

运行：stdio 模式，由 WorkBuddy MCP 客户端拉起。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastmcp import FastMCP

try:
    from geopy.geocoders import Nominatim
    _HAS_GEOPY = True
except Exception:
    _HAS_GEOPY = False

mcp = FastMCP(name="GeoGlobe Intelligence")

# ============================================================
# 数据源：全球主流媒体 RSS
# 注：部分源在国内可能无法直连，抓取时做 try-except 容错。
# ============================================================
NEWS_SOURCES = {
    # === 中国本土视角（官方对外英文版，原汁原味措辞）===
    "CGTN": "https://www.cgtn.com/subscribe/rss/section/world.xml",
    "Xinhua": "http://www.xinhuanet.com/english/rss/worldrss.xml",
    "People's Daily": "http://www.people.com.cn/rss/politics.xml",
    "China Daily": "https://www.chinadaily.com.cn/rss/world_rss.xml",
    # === 俄罗斯视角 ===
    "TASS": "http://tass.com/rss/v2.xml",
    # === 日本视角 ===
    "NHK World": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    # === 韩国视角 ===
    "Yonhap": "https://en.yna.co.kr/RSS/news.xml",
    # === 伊朗视角（官方通讯社）===
    "IRNA": "https://en.irna.ir/rss",
    # === 以色列视角 ===
    "Jerusalem Post": "https://www.jpost.com/Rss/RssFeedsHeadlines.aspx",
    # === 拉美左翼视角 ===
    "TeleSUR": "https://www.telesurenglish.net/rss/",
    # === 西方视角（国内可能需代理，保留作对照）===
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Reuters World": "https://feeds.reuters.com/Reuters/worldNews",
}

# ============================================================
# 预置地理坐标字典
# 覆盖主要地缘热点城市/地区。关键词小写匹配标题与摘要。
# 作用：规避 Nominatim 限速（1 req/s）与对新闻标题编码不准的问题。
# ============================================================
GEO_DICT = {
    # --- 中国 ---
    "beijing": (39.9042, 116.4074, "北京"),
    "shanghai": (31.2304, 121.4737, "上海"),
    "hong kong": (22.3193, 114.1694, "中国香港"),
    "taipei": (25.0330, 121.5654, "中国台北"),
    "xinjiang": (43.7928, 87.6271, "新疆"),
    "tibet": (29.6500, 91.1000, "西藏"),
    # --- 美国 ---
    "washington": (38.9072, -77.0369, "华盛顿"),
    "white house": (38.8977, -77.0365, "白宫"),
    "new york": (40.7128, -74.0060, "纽约"),
    "los angeles": (34.0522, -118.2437, "洛杉矶"),
    "pentagon": (38.8719, -77.0563, "五角大楼"),
    "texas": (31.9686, -99.9018, "得克萨斯"),
    # --- 俄罗斯 / 东欧 ---
    "moscow": (55.7558, 37.6173, "莫斯科"),
    "kremlin": (55.7520, 37.6175, "克里姆林宫"),
    "kyiv": (50.4501, 30.5234, "基辅"),
    "kiev": (50.4501, 30.5234, "基辅"),
    "ukraine": (48.3794, 31.1656, "乌克兰"),
    "donetsk": (48.0159, 37.8028, "顿涅茨克"),
    "crimea": (44.9521, 34.1024, "克里米亚"),
    "belarus": (53.7098, 27.9534, "白俄罗斯"),
    "mins": (53.9006, 27.5590, "明斯克"),
    # --- 欧盟 ---
    "london": (51.5074, -0.1278, "伦敦"),
    "paris": (48.8566, 2.3522, "巴黎"),
    "berlin": (52.5200, 13.4050, "柏林"),
    "brussels": (50.8503, 4.3517, "布鲁塞尔"),
    "rome": (41.9028, 12.4964, "罗马"),
    "madrid": (40.4168, -3.7038, "马德里"),
    "warsaw": (52.2297, 21.0122, "华沙"),
    "european union": (50.8503, 4.3517, "欧盟"),
    # --- 中东 ---
    "israel": (31.0461, 34.8516, "以色列"),
    "jerusalem": (31.7683, 35.2137, "耶路撒冷"),
    "tel aviv": (32.0853, 34.7818, "特拉维夫"),
    "gaza": (31.5017, 34.4668, "加沙"),
    "west bank": (31.9462, 35.3027, "约旦河西岸"),
    "palestin": (31.9522, 35.2332, "巴勒斯坦"),
    "iran": (32.4279, 53.6880, "伊朗"),
    "tehran": (35.6892, 51.3890, "德黑兰"),
    "syria": (34.8021, 38.9968, "叙利亚"),
    "damascus": (33.5138, 36.2765, "大马士革"),
    "yemen": (15.5527, 48.5164, "也门"),
    "sanaa": (15.3694, 44.1910, "萨那"),
    "iraq": (33.3152, 44.3661, "伊拉克"),
    "baghdad": (33.3152, 44.3661, "巴格达"),
    "lebanon": (33.8547, 35.8623, "黎巴嫩"),
    "beirut": (33.8938, 35.5018, "贝鲁特"),
    "saudi arabia": (23.8859, 45.0792, "沙特阿拉伯"),
    "riyadh": (24.7136, 46.6753, "利雅得"),
    "uae": (23.4241, 53.8478, "阿联酋"),
    "dubai": (25.2048, 55.2708, "迪拜"),
    "qatar": (25.3548, 51.1839, "卡塔尔"),
    "doha": (25.2854, 51.5310, "多哈"),
    "turkey": (38.9637, 35.2433, "土耳其"),
    "ankara": (39.9334, 32.8597, "安卡拉"),
    "istanbul": (41.0082, 28.9784, "伊斯坦布尔"),
    "egypt": (26.8206, 30.8025, "埃及"),
    "cairo": (30.0444, 31.2357, "开罗"),
    "afghanistan": (33.9391, 67.7100, "阿富汗"),
    "kabul": (34.5553, 69.2075, "喀布尔"),
    # --- 亚太 ---
    "japan": (36.2048, 138.2529, "日本"),
    "tokyo": (35.6762, 139.6503, "东京"),
    "south korea": (35.9078, 127.7669, "韩国"),
    "seoul": (37.5665, 126.9780, "首尔"),
    "north korea": (40.3399, 127.5101, "朝鲜"),
    "pyongyang": (39.0392, 125.7625, "平壤"),
    "philippines": (12.8797, 121.7740, "菲律宾"),
    "manila": (14.5995, 120.9842, "马尼拉"),
    "vietnam": (14.0583, 108.2772, "越南"),
    "hanoi": (21.0285, 105.8542, "河内"),
    "india": (20.5937, 78.9629, "印度"),
    "new delhi": (28.6139, 77.2090, "新德里"),
    "mumbai": (19.0760, 72.8777, "孟买"),
    "pakistan": (30.3753, 69.3451, "巴基斯坦"),
    "islamabad": (33.6844, 73.0479, "伊斯兰堡"),
    "australia": (-25.2744, 133.7751, "澳大利亚"),
    "canberra": (-35.2809, 149.1300, "堪培拉"),
    "taiwan": (23.6978, 120.9605, "中国台湾"),
    "south china sea": (15.0000, 115.0000, "南海"),
    # --- 非洲 ---
    "south africa": (-30.5595, 22.9375, "南非"),
    "nigeria": (9.0820, 8.6753, "尼日利亚"),
    "sudan": (12.8628, 30.2176, "苏丹"),
    "ethiopia": (9.1450, 40.4897, "埃塞俄比亚"),
    "addis ababa": (9.0249, 38.7469, "亚的斯亚贝巴"),
    "somalia": (5.1521, 46.1996, "索马里"),
    "libya": (26.3351, 17.2283, "利比亚"),
    # --- 拉美 ---
    "brazil": (-14.2350, -51.9253, "巴西"),
    "brasilia": (-15.8267, -47.9218, "巴西利亚"),
    "argentina": (-38.4161, -63.6167, "阿根廷"),
    "mexico": (23.6345, -102.5528, "墨西哥"),
    "venezuela": (6.4238, -66.5897, "委内瑞拉"),
    "caracas": (10.4806, -66.9036, "加拉加斯"),
    "cuba": (21.5218, -77.7812, "古巴"),
    "havana": (23.1136, -82.3666, "哈瓦那"),
    # --- 其他 ---
    "united nations": (40.7484, -73.9656, "联合国"),
    "nato": (50.8466, 4.3528, "北约"),
    "geneva": (46.2044, 6.1432, "日内瓦"),
    # --- 日文关键词（NHK 等日媒，日文标题不匹配英文 key）---
    "ベネズエラ": (10.4806, -66.9036, "委内瑞拉"),
    "群馬": (36.3, 139.2, "群马"),
    "九州": (33.5, 130.5, "九州"),
    "ウィンブルドン": (51.5074, -0.1278, "伦敦"),
    "イラン": (32.4279, 53.6880, "伊朗"),
    "テヘラン": (35.6892, 51.3890, "德黑兰"),
    "ウクライナ": (48.3794, 31.1656, "乌克兰"),
    "ロシア": (55.7558, 37.6173, "俄罗斯"),
    "モスクワ": (55.7558, 37.6173, "莫斯科"),
    "イスラエル": (31.0461, 34.8516, "以色列"),
    "ガザ": (31.5017, 34.4668, "加沙"),
    "パレスチナ": (31.9522, 35.2332, "巴勒斯坦"),
    "北朝鮮": (40.3399, 127.5101, "朝鲜"),
    "韓国": (37.5665, 126.9780, "韩国"),
    "ソウル": (37.5665, 126.9780, "首尔"),
    "中国": (39.9042, 116.4074, "中国"),
    "アメリカ": (38.9072, -77.0369, "美国"),
    "イギリス": (51.5074, -0.1278, "英国"),
    "東京": (35.6762, 139.6503, "东京"),
    "国会": (35.6762, 139.6503, "东京"),
    "高市": (35.6762, 139.6503, "东京"),
    "ブラジル": (-14.235, -51.9253, "巴西"),
    "ノルウェー": (59.9139, 10.7522, "挪威"),
}

# 发布地排除表（每个源的本土。geocode时两遍匹配，优先跳过发布地匹配事件地）
SOURCE_HOMES = {
    "CGTN": {"beijing"},
    "Xinhua": {"beijing"},
    "China Daily": {"beijing"},
    "People's Daily": {"beijing"},
    "TASS": {"moscow", "kremlin"},
    "NHK World": {"tokyo"},
    "Yonhap": {"seoul", "south korea"},
    "IRNA": {"tehran", "iran"},
    "Jerusalem Post": {"jerusalem", "israel"},
    "TeleSUR": {"caracas"},
}

# 地理编码缓存（进程内）
_GEO_CACHE: dict[str, tuple[float | None, float | None, str | None]] = {}


# ============================================================
# 工具 1：generate_globe — 抓取 + 渲染 + 自动打开浏览器
# ============================================================
@mcp.tool
def generate_globe(hours_back: int = 24, annotations: str = "") -> dict:
    """
    抓取全球主流媒体过去 hours_back 小时的新闻，地理编码后生成
    左右分屏 3D 地球 HTML（左：地球+光柱脉冲，右：时间轴信息流），
    并自动在默认浏览器打开。

    参数：
        hours_back: 回溯小时数，默认 24。
        annotations: 可选。GeoGlobe Analyst Skill 产出的分析标签 JSON 字符串，
                     格式为列表 [{"title":..., "lat":.., "lon":.., "label":..., "conflict":"..."}]。
                     提供后以浮动标签形式叠加在地球上。
    返回：
        {"status":..., "message":..., "file":..., "count":...}
    """
    news_data = fetch_global_news(hours_back)
    anno_list = _parse_annotations(annotations)
    html_path = render_globe_html(news_data, anno_list)
    try:
        webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")
    except Exception:
        pass
    return {
        "status": "success",
        "message": f"已生成 3D 地球仪，包含 {len(news_data)} 条事件"
                   + (f"、{len(anno_list)} 个分析标签" if anno_list else ""),
        "file": html_path,
        "count": len(news_data),
    }


# ============================================================
# 工具 2：fetch_raw_news — 纯数据获取（供 Skill 大脑分析）
# ============================================================
@mcp.tool
def fetch_raw_news(hours_back: int = 24, keywords: str = "") -> list:
    """
    仅返回原始新闻数据 JSON，不做渲染。供 GeoGlobe Analyst Skill
    进行矛盾链追踪与叙事冲突标定。

    参数：
        hours_back: 回溯小时数。
        keywords: 可选关键词过滤（不区分大小写，匹配标题+摘要）。
    返回：
        [{"source","title","summary","link","time","lat","lon","place"}, ...]
    """
    return fetch_global_news(hours_back, keywords)


# ============================================================
# 工具 3：render_with_annotations — 用已有数据+分析标签重新渲染
# ============================================================
@mcp.tool
def render_with_annotations(news_data: str, annotations: str) -> dict:
    """
    接收已抓取的新闻数据 JSON 与分析标签 JSON，重新渲染带浮动标签的
    3D 地球 HTML 并打开浏览器。用于 Skill 分析完成后把结论贴到地球上。

    参数：
        news_data: fetch_raw_news 返回的 JSON 字符串。
        annotations: 分析标签 JSON 字符串。
    返回：
        {"status":..., "file":...}
    """
    try:
        news = json.loads(news_data) if isinstance(news_data, str) else news_data
    except Exception:
        news = []
    anno_list = _parse_annotations(annotations)
    html_path = render_globe_html(news, anno_list)
    try:
        webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")
    except Exception:
        pass
    return {"status": "success", "file": html_path, "labels": len(anno_list)}


# ============================================================
# 内部函数
# ============================================================
def _parse_annotations(raw: str) -> list:
    """安全解析分析标签 JSON。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_one_source(source, url, headers):
    """抓取单个 RSS 源，返回 (source, feed 或 None)。"""
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return source, feedparser.parse(resp.content)
    except Exception as e:
        print(f"[WARN] 抓取 {source} 失败: {e}")
        return source, None


def fetch_global_news(hours_back: int = 24, keywords: str = "") -> list:
    """并行抓取所有 RSS 源，过滤时间与关键词，地理编码。"""
    results: list[dict] = []
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours_back)
    headers = {
        "User-Agent": "Mozilla/5.0 (GeoGlobe/1.0) FastMCP News Aggregator"
    }
    # 并行抓取（max_workers=8 限并发，避免被源限流）
    feeds: dict = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_one_source, s, u, headers)
                   for s, u in NEWS_SOURCES.items()]
        for fut in as_completed(futures):
            src, feed = fut.result()
            if feed is not None:
                feeds[src] = feed
    # 串行处理条目（地理编码带缓存，字典匹配很快）
    for source, feed in feeds.items():
        for entry in getattr(feed, "entries", []):
            try:
                pub = _parse_entry_date(entry)
            except Exception:
                pub = now
            # 时间过滤（无时区则按本地处理）
            pub_cmp = pub
            if pub_cmp.tzinfo is None:
                pub_cmp = pub_cmp.replace(tzinfo=timezone.utc)
            if pub_cmp < since:
                continue
            title = entry.get("title", "").strip()
            summary = _clean_html(entry.get("summary", "")).strip()
            link = entry.get("link", "")
            text = f"{title} {summary}"
            if keywords and keywords.lower() not in text.lower():
                continue
            lat, lon, place = geocode_location(text, source)
            results.append({
                "source": source,
                "title": title,
                "summary": summary[:300],
                "link": link,
                "time": pub_cmp.astimezone(timezone.utc).isoformat(),
                "lat": lat,
                "lon": lon,
                "place": place,
            })
    # 按时间倒序
    results.sort(key=lambda x: x["time"], reverse=True)
    return results


def _parse_entry_date(entry) -> datetime:
    """从 feedparser entry 解析发布时间，失败返回当前时间。"""
    for field in ("published_parsed", "updated_parsed"):
        val = entry.get(field)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    # 退化：尝试字符串解析
    for field in ("published", "updated"):
        val = entry.get(field)
        if val:
            try:
                return datetime.strptime(val[:25], "%a, %d %b %Y %H:%M:%S")
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _clean_html(text: str) -> str:
    """去除 summary 里的 HTML 标签。"""
    return re.sub(r"<[^>]+>", "", text)


def geocode_location(text: str, source: str = ""):
    """
    地理编码：字典关键词匹配优先（快、准），匹配不到再用 Nominatim 兜底。
    两遍匹配：第一遍跳过发布地（源的本土），避免"首尔报道伊朗"被标在首尔。
    返回 (lat, lon, place) 或 (None, None, None)。
    """
    text_lower = text.lower()
    skip_keys = SOURCE_HOMES.get(source, set())
    # 1a. 第一遍：跳过发布地，匹配事件地
    for key, (lat, lon, place) in GEO_DICT.items():
        if key not in skip_keys and key in text_lower:
            return lat, lon, place
    # 1b. 第二遍：无事件地，回退匹配发布地（本媒体报道本土事件）
    for key, (lat, lon, place) in GEO_DICT.items():
        if key in text_lower:
            return lat, lon, place
    # 2. 缓存命中
    cache_key = text_lower[:80]
    if cache_key in _GEO_CACHE:
        return _GEO_CACHE[cache_key]
    # 3. geopy 兜底（限速）
    if _HAS_GEOPY:
        try:
            geolocator = Nominatim(user_agent="geo_globe_intel", timeout=8)
            loc = geolocator.geocode(text[:200])
            time.sleep(1)  # 遵守 1 req/s 限速
            if loc:
                result = (loc.latitude, loc.longitude, loc.address.split(",")[0])
                _GEO_CACHE[cache_key] = result
                return result
        except Exception:
            pass
    _GEO_CACHE[cache_key] = (None, None, None)
    return None, None, None


# ============================================================
# HTML 渲染：Three.js 3D 地球 + 时间轴信息流
# ============================================================
def render_globe_html(news_data: list, annotations: list | None = None) -> str:
    """生成交互式 HTML 并写入临时文件，返回绝对路径。"""
    annotations = annotations or []
    news_json = json.dumps(news_data, ensure_ascii=False)
    anno_json = json.dumps(annotations, ensure_ascii=False)

    html = _HTML_TEMPLATE
    html = html.replace("__NEWS_DATA__", news_json)
    html = html.replace("__ANNOTATIONS_DATA__", anno_json)
    html = html.replace("__GEN_TIME__", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    out_dir = Path(tempfile.gettempdir()) / "geo_globe"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "geo_globe.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


# ============================================================
# HTML 模板（Three.js + 左右分屏）
# 占位符：__NEWS_DATA__ / __ANNOTATIONS_DATA__ / __GEN_TIME__
# ============================================================
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GeoGlobe Intelligence · 全球地缘情报台</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:100%; height:100%; overflow:hidden;
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background:#05070d; color:#e6edf3; }
  #app { display:flex; width:100vw; height:100vh; }
  /* 左侧地球 */
  #globe-wrap { width:62%; height:100%; position:relative;
    background:radial-gradient(ellipse at center, #0a1428 0%, #05070d 70%); }
  #globe-canvas { width:100%; height:100%; display:block; }
  #globe-title { position:absolute; top:14px; left:18px; z-index:10;
    font-size:13px; letter-spacing:2px; color:#7dd3fc; opacity:.85;
    text-shadow:0 0 8px rgba(125,211,252,.4); }
  #globe-title b { color:#e6edf3; font-size:15px; }
  #legend { position:absolute; bottom:14px; left:18px; z-index:10;
    font-size:11px; color:#8b98a9; line-height:1.7; }
  #legend .dot { display:inline-block; width:8px; height:8px; border-radius:50%;
    margin-right:6px; vertical-align:middle; box-shadow:0 0 6px currentColor; }
  /* 浮动分析标签 */
  .anno-label { position:absolute; z-index:20; pointer-events:auto;
    background:rgba(15,23,42,.92); border:1px solid #f59e0b;
    border-radius:6px; padding:7px 11px; max-width:220px; font-size:11.5px;
    line-height:1.5; color:#fcd34d; box-shadow:0 0 16px rgba(245,158,11,.35);
    transform:translate(-50%,-115%); transition:opacity .2s; }
  .anno-label .anno-title { font-weight:600; color:#fef3c7; margin-bottom:2px; }
  .anno-label .anno-conflict { color:#fca5a5; font-size:10.5px; }
  .anno-label .anno-place { color:#94a3b8; font-size:10px; }
  /* 右侧信息流 */
  #feed-wrap { width:38%; height:100%; background:#0b0f17;
    border-left:1px solid #1e2632; display:flex; flex-direction:column; }
  #feed-header { padding:16px 20px 12px; border-bottom:1px solid #1e2632;
    background:linear-gradient(180deg,#0f1623,#0b0f17); }
  #feed-header h1 { font-size:16px; color:#e6edf3; font-weight:600; }
  #feed-header .meta { font-size:11px; color:#64748b; margin-top:4px; }
  #feed-header .count { color:#7dd3fc; font-weight:600; }
  #feed-list { flex:1; overflow-y:auto; padding:10px 16px 30px; }
  #feed-list::-webkit-scrollbar { width:6px; }
  #feed-list::-webkit-scrollbar-thumb { background:#1e2632; border-radius:3px; }
  .news-card { position:relative; padding:12px 14px 12px 26px; margin-bottom:10px;
    background:#11161f; border:1px solid #1a2230; border-radius:8px;
    cursor:pointer; transition:all .2s; }
  .news-card:hover { border-color:#334155; background:#141b26; transform:translateX(2px); }
  .news-card.active { border-color:#7dd3fc; box-shadow:0 0 0 1px #7dd3fc, 0 0 18px rgba(125,211,252,.25); }
  .news-card::before { content:""; position:absolute; left:9px; top:14px; bottom:14px;
    width:2px; background:linear-gradient(180deg,#7dd3fc,#334155); border-radius:1px; }
  .news-card .nc-time { font-size:10.5px; color:#64748b; }
  .news-card .nc-source { display:inline-block; font-size:10px; font-weight:600;
    padding:1px 7px; border-radius:10px; margin-left:6px; vertical-align:middle; }
  .src-CGTN { background:#1e3a5f; color:#7dd3fc; }
  .src-BBC-World { background:#5b1a1a; color:#fca5a5; }
  .src-Al-Jazeera { background:#5b3a1a; color:#fcd34d; }
  .src-NHK-World { background:#3a1a5b; color:#c4b5fd; }
  .src-China-Daily { background:#1a4d3a; color:#6ee7b7; }
  .src-Reuters-World { background:#5b1a3a; color:#f9a8d4; }
  .src-TASS { background:#3a1a1a; color:#fca5a5; }
  .src-IRNA { background:#0d3b27; color:#86efac; }
  .src-Xinhua { background:#5b1a1a; color:#fca5a5; }
  .src-Global-Times { background:#4a1a1a; color:#f87171; }
  .src-Peoples-Daily { background:#4a2a1a; color:#fbbf24; }
  .src-Yonhap { background:#2a1a4b; color:#c4b5fd; }
  .src-Jerusalem-Post { background:#1a2a4b; color:#93c5fd; }
  .src-TeleSUR { background:#4b3a1a; color:#fcd34d; }
  .news-card .nc-title { font-size:13px; font-weight:600; color:#e6edf3;
    margin-top:5px; line-height:1.4; }
  .news-card .nc-summary { font-size:11.5px; color:#94a3b8; margin-top:5px;
    line-height:1.55; display:-webkit-box; -webkit-line-clamp:3;
    -webkit-box-orient:vertical; overflow:hidden; }
  .news-card .nc-place { font-size:10px; color:#7dd3fc; margin-top:6px; }
  .news-card .nc-place.no-geo { color:#475569; }
  #empty { text-align:center; padding:60px 20px; color:#475569; font-size:13px; }
</style>
</head>
<body>
<div id="app">
  <div id="globe-wrap">
    <div id="globe-title"><b>GeoGlobe Intelligence</b> · 3D 地缘情报台</div>
    <canvas id="globe-canvas"></canvas>
    <div id="legend">
      <div><span class="dot" style="color:#f87171"></span>新闻事件光柱（脉冲）</div>
      <div><span class="dot" style="color:#f59e0b"></span>叙事冲突分析标签</div>
      <div style="margin-top:4px;color:#475569">拖拽旋转 · 滚轮缩放 · 点击光柱定位</div>
    </div>
  </div>
  <div id="feed-wrap">
    <div id="feed-header">
      <h1>全球情报流 · 时间轴</h1>
      <div class="meta">生成时间：__GEN_TIME__ · 共 <span class="count" id="totalCount">0</span> 条事件</div>
    </div>
    <div id="feed-list"></div>
  </div>
</div>

<script type="importmap">
{ "imports": {
  "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const NEWS = __NEWS_DATA__;
const ANNOTATIONS = __ANNOTATIONS_DATA__;
const EARTH_R = 100;

// ---------- Three.js 场景 ----------
const canvas = document.getElementById('globe-canvas');
const globeWrap = document.getElementById('globe-wrap');
const renderer = new THREE.WebGLRenderer({ canvas, antialias:true, alpha:true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(globeWrap.clientWidth, globeWrap.clientHeight);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, globeWrap.clientWidth/globeWrap.clientHeight, 0.1, 2000);
camera.position.set(0, 60, 240);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 150;
controls.maxDistance = 500;
controls.rotateSpeed = 0.5;

// 灯光
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
dirLight.position.set(200, 150, 200);
scene.add(dirLight);

// 星空背景
const starGeo = new THREE.BufferGeometry();
const starCount = 2500;
const starPos = new Float32Array(starCount * 3);
for (let i=0;i<starCount;i++){
  const r = 700 + Math.random()*300;
  const t = Math.random()*Math.PI*2, p = Math.acos(2*Math.random()-1);
  starPos[i*3]   = r*Math.sin(p)*Math.cos(t);
  starPos[i*3+1] = r*Math.sin(p)*Math.sin(t);
  starPos[i*3+2] = r*Math.cos(p);
}
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color:0xffffff, size:1.2, transparent:true, opacity:0.7 })));

// 地球
const earthGeo = new THREE.SphereGeometry(EARTH_R, 64, 64);
const earthMat = new THREE.MeshPhongMaterial({ color:0x113355, shininess:8 });
// 尝试加载纹理，失败用纯色
const texLoader = new THREE.TextureLoader();
texLoader.setCrossOrigin('anonymous');
texLoader.load(
  'https://unpkg.com/three-globe@2.31.0/example/img/earth-blue-marble.jpg',
  (tex) => { earthMat.map = tex; earthMat.color.set(0xffffff); earthMat.needsUpdate = true; },
  undefined,
  () => {
    // 退化：用一张程序生成的简绘纹理
    const c = document.createElement('canvas'); c.width=512; c.height=256;
    const ctx = c.getContext('2d');
    ctx.fillStyle='#0a2540'; ctx.fillRect(0,0,512,256);
    earthMat.map = new THREE.CanvasTexture(c); earthMat.needsUpdate=true;
  }
);
const earth = new THREE.Mesh(earthGeo, earthMat);
scene.add(earth);

// 经纬网格
const gridMat = new THREE.LineBasicMaterial({ color:0x1e3a5f, transparent:true, opacity:0.35 });
for (let lat=-80; lat<=80; lat+=20){
  const pts=[]; for(let lon=0;lon<=360;lon+=5) pts.push(latLonToVec3(lat,lon,EARTH_R+0.3));
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
}
for (let lon=0; lon<360; lon+=20){
  const pts=[]; for(let lat=-80;lat<=80;lat+=5) pts.push(latLonToVec3(lat,lon,EARTH_R+0.3));
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
}

// 大气光晕
const atmoGeo = new THREE.SphereGeometry(EARTH_R*1.06, 48, 48);
const atmoMat = new THREE.ShaderMaterial({
  vertexShader:`varying vec3 vN; void main(){ vN=normalize(normalMatrix*normal); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
  fragmentShader:`varying vec3 vN; void main(){ float i=pow(0.65-dot(vN,vec3(0,0,1.0)),2.5); gl_FragColor=vec4(0.3,0.6,1.0,1.0)*i; }`,
  blending:THREE.AdditiveBlending, side:THREE.BackSide, transparent:true
});
scene.add(new THREE.Mesh(atmoGeo, atmoMat));

// ---------- 标记点 + 光柱 ----------
function latLonToVec3(lat, lon, r){
  const phi=(90-lat)*Math.PI/180, theta=(lon+180)*Math.PI/180;
  return new THREE.Vector3(-r*Math.sin(phi)*Math.cos(theta), r*Math.cos(phi), r*Math.sin(phi)*Math.sin(theta));
}

const markers = [];
const newsWithGeo = NEWS.filter(n => n.lat!=null && n.lon!=null);
// ---------- 避让：相近坐标聚类 + 环形偏移（解决集中爆发地光柱重叠）----------
const CLUSTER_THRESH = 3; // 经纬度阈值（度），小于此归为同一爆发地
const clusters = [];
newsWithGeo.forEach(n => {
  let target = null;
  for (const c of clusters) {
    if (Math.abs(c.lat - n.lat) < CLUSTER_THRESH && Math.abs(c.lon - n.lon) < CLUSTER_THRESH) {
      target = c; break;
    }
  }
  if (target) target.members.push(n);
  else clusters.push({ lat:n.lat, lon:n.lon, members:[n] });
});
clusters.forEach(c => {
  const m = c.members.length;
  c.members.forEach((n, i) => {
    if (m > 1) {
      const angle = (i / m) * Math.PI * 2;
      const radius = Math.min(2.5, 0.8 + m * 0.15); // 簇越大散得越开，上限2.5度
      n._offLat = Math.cos(angle) * radius;
      n._offLon = Math.sin(angle) * radius / Math.max(0.2, Math.cos(n.lat * Math.PI / 180));
    } else { n._offLat = 0; n._offLon = 0; }
  });
});
NEWS.forEach((n, idx) => {
  if (n.lat==null || n.lon==null) return;
  const lat = n.lat + (n._offLat || 0);
  const lon = n.lon + (n._offLon || 0);
  const pos = latLonToVec3(lat, lon, EARTH_R);
  const srcColors={TASS:0xff4444,IRNA:0x44cc44,Yonhap:0x4488ff,CGTN:0xff8833,'NHK World':0xcc66ff};
  const clr=srcColors[n.source]||0xf87171;
  const group = new THREE.Group();
  group.position.copy(pos);
  // 朝向法线
  group.lookAt(pos.clone().multiplyScalar(2));

  // 标记小球
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(1.2, 12, 12),
    new THREE.MeshBasicMaterial({ color:clr })
  );
  group.add(dot);

  // 光柱
  const beamH = 14 + Math.random()*10;
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.4, 2.2, beamH, 8, 1, true),
    new THREE.MeshBasicMaterial({ color:clr, transparent:true, opacity:0.55, side:THREE.DoubleSide })
  );
  beam.rotation.x = Math.PI/2;  // 圆柱默认Y轴，转成沿法线方向
  beam.position.z = beamH/2;
  group.add(beam);

  // 光柱顶端光晕
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(2, 10, 10),
    new THREE.MeshBasicMaterial({ color:clr, transparent:true, opacity:0.5 })
  );
  halo.position.z = beamH;
  group.add(halo);

  group.userData = { idx, beam, halo, beamH, basePos: pos.clone(), news: n };
  earth.add(group);
  markers.push(group);
});

// ---------- 浮动分析标签（HTML overlay） ----------
const annoLayer = globeWrap;
const annoEls = [];
ANNOTATIONS.forEach(a => {
  const el = document.createElement('div');
  el.className = 'anno-label';
  el.innerHTML = `<div class="anno-title">${esc(a.title||'分析')}</div>` +
    (a.conflict?`<div class="anno-conflict">⚡ ${esc(a.conflict)}</div>`:'') +
    (a.place?`<div class="anno-place">📍 ${esc(a.place)}</div>`:'');
  el.style.display='none';
  annoLayer.appendChild(el);
  annoEls.push({ el, lat:a.lat, lon:a.lon, vec: (a.lat!=null&&a.lon!=null)? latLonToVec3(a.lat,a.lon,EARTH_R): null });
});

function esc(s){ return String(s).replace(/[<>&"]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c])); }

// ---------- 信息流渲染 ----------
const feedList = document.getElementById('feed-list');
document.getElementById('totalCount').textContent = NEWS.length;
if (NEWS.length===0){
  feedList.innerHTML = '<div id="empty">暂无情报数据<br>可能是 RSS 源无法访问，或时间范围内无更新</div>';
} else {
  NEWS.forEach((n, idx) => {
    const card = document.createElement('div');
    card.className = 'news-card';
    card.dataset.idx = idx;
    const srcClass = 'src-' + n.source.replace(/\s+/g,'-');
    const hasGeo = n.lat!=null && n.lon!=null;
    const timeStr = n.time ? n.time.replace('T',' ').substring(5,16) : '';
    card.innerHTML =
      `<div class="nc-time">${timeStr} UTC<span class="nc-source ${srcClass}">${esc(n.source)}</span></div>` +
      `<div class="nc-title">${esc(n.title)}</div>` +
      (n.summary?`<div class="nc-summary">${esc(n.summary)}</div>`:'') +
      (n.place?`<div class="nc-place ${hasGeo?'':'no-geo'}">${hasGeo?'📍':'⚫'} ${esc(n.place)} (${n.lat?.toFixed(2)}, ${n.lon?.toFixed(2)})</div>`:'');
    card.addEventListener('click', () => {
      document.querySelectorAll('.news-card').forEach(c=>c.classList.remove('active'));
      card.classList.add('active');
      if (hasGeo) flyTo(n.lat, n.lon);
    });
    feedList.appendChild(card);
  });
}

// ---------- 飞行到坐标 ----------
function flyTo(lat, lon){
  const target = latLonToVec3(lat, lon, 260);
  const start = camera.position.clone();
  let t=0;
  function step(){
    t += 0.04;
    if (t>1) t=1;
    const ease = 1-Math.pow(1-t,3);
    camera.position.lerpVectors(start, target, ease);
    controls.update();
    if (t<1) requestAnimationFrame(step);
  }
  step();
}

// ---------- 点击地球标记 ----------
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let activeMarker = null;
canvas.addEventListener('click', (e) => {
  const rect = canvas.getBoundingClientRect();
  mouse.x = ((e.clientX-rect.left)/rect.width)*2-1;
  mouse.y = -((e.clientY-rect.top)/rect.height)*2+1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(markers, true);
  if (hits.length>0){
    let g = hits[0].object;
    while (g && !g.userData.idx) g = g.parent;
    if (g && g.userData.idx!=null){
      highlightMarker(g.userData.idx);
    }
  }
});

function highlightMarker(idx){
  markers.forEach(m=>{
    m.children[0].material.color.set(0xf87171);
    m.userData.beam.material.opacity = 0.55;
  });
  const m = markers.find(x=>x.userData.idx===idx);
  if (m){
    m.children[0].material.color.set(0x7dd3fc);
    m.userData.beam.material.opacity = 0.9;
    activeMarker = m;
    // 同步高亮卡片
    document.querySelectorAll('.news-card').forEach(c=>c.classList.remove('active'));
    const card = document.querySelector(`.news-card[data-idx="${idx}"]`);
    if (card){ card.classList.add('active'); card.scrollIntoView({behavior:'smooth', block:'center'}); }
    const n = m.userData.news;
    flyTo(n.lat, n.lon);
  }
}

// ---------- 动画循环 ----------
const clock = new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  controls.update();
  // 地球缓慢自转
  earth.rotation.y += 0.0008;
  // 光柱脉冲
  markers.forEach((m, i) => {
    const phase = t*2 + i*0.5;
    const pulse = 0.5 + 0.5*Math.sin(phase);
    m.userData.beam.material.opacity = 0.3 + 0.5*pulse;
    m.userData.beam.scale.y = 0.85 + 0.3*pulse;
    m.userData.halo.material.opacity = 0.3 + 0.5*pulse;
    m.userData.halo.scale.setScalar(0.8 + 0.4*pulse);
  });
  // 更新浮动标签位置
  annoEls.forEach(a => {
    if (!a.vec){ a.el.style.display='none'; return; }
    // 应用地球自转
    const worldPos = a.vec.clone().applyMatrix4(earth.matrixWorld);
    const screenPos = worldPos.clone().project(camera);
    if (screenPos.z > 1 || screenPos.z < -1){ a.el.style.display='none'; return; }
    // 判断是否在地球正面（朝向相机）
    const camDir = camera.position.clone().sub(worldPos).normalize();
    const normal = a.vec.clone().normalize().applyQuaternion(earth.quaternion);
    const facing = normal.dot(camDir);
    // 收紧：侧面(0.3以下)和背面不显示标签内容
    if (facing < 0.3){ a.el.style.display='none'; return; }
    const x = (screenPos.x*0.5+0.5)*globeWrap.clientWidth;
    const y = (-screenPos.y*0.5+0.5)*globeWrap.clientHeight;
    // 以窗口中心为主：离屏幕中心远的标签隐藏
    const cx = globeWrap.clientWidth/2, cy = globeWrap.clientHeight/2;
    const dist = Math.hypot(x-cx, y-cy);
    const maxDist = Math.min(globeWrap.clientWidth, globeWrap.clientHeight) * 0.42;
    if (dist > maxDist){ a.el.style.display='none'; return; }
    // 透明度渐变：正面中央1.0，侧面渐淡
    const fade = facing < 0.6 ? (facing - 0.3) / 0.3 : 1.0;
    a.el.style.display='block';
    a.el.style.left = x+'px';
    a.el.style.top = y+'px';
    a.el.style.opacity = fade;
  });
  renderer.render(scene, camera);
}
animate();

// ---------- 自适应 ----------
window.addEventListener('resize', () => {
  camera.aspect = globeWrap.clientWidth/globeWrap.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(globeWrap.clientWidth, globeWrap.clientHeight);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    mcp.run()
