"""神州数码(000034) 基本面 + 交易策略分析脚本
基于 a-stock-data SKILL.md 中的接口"""
import urllib.request
import requests
import pandas as pd
from io import StringIO
import json
import time
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

CODE = "000034"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ============ 东财统一限流入口 ============
# 沙箱在海外，需要通过代理访问中国站点
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
# 尝试使用代理（沙箱环境）
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url, params=None, headers=None, timeout=15, **kwargs):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    except Exception as e:
        print(f"  [WARN] 请求失败: {str(e)[:100]}")
        return None

def safe_call(func, *args, **kwargs):
    """安全调用，失败返回 None"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"  [ERROR] {func.__name__}: {str(e)[:100]}")
        return None

def eastmoney_datacenter(report_name, columns="ALL", filter_str="", page_size=50,
                         sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get("https://datacenter-web.eastmoney.com/api/data/v1/get",
               params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []

# ============ 1. 腾讯实时行情 ============
print("=" * 70)
print("【1】实时行情 & 估值")
print("=" * 70)
def tencent_quote(codes):
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")): prefixed.append(f"sh{c}")
        elif c.startswith("8"): prefixed.append(f"bj{c}")
        else: prefixed.append(f"sz{c}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
        }
    return result

quotes = tencent_quote([CODE])
q = quotes[CODE]
for k, v in q.items():
    print(f"  {k}: {v}")

# ============ 2. mootdx 财务快照 ============
print("\n" + "=" * 70)
print("【2】mootdx 财务快照（最近季报）")
print("=" * 70)
try:
    from mootdx.quotes import Quotes
    client = Quotes.factory(market='std')
    fin = client.finance(symbol=CODE)
    if fin:
        for k, v in fin.items():
            print(f"  {k}: {v}")
except Exception as e:
    print(f"  mootdx 失败: {e}")

# ============ 3. mootdx F10 公司概况 ============
print("\n" + "=" * 70)
print("【3】mootdx F10 公司概况")
print("=" * 70)
try:
    for cat in ["公司概况", "财务分析", "股东研究"]:
        text = client.F10(symbol=CODE, name=cat)
        print(f"\n--- {cat} ---")
        print((text or "(空)")[:1500])
except Exception as e:
    print(f"  F10 失败: {e}")

# ============ 4. 东财个股基本信息 ============
print("\n" + "=" * 70)
print("【4】东财个股基本信息")
print("=" * 70)
def eastmoney_stock_info(code):
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43,f162,f163,f167,f173,f183,f186,f187,f188",
        "secid": f"{market_code}.{code}",
    }
    headers = {"User-Agent": UA}
    r = em_get(url, params=params, headers=headers, timeout=10)
    return r.json().get("data", {})
info = eastmoney_stock_info(CODE)
for k, v in info.items():
    print(f"  {k}: {v}")

# ============ 5. 所属板块/概念 ============
print("\n" + "=" * 70)
print("【5】所属板块/概念（东财 slist）")
print("=" * 70)
def eastmoney_concept_blocks(code):
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
    return {"total": len(boards), "boards": boards,
            "concept_tags": [b["name"] for b in boards]}

blocks = eastmoney_concept_blocks(CODE)
print(f"  共 {blocks['total']} 个板块")
for b in blocks["boards"][:20]:
    print(f"  - {b['name']} (涨跌幅:{b['change_pct']}% 龙头:{b['lead_stock']})")

# ============ 6. 研报列表 ============
print("\n" + "=" * 70)
print("【6】近 1 年研报（东财 reportapi）")
print("=" * 70)
def eastmoney_reports(code, max_pages=2):
    REPORT_API = "https://reportapi.eastmoney.com/report/list"
    all_records = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            "endTime": datetime.now().strftime("%Y-%m-%d"),
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = em_get(REPORT_API, params=params,
                   headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows: break
        all_records.extend(rows)
    return all_records

reports = eastmoney_reports(CODE)
print(f"  共 {len(reports)} 篇研报")
for r in reports[:10]:
    print(f"  {r.get('publishDate','')[:10]} | {r.get('orgSName',''):<10} | "
          f"{r.get('emRatingName',''):<4} | {r.get('title','')[:50]} | "
          f"EPS预测:今年{r.get('predictThisYearEps','')} "
          f"明年{r.get('predictNextYearEps','')}")

# ============ 7. 同花顺一致预期 EPS ============
print("\n" + "=" * 70)
print("【7】同花顺一致预期 EPS")
print("=" * 70)
def ths_eps_forecast(code):
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    return dfs[0] if dfs else pd.DataFrame()

try:
    df_eps = ths_eps_forecast(CODE)
    print(df_eps.to_string())
except Exception as e:
    print(f"  失败: {e}")

# ============ 8. 资金流向（120 日）============
print("\n" + "=" * 70)
print("【8】个股资金流（120 日）")
print("=" * 70)
def stock_fund_flow_120d(code):
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
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

flow_120 = stock_fund_flow_120d(CODE)
print(f"  共 {len(flow_120)} 个交易日")
if flow_120:
    for d in flow_120[-10:]:
        print(f"  {d['date']} 主力:{d['main_net']/1e4:>10.0f}万 超大单:{d['super_net']/1e4:>10.0f}万 "
              f"大单:{d['large_net']/1e4:>10.0f}万 中单:{d['mid_net']/1e4:>10.0f}万 小单:{d['small_net']/1e4:>10.0f}万")
    # 统计
    for days, label in [(5, "近5日"), (10, "近10日"), (20, "近20日"), (60, "近60日")]:
        recent = flow_120[-days:]
        if recent:
            total_main = sum(d["main_net"] for d in recent)
            total_super = sum(d["super_net"] for d in recent)
            print(f"  {label}: 主力累计 {total_main/1e8:.2f}亿 超大单累计 {total_super/1e8:.2f}亿")

# ============ 9. 融资融券 ============
print("\n" + "=" * 70)
print("【9】融资融券（近 30 日）")
print("=" * 70)
def margin_trading(code, page_size=30):
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
            "rzrqye": row.get("RZRQYE", 0),
        })
    return rows

margin = margin_trading(CODE)
print(f"  共 {len(margin)} 条")
for d in margin[:10]:
    print(f"  {d['date']} 融资余额:{d['rzye']/1e8:.2f}亿 融券余额:{d['rqye']/1e8:.2f}亿 "
          f"合计:{d['rzrqye']/1e8:.2f}亿")

# ============ 10. 股东户数 ============
print("\n" + "=" * 70)
print("【10】股东户数变化")
print("=" * 70)
def holder_num_change(code, page_size=10):
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

holders = holder_num_change(CODE)
print(f"  共 {len(holders)} 期")
for d in holders:
    print(f"  {d['date']} 股东数:{d['holder_num']} 环比:{d['change_ratio']}% "
          f"户均持股:{d['avg_shares']}")

# ============ 11. 大宗交易 ============
print("\n" + "=" * 70)
print("【11】大宗交易（近 3 月）")
print("=" * 70)
def block_trade(code, page_size=20):
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        close = row.get("CLOSE_PRICE") or 0
        deal_price = row.get("DEAL_PRICE") or 0
        premium = ((deal_price / close - 1) * 100) if close else 0
        rows.append({
            "date": str(row.get("TRADE_DATE", ""))[:10],
            "price": deal_price,
            "close": close,
            "premium_pct": round(premium, 2),
            "vol": row.get("DEAL_VOLUME", 0),
            "amount": row.get("DEAL_AMT", 0),
            "buyer": row.get("BUYER_NAME", ""),
            "seller": row.get("SELLER_NAME", ""),
        })
    return rows

bt = block_trade(CODE)
print(f"  共 {len(bt)} 笔")
for d in bt[:10]:
    print(f"  {d['date']} 价格:{d['price']} 收盘:{d['close']} 溢价:{d['premium_pct']}% "
          f"成交量:{d['vol']} 金额:{d['amount']/1e4:.0f}万 买方:{d['buyer']}")

# ============ 12. 分红送转 ============
print("\n" + "=" * 70)
print("【12】分红送转历史")
print("=" * 70)
def dividend_history(code, page_size=20):
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": row.get("PRETAX_BONUS_RMB", 0),
            "transfer_ratio": row.get("TRANSFER_RATIO", 0),
            "bonus_ratio": row.get("BONUS_RATIO", 0),
            "plan": row.get("ASSIGN_PROGRESS", ""),
        })
    return rows

divs = dividend_history(CODE)
print(f"  共 {len(divs)} 次")
for d in divs[:10]:
    print(f"  {d['date']} 每股派息:{d['bonus_rmb']}元 转增:{d['transfer_ratio']} "
          f"送股:{d['bonus_ratio']} 进度:{d['plan']}")

# ============ 13. 限售解禁 ============
print("\n" + "=" * 70)
print("【13】限售解禁日历")
print("=" * 70)
def lockup_expiry(code, forward_days=90):
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=forward_days)).strftime("%Y-%m-%d")
    history = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=10,
        sort_columns="FREE_DATE", sort_types="-1",
    )
    upcoming = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")(FREE_DATE>="{today}")(FREE_DATE<="{end_date}")',
        page_size=20,
        sort_columns="FREE_DATE", sort_types="1",
    )
    return history, upcoming

hist, upco = lockup_expiry(CODE)
print(f"  历史解禁 {len(hist)} 批:")
for h in hist[:5]:
    print(f"    {str(h.get('FREE_DATE',''))[:10]} {h.get('LIMITED_STOCK_TYPE','')} "
          f"数量:{h.get('FREE_SHARES_NUM',0)} 占比:{h.get('FREE_RATIO',0)}")
print(f"  未来 90 天待解禁 {len(upco)} 批:")
for u in upco:
    print(f"    {str(u.get('FREE_DATE',''))[:10]} {u.get('LIMITED_STOCK_TYPE','')} "
          f"数量:{u.get('FREE_SHARES_NUM',0)} 占比:{u.get('FREE_RATIO',0)}")

# ============ 14. 龙虎榜 ============
print("\n" + "=" * 70)
print("【14】龙虎榜（近 60 日）")
print("=" * 70)
def dragon_tiger_board(code, look_back=60):
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=look_back)).strftime("%Y-%m-%d")
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{today}')(SECURITY_CODE=\"{code}\")",
        page_size=50,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    return data

dtb = dragon_tiger_board(CODE)
print(f"  近 60 日上龙虎榜 {len(dtb)} 次")
for r in dtb[:5]:
    print(f"  {str(r.get('TRADE_DATE',''))[:10]} 原因:{r.get('EXPLANATION','')} "
          f"净买:{(r.get('BILLBOARD_NET_AMT') or 0)/1e4:.0f}万 "
          f"换手:{r.get('TURNOVERRATE',0)}%")

# ============ 15. 个股新闻 ============
print("\n" + "=" * 70)
print("【15】个股新闻（东财）")
print("=" * 70)
def eastmoney_stock_news(code, page_size=10):
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "", "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                  "pageIndex": 1, "pageSize": page_size, "preTag": "", "postTag": ""}},
    }, separators=(',', ':'))
    params = {"cb": cb, "param": inner_params}
    headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}
    r = em_get(url, params=params, headers=headers, timeout=15)
    text = r.text
    try:
        json_str = text[text.index("(") + 1 : text.rindex(")")]
        d = json.loads(json_str)
    except Exception:
        return []
    articles = d.get("result", {}).get("cmsArticleWebOld", []) or []
    rows = []
    for a in articles:
        rows.append({
            "title": re.sub(r'<[^>]+>', '', a.get("title", "")),
            "time": a.get("date", ""),
            "source": a.get("mediaName", ""),
        })
    return rows

news = eastmoney_stock_news(CODE)
print(f"  共 {len(news)} 条")
for n in news[:8]:
    print(f"  {n['time']} | {n['source']} | {n['title'][:60]}")

# ============ 16. 新浪利润表 ============
print("\n" + "=" * 70)
print("【16】新浪利润表（最近 4 期）")
print("=" * 70)
def sina_financial_report(code, report_type="lrb", num=4):
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code, "source": report_type,
        "type": "0", "page": "1", "num": str(num),
    }
    headers = {"User-Agent": UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    report_list = r.json().get("result", {}).get("data", {}).get("report_list", {}) or {}
    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in obj.get("data", []) or []:
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None: continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""):
                rec[title + "_同比"] = tongbi
        rows.append(rec)
    return rows

try:
    lrb = sina_financial_report(CODE, "lrb", 4)
    for item in lrb:
        print(f"\n  报告期: {item.get('报告期')}")
        for k in ["营业总收入", "营业总收入_同比", "归母净利润", "归母净利润_同比",
                  "扣非净利润", "扣非净利润_同比", "每股收益", "毛利率", "净利率"]:
            if k in item:
                print(f"    {k}: {item[k]}")
except Exception as e:
    print(f"  失败: {e}")

print("\n" + "=" * 70)
print("数据拉取完成")
print("=" * 70)
