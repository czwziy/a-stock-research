#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股主板股票一键分析脚本
基于 a-stock-data SKILL.md V3.2.2 指南
支持沪深主板股票（600/601/603/605/000/001/002/003）
"""

import sys
import time
import random
import requests
import pandas as pd
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from io import StringIO

# ==================== 全局配置 ====================
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 东财防封：全局节流 + 会话复用
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def em_get(url: str, params: dict = None, headers: dict = None,
           timeout: int = 15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    except Exception as e:
        # 记录错误但不中断程序
        print(f"[网络错误] {e}")
        raise
    finally:
        _em_last_call[0] = time.time()


def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "", sort_types: str = "-1") -> list:
    """东财数据中心统一查询"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ==================== 工具函数 ====================

def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀"""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"


def is_main_board(code: str) -> bool:
    """判断是否为沪深主板股票"""
    # 上海主板: 600/601/603/605
    # 深圳主板: 000/001/002/003
    if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
        return True
    return False


def normalize_code(input_str: str) -> str:
    """归一化股票代码"""
    input_str = input_str.strip().upper()
    # 移除市场前缀
    for prefix in ["SH", "SZ", "BJ"]:
        if input_str.startswith(prefix):
            input_str = input_str[2:]
        if input_str.endswith("." + prefix):
            input_str = input_str[:-3]
    return input_str


def search_stock_code(name: str) -> str:
    """通过股票名称搜索股票代码"""
    try:
        # 使用腾讯接口搜索
        url = f"https://smartbox.gtimg.cn/s3/?v=2&q={name}&t=all"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("gbk")

        # 解析结果
        if "v_hint=" in data:
            content = data.split("v_hint=")[1]
            if "^" in content:
                items = content.split("^")
                for item in items[:5]:
                    parts = item.split("~")
                    if len(parts) >= 3:
                        code = parts[0]
                        stock_name = parts[1]
                        market = parts[2]
                        if name in stock_name and is_main_board(code):
                            return code
        return ""
    except Exception as e:
        print(f"[WARN] 股票名称搜索失败: {e}")
        return ""


# ==================== 数据获取函数 ====================

def tencent_quote(codes: list) -> dict:
    """腾讯财经实时行情"""
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "amplitude_pct": float(vals[43]) if vals[43] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result


def mootdx_kline(code: str, category: int = 4, offset: int = 30):
    """mootdx K线数据"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')
        klines = client.bars(symbol=code, category=category, offset=offset)
        return klines
    except Exception as e:
        print(f"[WARN] mootdx K线获取失败: {e}")
        return None


def mootdx_finance(code: str):
    """mootdx 财务快照"""
    try:
        from mootdx.quotes import Quotes
        # 尝试多个服务器
        for market_type in ['std', 'ext']:
            try:
                client = Quotes.factory(market=market_type)
                fin = client.finance(symbol=code)
                # mootdx finance 返回的是 tuple (data_list, field_names)
                if isinstance(fin, tuple) and len(fin) >= 2:
                    data_list = fin[0]
                    if data_list and len(data_list) > 0:
                        return data_list[0]  # 返回第一条记录
                return fin
            except Exception:
                continue
        return None
    except Exception as e:
        print(f"[WARN] mootdx 财务数据获取失败: {e}")
        return None


def mootdx_f10(code: str, category: str = "最新提示"):
    """mootdx F10 公司资料"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std')
        text = client.F10(symbol=code, name=category)
        return text
    except Exception as e:
        print(f"[WARN] mootdx F10 获取失败: {e}")
        return None


def eastmoney_stock_info(code: str) -> dict:
    """东财个股基本面信息"""
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
        "secid": f"{market_code}.{code}",
    }
    headers = {"User-Agent": UA}
    r = em_get(url, params=params, headers=headers, timeout=10)
    d = r.json().get("data", {})
    return {
        "code": d.get("f57", ""),
        "name": d.get("f58", ""),
        "industry": d.get("f127", ""),
        "total_shares": d.get("f84", 0),
        "float_shares": d.get("f85", 0),
        "mcap": d.get("f116", 0),
        "float_mcap": d.get("f117", 0),
        "list_date": str(d.get("f189", "")),
        "price": d.get("f43", 0),
    }


def eastmoney_concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属"""
    market_code = 1 if code.startswith("6") else 0
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{market_code}.{code}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get("https://push2.eastmoney.com/api/qt/slist/get",
                   params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"[WARN] 东财板块归属请求失败: {e}")
        return {"total": 0, "boards": [], "concept_tags": []}

    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""),
            "lead_stock": it.get("f128", ""),
        })
    return {
        "total": len(boards),
        "boards": boards,
        "concept_tags": [b["name"] for b in boards],
    }


