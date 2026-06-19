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
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from io import StringIO

# ==================== 全局配置 ====================
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 新浪接口会话
SINA_SESSION = requests.Session()
SINA_SESSION.headers.update({"User-Agent": UA})


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
        encoded_name = urllib.parse.quote(name)
        url = f"https://smartbox.gtimg.cn/s3/?v=2&q={encoded_name}&t=all"
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
    """腾讯财经实时行情（增强版）
    
    可用字段说明（从返回值解析）：
    - vals[1]: 股票名称
    - vals[3]: 当前价格
    - vals[4]: 昨收
    - vals[5]: 今开
    - vals[31]: 涨跌额
    - vals[32]: 涨跌幅
    - vals[33]: 最高
    - vals[34]: 最低
    - vals[37]: 成交量（万元）
    - vals[38]: 换手率
    - vals[39]: PE(TTM)
    - vals[43]: 振幅
    - vals[44]: 总市值（亿）
    - vals[45]: 流通市值（亿）
    - vals[46]: PB
    - vals[47]: 涨停价
    - vals[48]: 跌停价
    - vals[49]: 量比
    - vals[52]: PE(静)
    - vals[100]: 行业（部分股票有）
    - vals[117]: 总股本
    - vals[118]: 流通股本
    - vals[119]: 上市日期
    """
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
            # 新增字段
            "industry": vals[100] if len(vals) > 100 and vals[100] else "N/A",
            "total_shares": float(vals[117]) if len(vals) > 117 and vals[117] else 0,
            "float_shares": float(vals[118]) if len(vals) > 118 and vals[118] else 0,
            "list_date": vals[119] if len(vals) > 119 and vals[119] else "N/A",
        }
    return result