def eastmoney_fund_flow_minute(code: str) -> list:
    """个股资金流向（分钟级）"""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception as e:
        print(f"[WARN] push2 资金流请求失败: {e}")
        return []

    rows = []
    for line in d.get("data", {}).get("klines", []):
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "time": parts[0],
                "main_net": float(parts[1]),
                "small_net": float(parts[2]),
                "mid_net": float(parts[3]),
                "large_net": float(parts[4]),
                "super_net": float(parts[5]),
            })
    return rows


def stock_fund_flow_120d(code: str) -> list:
    """个股资金流（日级，120日）"""
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f"[WARN] push2 资金流请求失败: {e}")
        return []
    klines = d.get("data", {}).get("klines", [])

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "date": parts[0],
                "main_net": float(parts[1]) if parts[1] != "-" else 0,
                "small_net": float(parts[2]) if parts[2] != "-" else 0,
                "mid_net": float(parts[3]) if parts[3] != "-" else 0,
                "large_net": float(parts[4]) if parts[4] != "-" else 0,
                "super_net": float(parts[5]) if parts[5] != "-" else 0,
            })
    return rows


def ths_eps_forecast(code: str) -> pd.DataFrame:
    """同花顺机构一致预期EPS"""
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://basic.10jqka.com.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(StringIO(r.text))
        # 查找包含"每股收益"或"EPS"的表格
        for df in dfs:
            cols = [str(c) for c in df.columns]
            # 检查是否包含 EPS 相关列
            if any("每股收益" in c or "EPS" in c.upper() or "均值" in c for c in cols):
                # 进一步验证：检查是否有年度数据（如2024、2025等）
                if any(str(c).isdigit() and len(str(c)) == 4 for c in cols):
                    return df
        # 如果没有找到完全匹配的，返回第一个看起来像 EPS 预测的表格
        for df in dfs:
            if len(df.columns) >= 3:
                return df
        return pd.DataFrame()
    except Exception as e:
        print(f"[WARN] 同花顺一致预期获取失败: {e}")
        return pd.DataFrame()


def eastmoney_reports(code: str, max_pages: int = 2) -> list:
    """东财研报列表"""
    import json as _json
    import re as _re

    all_records = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2024-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        try:
            r = em_get("https://reportapi.eastmoney.com/report/list",
                       params=params,
                       headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)

            # reportapi 可能返回 JSONP 格式，需要剥离
            text = r.text.strip()
            if text.startswith("jQuery") or text.startswith("callback"):
                # 提取 JSON 部分
                match = _re.search(r'\((\{.*\})\)', text, _re.DOTALL)
                if match:
                    text = match.group(1)

            d = _json.loads(text)
            rows = d.get("data") or []
            if not rows:
                break
            all_records.extend(rows)
            if page >= (d.get("TotalPage", 1) or 1):
                break
        except Exception as e:
            print(f"[WARN] 研报获取第 {page} 页失败: {e}")
            break
    return all_records


def margin_trading(code: str, page_size: int = 10) -> list:
    """融资融券明细"""
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=page_size,
        sort_columns="DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye": row.get("RZYE", 0),
            "rzmre": row.get("RZMRE", 0),
            "rzche": row.get("RZCHE", 0),
            "rqye": row.get("RQYE", 0),
            "rqmcl": row.get("RQMCL", 0),
            "rqchl": row.get("RQCHL", 0),
            "rzrqye": row.get("RZRQYE", 0),
        })
    return rows


def holder_num_change(code: str, page_size: int = 5) -> list:
    """股东户数变化"""
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="END_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),
            "avg_shares": row.get("AVG_FREE_SHARES", 0),
        })
    return rows


def dividend_history(code: str, page_size: int = 10) -> list:
    """分红送转历史"""
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        # 东财返回的是每10股的金额，需要转换为每股
        bonus_per_10 = row.get("PRETAX_BONUS_RMB", 0) or 0
        bonus_per_share = round(bonus_per_10 / 10, 2) if bonus_per_10 else 0

        transfer_per_10 = row.get("TRANSFER_RATIO", 0) or 0
        transfer_per_share = round(transfer_per_10 / 10, 2) if transfer_per_10 else 0

        bonus_ratio_per_10 = row.get("BONUS_RATIO", 0) or 0
        bonus_ratio_per_share = round(bonus_ratio_per_10 / 10, 2) if bonus_ratio_per_10 else 0

        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": bonus_per_share,  # 每股派息
            "transfer_ratio": transfer_per_share,  # 每股转增
            "bonus_ratio": bonus_ratio_per_share,  # 每股送股
            "plan": row.get("ASSIGN_PROGRESS", ""),
        })
    return rows


def lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> dict:
    """限售解禁日历"""
    start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=365)
    start_str = start.strftime("%Y-%m-%d")

    history_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f"(SECURITY_CODE=\"{code}\")(FREE_DATE>='{start_str}')(FREE_DATE<='{trade_date}')",
        page_size=10,
        sort_columns="FREE_DATE", sort_types="-1",
    )
    history = []
    for row in history_data:
        history.append({
            "date": str(row.get("FREE_DATE", ""))[:10],
            "type": row.get("LIMITED_STOCK_TYPE", ""),
            "shares": row.get("FREE_SHARES_NUM", 0),
            "ratio": row.get("FREE_RATIO", 0),
        })

    end_date = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
    end_str = end_date.strftime("%Y-%m-%d")
    upcoming_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f"(SECURITY_CODE=\"{code}\")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_str}')",
        page_size=10,
        sort_columns="FREE_DATE", sort_types="1",
    )
    upcoming = []
    for row in upcoming_data:
        upcoming.append({
            "date": str(row.get("FREE_DATE", ""))[:10],
            "type": row.get("LIMITED_STOCK_TYPE", ""),
            "shares": row.get("FREE_SHARES_NUM", 0),
            "ratio": row.get("FREE_RATIO", 0),
        })

    return {"history": history, "upcoming": upcoming}


def eastmoney_stock_news(code: str, page_size: int = 10) -> list:
    """东财个股新闻"""
    import json
    import re

    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                  "pageIndex": 1, "pageSize": page_size, "preTag": "", "postTag": ""}},
    }, separators=(',', ':'))
    params = {"cb": cb, "param": inner_params}
    headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}
    r = em_get(url, params=params, headers=headers, timeout=15)

    text = r.text
    if "(" not in text or ")" not in text:
        return []
    json_str = text[text.index("(") + 1 : text.rindex(")")]
    d = json.loads(json_str)

    rows = []
    articles = d.get("result", {}).get("cmsArticleWebOld", []) or []
    for a in articles:
        rows.append({
            "title": re.sub(r'<[^>]+>', '', a.get("title", "")),
            "content": re.sub(r'<[^>]+>', '', a.get("content", ""))[:200],
            "time": a.get("date", ""),
            "source": a.get("mediaName", ""),
            "url": a.get("url", ""),
        })
    return rows


# ==================== 分析函数 ====================