def tencent_kline(code: str, days: int = 120) -> list:
    """腾讯K线数据（已验证可用）"""
    prefix = get_prefix(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    headers = {"User-Agent": UA}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        
        # 解析K线数据
        klines = []
        if data.get("code") == 0 and data.get("data"):
            stock_data = data["data"].get(f"{prefix}{code}", {})
            day_data = stock_data.get("qfqday", [])
            
            for item in day_data:
                if len(item) >= 6:
                    klines.append({
                        "date": item[0],
                        "open": float(item[1]),
                        "close": float(item[2]),
                        "high": float(item[3]),
                        "low": float(item[4]),
                        "volume": float(item[5]),
                    })
        return klines
    except Exception as e:
        print(f"[WARN] 腾讯K线数据请求失败: {e}")
        return []


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


def sina_stock_info(code: str) -> dict:
    """新浪个股基本面信息"""
    prefix = get_prefix(code)
    url = f"https://finance.sina.com.cn/realstock/company/{prefix}{code}/nc.shtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 从页面提取信息
        info = {
            "code": code,
            "name": "",
            "industry": "",
            "total_shares": 0,
            "float_shares": 0,
            "mcap": 0,
            "float_mcap": 0,
            "list_date": "",
            "price": 0,
        }
        
        # 提取股票名称
        if "var hq_str" in r.text:
            import re
            match = re.search(r'var hq_str_[a-z]{2}\d+="([^,]+)', r.text)
            if match:
                info["name"] = match.group(1)
        
        return info
    except Exception as e:
        print(f"[WARN] 新浪基本面请求失败: {e}")
        return {}


def sina_finance_data(code: str) -> dict:
    """新浪财务数据"""
    prefix = get_prefix(code)
    url = f"https://finance.sina.com.cn/realstock/company/{prefix}{code}/nc.shtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 从页面提取财务数据
        data = {
            "eps": 0,
            "bvps": 0,
            "roe": 0,
            "profit": 0,
            "income": 0,
            "total_shares": 0,
            "float_shares": 0,
        }
        
        # 简单提取（实际应该用正则或解析HTML）
        import re
        eps_match = re.search(r'每股收益[^:]*：([0-9.-]+)', r.text)
        if eps_match:
            data["eps"] = float(eps_match.group(1))
        
        bvps_match = re.search(r'每股净资产[^:]*：([0-9.-]+)', r.text)
        if bvps_match:
            data["bvps"] = float(bvps_match.group(1))
        
        return data
    except Exception as e:
        print(f"[WARN] 新浪财务数据请求失败: {e}")
        return {}


def sina_fund_flow(code: str, days: int = 120) -> list:
    """新浪资金流向（日级）"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_zjlrqs"
    params = {
        "page": "1",
        "num": str(days),
        "sort": "opendate",
        "asc": "0",
        "bankuai": "",
        "shession": f"{prefix}{code}",
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://vip.stock.finance.sina.com.cn/",
    }
    try:
        r = SINA_SESSION.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        
        rows = []
        for item in data:
            rows.append({
                "date": item.get("opendate", ""),
                "main_net": float(item.get("r0_net", 0) or 0),
                "small_net": float(item.get("r1_net", 0) or 0),
                "mid_net": float(item.get("r2_net", 0) or 0),
                "large_net": float(item.get("r3_net", 0) or 0),
                "super_net": float(item.get("r4_net", 0) or 0),
            })
        return rows
    except Exception as e:
        print(f"[WARN] 新浪资金流请求失败: {e}")
        return []


def sina_margin_trading(code: str, page_size: int = 10) -> list:
    """新浪融资融券明细"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vRM_MarginDetail/stockid/{code}.phtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 解析HTML表格
        dfs = pd.read_html(StringIO(r.text))
        if not dfs:
            return []
        
        # 找到融资融券表格
        for df in dfs:
            if "日期" in df.columns and "融资余额" in df.columns:
                rows = []
                for _, row in df.head(page_size).iterrows():
                    rows.append({
                        "date": str(row.get("日期", "")),
                        "rzye": float(row.get("融资余额", 0) or 0),
                        "rzmre": float(row.get("融资买入额", 0) or 0),
                        "rzche": float(row.get("融资偿还额", 0) or 0),
                        "rqye": float(row.get("融券余额", 0) or 0),
                        "rqmcl": float(row.get("融券卖出量", 0) or 0),
                        "rqchl": float(row.get("融券偿还量", 0) or 0),
                        "rzrqye": float(row.get("融资融券余额", 0) or 0),
                    })
                return rows
        return []
    except Exception as e:
        print(f"[WARN] 新浪融资融券请求失败: {e}")
        return []


def sina_holder_num(code: str, page_size: int = 5) -> list:
    """新浪股东户数变化"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vSD_NumShareholder/stockid/{code}.phtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 解析HTML表格
        dfs = pd.read_html(StringIO(r.text))
        if not dfs:
            return []
        
        # 找到股东户数表格
        for df in dfs:
            if "截止日期" in df.columns and "股东户数" in df.columns:
                rows = []
                for _, row in df.head(page_size).iterrows():
                    rows.append({
                        "date": str(row.get("截止日期", "")),
                        "holder_num": int(row.get("股东户数", 0) or 0),
                        "change_num": int(row.get("较上期变化", 0) or 0),
                        "change_ratio": float(row.get("变化率(%)", 0) or 0),
                        "avg_shares": float(row.get("户均持股数", 0) or 0),
                    })
                return rows
        return []
    except Exception as e:
        print(f"[WARN] 新浪股东户数请求失败: {e}")
        return []


def sina_dividend_history(code: str, page_size: int = 10) -> list:
    """新浪分红送转历史"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vISSUE_ShareBonus/stockid/{code}.phtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 解析HTML表格
        dfs = pd.read_html(StringIO(r.text))
        if not dfs:
            return []
        
        # 找到分红表格（查找包含"派息"或"送股"的表格）
        for df in dfs:
            cols = [str(c) for c in df.columns]
            # 检查是否包含分红相关列
            if any("派息" in c or "送股" in c or "转增" in c for c in cols):
                rows = []
                for _, row in df.head(page_size).iterrows():
                    # 新浪返回的是每10股数据，需要转换为每股
                    bonus_per_10 = 0
                    transfer_per_10 = 0
                    bonus_ratio_per_10 = 0
                    
                    # 查找派息列
                    for col in df.columns:
                        col_str = str(col)
                        if "派息" in col_str:
                            bonus_per_10 = float(row[col] or 0)
                        elif "转增" in col_str:
                            transfer_per_10 = float(row[col] or 0)
                        elif "送股" in col_str:
                            bonus_ratio_per_10 = float(row[col] or 0)
                    
                    # 转换为每股
                    bonus_per_share = round(bonus_per_10 / 10, 2) if bonus_per_10 else 0
                    transfer_per_share = round(transfer_per_10 / 10, 2) if transfer_per_10 else 0
                    bonus_ratio_per_share = round(bonus_ratio_per_10 / 10, 2) if bonus_ratio_per_10 else 0
                    
                    # 查找公告日期和进度
                    date_str = ""
                    plan_str = ""
                    for col in df.columns:
                        col_str = str(col)
                        if "公告日期" in col_str:
                            date_str = str(row[col])
                        elif "进度" in col_str:
                            plan_str = str(row[col])
                    
                    rows.append({
                        "date": date_str,
                        "bonus_rmb": bonus_per_share,
                        "transfer_ratio": transfer_per_share,
                        "bonus_ratio": bonus_ratio_per_share,
                        "plan": plan_str,
                    })
                return rows
        return []
    except Exception as e:
        print(f"[WARN] 新浪分红历史请求失败: {e}")
        return []


def sina_lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> dict:
    """新浪限售解禁日历"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vRestricted_Stock/stockid/{code}.phtml"
    headers = {"User-Agent": UA}
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 解析HTML表格
        dfs = pd.read_html(StringIO(r.text))
        
        history = []
        upcoming = []
        
        for df in dfs:
            if "解禁日期" in df.columns:
                for _, row in df.iterrows():
                    date_str = str(row.get("解禁日期", ""))
                    if not date_str or date_str == "nan":
                        continue
                    
                    item = {
                        "date": date_str[:10],
                        "type": str(row.get("股份类型", "")),
                        "shares": int(row.get("解禁数量(股)", 0) or 0),
                        "ratio": float(row.get("占总股本比例(%)", 0) or 0),
                    }
                    
                    # 判断是历史还是未来
                    try:
                        item_date = datetime.strptime(item["date"], "%Y-%m-%d")
                        trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
                        end_dt = trade_dt + timedelta(days=forward_days)
                        
                        if item_date < trade_dt and item_date > trade_dt - timedelta(days=365):
                            history.append(item)
                        elif trade_dt <= item_date <= end_dt:
                            upcoming.append(item)
                    except:
                        pass
        
        return {"history": history, "upcoming": upcoming}
    except Exception as e:
        print(f"[WARN] 新浪解禁预警请求失败: {e}")
        return {"history": [], "upcoming": []}


def sina_stock_news(code: str, page_size: int = 10) -> list:
    """新浪个股新闻"""
    prefix = get_prefix(code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllNews.php?stockid={code}"
    headers = {
        "User-Agent": UA,
        "Referer": "https://vip.stock.finance.sina.com.cn/",
    }
    try:
        r = SINA_SESSION.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        
        # 简单提取新闻标题
        import re
        news_list = []
        
        # 查找新闻链接
        pattern = r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, r.text)
        
        for url, title in matches[:page_size]:
            if "news" in url or "finance" in url:
                news_list.append({
                    "title": title.strip(),
                    "content": "",
                    "time": "",
                    "source": "新浪财经",
                    "url": url,
                })
        
        return news_list
    except Exception as e:
        print(f"[WARN] 新浪新闻请求失败: {e}")
        return []


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
            # 新增字段
            if q.get('industry') and q['industry'] != 'N/A':
                print(f"所属行业: {q['industry']}")
            if q.get('total_shares') and q['total_shares'] > 0:
                print(f"总股本: {q['total_shares']/1e8:.2f} 亿股")
            if q.get('float_shares') and q['float_shares'] > 0:
                print(f"流通股本: {q['float_shares']/1e8:.2f} 亿股")
            if q.get('list_date') and q['list_date'] != 'N/A':
                print(f"上市日期: {q['list_date']}")
        else:
            print("[WARN] 未获取到行情数据")
    except Exception as e:
        print(f"[ERROR] 行情获取失败: {e}")
    print()

    # 4. 获取K线数据（腾讯）
    print("【2】近120日K线数据（腾讯财经）")
    print("-" * 80)
    try:
        klines = tencent_kline(code, days=120)
        if klines:
            print(f"共 {len(klines)} 个交易日数据")
            print("\n最近5日K线:")
            for k in klines[-5:]:
                print(f"  {k['date']}: 开={k['open']:.2f} 收={k['close']:.2f} 高={k['high']:.2f} 低={k['low']:.2f} 量={k['volume']:.0f}")
            
            # 计算简单统计
            closes = [k['close'] for k in klines]
            print(f"\n120日统计:")
            print(f"  最高价: {max(closes):.2f}")
            print(f"  最低价: {min(closes):.2f}")
            print(f"  平均价: {sum(closes)/len(closes):.2f}")
        else:
            print("无K线数据")
    except Exception as e:
        print(f"[ERROR] K线数据获取失败: {e}")
    print()

    # 5. 获取一致预期（同花顺）
    print("【3】机构一致预期（同花顺）")
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

    # 6. 获取分红历史（新浪）
    print("【4】分红送转历史（新浪财经）")
    print("-" * 80)
    try:
        dividends = sina_dividend_history(code, page_size=5)
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