def analyze_stock(input_str: str):
    """一键分析股票"""
    print("=" * 80)
    print(f"开始分析: {input_str}")
    print("=" * 80)

    # 1. 归一化代码
    code = normalize_code(input_str)
    if not code.isdigit() or len(code) != 6:
        # 尝试通过名称搜索
        code = search_stock_code(input_str)
        if not code:
            print(f"[ERROR] 无法找到股票: {input_str}")
            return None

    # 2. 检查是否为沪深主板
    if not is_main_board(code):
        print(f"[ERROR] {code} 不是沪深主板股票（仅支持 600/601/603/605/000/001/002/003）")
        return None

    print(f"股票代码: {code}")
    print()

    # 3. 获取实时行情（腾讯）
    print("【1】实时行情（腾讯财经）")
    print("-" * 80)
    try:
        quotes = tencent_quote([code])
        if code in quotes:
            q = quotes[code]
            print(f"股票名称: {q['name']}")
            print(f"当前价格: {q['price']} 元")
            print(f"涨跌额: {q['change_amt']:+.2f} 元")
            print(f"涨跌幅: {q['change_pct']:+.2f}%")
            print(f"今开: {q['open']:.2f} 元")
            print(f"最高: {q['high']:.2f} 元")
            print(f"最低: {q['low']:.2f} 元")
            print(f"昨收: {q['last_close']:.2f} 元")
            print(f"成交量: {q['amount_wan']:.0f} 万元")
            print(f"换手率: {q['turnover_pct']:.2f}%")
            print(f"振幅: {q['amplitude_pct']:.2f}%")
            print(f"量比: {q['vol_ratio']:.2f}")
            print(f"PE(TTM): {q['pe_ttm']:.2f}")
            print(f"PE(静): {q['pe_static']:.2f}")
            print(f"PB: {q['pb']:.2f}")
            print(f"总市值: {q['mcap_yi']:.2f} 亿")
            print(f"流通市值: {q['float_mcap_yi']:.2f} 亿")
            print(f"涨停价: {q['limit_up']:.2f} 元")
            print(f"跌停价: {q['limit_down']:.2f} 元")
        else:
            print("[WARN] 未获取到行情数据")
    except Exception as e:
        print(f"[ERROR] 行情获取失败: {e}")
    print()

    # 4. 获取基本面信息（东财）
    print("【2】基本面信息（东财）")
    print("-" * 80)
    try:
        info = eastmoney_stock_info(code)
        print(f"所属行业: {info['industry']}")
        print(f"总股本: {info['total_shares']/1e8:.2f} 亿股")
        print(f"流通股本: {info['float_shares']/1e8:.2f} 亿股")
        print(f"上市日期: {info['list_date']}")
    except Exception as e:
        print(f"[ERROR] 基本面获取失败: {e}")
    print()

    # 5. 获取板块归属
    print("【3】板块归属（东财）")
    print("-" * 80)
    try:
        blocks = eastmoney_concept_blocks(code)
        print(f"共 {blocks['total']} 个板块")
        if blocks['concept_tags']:
            print("板块列表:")
            for i, tag in enumerate(blocks['concept_tags'][:15], 1):
                print(f"  {i}. {tag}")
    except Exception as e:
        print(f"[ERROR] 板块归属获取失败: {e}")
    print()

    # 6. 获取财务数据（mootdx）
    print("【4】财务快照（mootdx）")
    print("-" * 80)
    try:
        fin = mootdx_finance(code)
        if fin:
            print(f"每股收益(EPS): {fin.get('eps', 'N/A')} 元")
            print(f"每股净资产: {fin.get('bvps', 'N/A')} 元")
            print(f"净资产收益率(ROE): {fin.get('roe', 'N/A')}%")
            print(f"净利润: {fin.get('profit', 'N/A')} 元")
            print(f"主营收入: {fin.get('income', 'N/A')} 元")
            print(f"总股本: {fin.get('zongguben', 'N/A')}")
            print(f"流通股本: {fin.get('liutongguben', 'N/A')}")
    except Exception as e:
        print(f"[ERROR] 财务数据获取失败: {e}")
    print()

    # 7. 获取一致预期
    print("【5】机构一致预期（同花顺）")
    print("-" * 80)
    try:
        df_eps = ths_eps_forecast(code)
        if not df_eps.empty:
            print("机构一致预期EPS:")
            print(df_eps.head())
        else:
            print("无机构覆盖或数据为空")
    except Exception as e:
        print(f"[ERROR] 一致预期获取失败: {e}")
    print()

    # 8. 获取研报列表
    print("【6】近期研报（东财）")
    print("-" * 80)
    try:
        reports = eastmoney_reports(code, max_pages=1)
        if reports:
            print(f"共 {len(reports)} 篇研报")
            for i, r in enumerate(reports[:5], 1):
                date = (r.get('publishDate') or '')[:10]
                org = r.get('orgSName', '')
                title = r.get('title', '')[:60]
                rating = r.get('emRatingName', '')
                print(f"  {i}. [{date}] {org} - {title} ({rating})")
        else:
            print("无研报")
    except Exception as e:
        print(f"[ERROR] 研报获取失败: {e}")
    print()

    # 9. 获取资金流向（当日）
    print("【7】当日资金流向（东财）")
    print("-" * 80)
    try:
        flow = eastmoney_fund_flow_minute(code)
        if flow:
            last = flow[-1]
            print(f"最新时间点: {last['time']}")
            print(f"主力净流入: {last['main_net']/1e4:.2f} 万元")
            print(f"超大单净流入: {last['super_net']/1e4:.2f} 万元")
            print(f"大单净流入: {last['large_net']/1e4:.2f} 万元")
            print(f"中单净流入: {last['mid_net']/1e4:.2f} 万元")
            print(f"小单净流入: {last['small_net']/1e4:.2f} 万元")

            # 统计全天
            total_main = sum(f['main_net'] for f in flow)
            print(f"\n全天主力累计净流入: {total_main/1e4:.2f} 万元")
        else:
            print("无资金流数据（可能非交易时间）")
    except Exception as e:
        print(f"[ERROR] 资金流向获取失败: {e}")
    print()

    # 10. 获取120日资金流
    print("【8】近120日资金流向（东财）")
    print("-" * 80)
    try:
        flow_120 = stock_fund_flow_120d(code)
        if flow_120:
            print(f"共 {len(flow_120)} 个交易日数据")
            recent_20 = flow_120[-20:]
            total_main_20 = sum(d['main_net'] for d in recent_20)
            print(f"近20日主力累计净流入: {total_main_20/1e8:.2f} 亿元")

            print("\n最近5日资金流:")
            for d in flow_120[-5:]:
                print(f"  {d['date']}: 主力={d['main_net']/1e4:.0f}万 超大单={d['super_net']/1e4:.0f}万")
        else:
            print("无120日资金流数据")
    except Exception as e:
        print(f"[ERROR] 120日资金流获取失败: {e}")
    print()

    # 11. 获取融资融券
    print("【9】融资融券（东财）")
    print("-" * 80)
    try:
        margin = margin_trading(code, page_size=5)
        if margin:
            print(f"最近 {len(margin)} 个交易日:")
            for d in margin:
                rzye_yi = d['rzye'] / 1e8 if d['rzye'] else 0
                rqye_yi = d['rqye'] / 1e8 if d['rqye'] else 0
                print(f"  {d['date']}: 融资余额={rzye_yi:.2f}亿 融券余额={rqye_yi:.2f}亿")
        else:
            print("无融资融券数据")
    except Exception as e:
        print(f"[ERROR] 融资融券获取失败: {e}")
    print()

    # 12. 获取股东户数
    print("【10】股东户数变化（东财）")
    print("-" * 80)
    try:
        holders = holder_num_change(code, page_size=5)
        if holders:
            print("股东户数变化:")
            for d in holders:
                change_str = f"{d['change_ratio']:+.2f}%" if d['change_ratio'] else "N/A"
                print(f"  {d['date']}: {d['holder_num']} 户 (环比 {change_str}) 户均持股 {d['avg_shares']}")
        else:
            print("无股东户数数据")
    except Exception as e:
        print(f"[ERROR] 股东户数获取失败: {e}")
    print()

    # 13. 获取分红历史
    print("【11】分红送转历史（东财）")
    print("-" * 80)
    try:
        dividends = dividend_history(code, page_size=5)
        if dividends:
            print("近期分红:")
            for d in dividends:
                bonus = d['bonus_rmb'] if d['bonus_rmb'] else 0
                transfer = d['transfer_ratio'] if d['transfer_ratio'] else 0
                bonus_ratio = d['bonus_ratio'] if d['bonus_ratio'] else 0
                print(f"  {d['date']}: 每股派息 {bonus}元 转增 {transfer} 送 {bonus_ratio} ({d['plan']})")
        else:
            print("无分红记录")
    except Exception as e:
        print(f"[ERROR] 分红历史获取失败: {e}")
    print()

    # 14. 获取解禁预警
    print("【12】限售解禁预警（东财）")
    print("-" * 80)
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        lockup = lockup_expiry(code, today)
        if lockup['history']:
            print(f"近1年历史解禁 {len(lockup['history'])} 批:")
            for h in lockup['history'][:3]:
                print(f"  {h['date']}: {h['type']} 数量={h['shares']}")
        if lockup['upcoming']:
            print(f"\n未来90天待解禁 {len(lockup['upcoming'])} 批:")
            for u in lockup['upcoming']:
                print(f"  {u['date']}: {u['type']} 数量={u['shares']}")
        else:
            print("未来90天无待解禁")
    except Exception as e:
        print(f"[ERROR] 解禁预警获取失败: {e}")
    print()

    # 15. 获取新闻
    print("【13】近期新闻（东财）")
    print("-" * 80)
    try:
        news = eastmoney_stock_news(code, page_size=5)
        if news:
            print(f"共 {len(news)} 条新闻")
            for i, n in enumerate(news[:5], 1):
                print(f"  {i}. [{n['time']}] {n['source']} - {n['title']}")
        else:
            print("无新闻")
    except Exception as e:
        print(f"[ERROR] 新闻获取失败: {e}")
    print()

    print("=" * 80)
    print("分析完成")
    print("=" * 80)

    return code


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python stock_analyzer.py <股票代码或名称>")
        print("示例: python stock_analyzer.py 003010")
        print("      python stock_analyzer.py 丽臣实业")
        sys.exit(1)

    input_str = sys.argv[1]
    analyze_stock(input_str)


if __name__ == "__main__":
    main()
