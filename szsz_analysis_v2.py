"""神州数码(000034) 完整分析 - 带容错和代理支持"""
import urllib.request
import requests
import pandas as pd
from io import StringIO
import json
import time
import random
import re
from datetime import datetime, timedelta

CODE = "002156"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 使用代理访问中国站点
PROXY = "http://127.0.0.1:18080"
proxies = {"http": PROXY, "https": PROXY}

# 东财限流
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url, params=None, headers=None, timeout=15):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, proxies=proxies)
    except Exception as e:
        print(f"  [WARN] {str(e)[:80]}")
        return None

def eastmoney_datacenter(report_name, filter_str="", page_size=50, sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": "ALL",
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get("https://datacenter-web.eastmoney.com/api/data/v1/get", params=params, timeout=15)
    if r and r.status_code == 200:
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    return []

# ============ 1. 腾讯实时行情 ============
print("=" * 70)
print("【1】实时行情 & 估值（腾讯财经）")
print("=" * 70)
def tencent_quote(codes):
    prefixed = [f"sh{c}" if c.startswith(("6","9")) else f"bj{c}" if c.startswith("8") else f"sz{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
print(f"股票名称: {q['name']}")
print(f"当前价格: {q['price']}元")
print(f"涨跌幅: {q['change_pct']}%")
print(f"今开: {q.get('open', 'N/A')}")
print(f"最高: {q['high']} 最低: {q['low']}")
print(f"PE(TTM): {q['pe_ttm']}")
print(f"PE(静): {q['pe_static']}")
print(f"PB: {q['pb']}")
print(f"总市值: {q['mcap_yi']}亿元")
print(f"流通市值: {q['float_mcap_yi']}亿元")
print(f"换手率: {q['turnover_pct']}%")
print(f"成交额: {q['amount_wan']}万元")
print(f"量比: {q['vol_ratio']}")
print(f"涨停价: {q['limit_up']} 跌停价: {q['limit_down']}")

# ============ 2. 东财个股基本信息 ============
print("\n" + "=" * 70)
print("【2】东财个股基本信息")
print("=" * 70)
try:
    market_code = 1 if CODE.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43,f162,f163,f167,f173",
        "secid": f"{market_code}.{CODE}",
    }
    r = em_get(url, params=params, timeout=10)
    if r and r.status_code == 200:
        info = r.json().get("data", {})
        print(f"行业: {info.get('f127', 'N/A')}")
        print(f"总股本: {info.get('f84', 0)}")
        print(f"流通股: {info.get('f85', 0)}")
        print(f"上市日期: {info.get('f189', 'N/A')}")
    else:
        print("  [INFO] 东财接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 3. 所属板块/概念 ============
print("\n" + "=" * 70)
print("【3】所属板块/概念（东财）")
print("=" * 70)
try:
    market_code = 1 if CODE.startswith("6") else 0
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{market_code}.{CODE}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    r = em_get("https://push2.eastmoney.com/api/qt/slist/get",
               params=params, headers={"Referer": "https://quote.eastmoney.com/"}, timeout=15)
    if r and r.status_code == 200:
        d = r.json()
        diff = (d.get("data") or {}).get("diff") or {}
        items = diff.values() if isinstance(diff, dict) else diff
        boards = []
        for it in items:
            boards.append({
                "name": it.get("f14", ""),
                "change_pct": it.get("f3", ""),
                "lead_stock": it.get("f128", ""),
            })
        print(f"共 {len(boards)} 个板块")
        for b in boards[:15]:
            print(f"  - {b['name']} (涨跌:{b['change_pct']}% 龙头:{b['lead_stock']})")
    else:
        print("  [INFO] 东财接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 4. 研报列表 ============
print("\n" + "=" * 70)
print("【4】近1年研报（东财）")
print("=" * 70)
try:
    REPORT_API = "https://reportapi.eastmoney.com/report/list"
    params = {
        "industryCode": "*", "pageSize": "50", "industry": "*",
        "rating": "*", "ratingChange": "*",
        "beginTime": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
        "endTime": datetime.now().strftime("%Y-%m-%d"),
        "pageNo": "1", "fields": "", "qType": "0",
        "orgCode": "", "code": CODE, "rcode": "",
        "p": "1", "pageNum": "1", "pageNumber": "1",
    }
    r = em_get(REPORT_API, params=params, headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
    if r and r.status_code == 200:
        d = r.json()
        rows = d.get("data") or []
        print(f"共 {len(rows)} 篇研报")
        for rec in rows[:10]:
            print(f"  {rec.get('publishDate','')[:10]} | {rec.get('orgSName',''):<10} | "
                  f"{rec.get('emRatingName',''):<4} | {rec.get('title','')[:50]}")
            eps_info = f"今年EPS:{rec.get('predictThisYearEps','')} 明年:{rec.get('predictNextYearEps','')}"
            print(f"    {eps_info}")
    else:
        print("  [INFO] 东财接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 5. 资金流向（120日）============
print("\n" + "=" * 70)
print("【5】个股资金流（120日，东财）")
print("=" * 70)
try:
    market_code = 1 if CODE.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{CODE}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    r = em_get(url, params=params, headers={"Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}, timeout=15)
    if r and r.status_code == 200:
        d = r.json()
        klines = d.get("data", {}).get("klines", [])
        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({
                    "date": parts[0],
                    "main_net": float(parts[1]) if parts[1] != "-" else 0,
                    "super_net": float(parts[5]) if parts[5] != "-" else 0,
                })
        print(f"共 {len(rows)} 个交易日")
        if rows:
            for d in rows[-5:]:
                print(f"  {d['date']} 主力:{d['main_net']/1e4:>10.0f}万 超大单:{d['super_net']/1e4:>10.0f}万")
            for days, label in [(5, "近5日"), (10, "近10日"), (20, "近20日")]:
                recent = rows[-days:]
                if recent:
                    total_main = sum(d["main_net"] for d in recent)
                    print(f"  {label}: 主力累计 {total_main/1e8:.2f}亿")
    else:
        print("  [INFO] 东财接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 6. 融资融券 ============
print("\n" + "=" * 70)
print("【6】融资融券（东财）")
print("=" * 70)
try:
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{CODE}")',
        page_size=10,
        sort_columns="DATE", sort_types="-1",
    )
    if data:
        print(f"共 {len(data)} 条")
        for row in data[:5]:
            rzye = row.get("RZYE", 0)
            rqye = row.get("RQYE", 0)
            print(f"  {str(row.get('DATE',''))[:10]} 融资余额:{rzye/1e8:.2f}亿 融券余额:{rqye/1e8:.2f}亿")
    else:
        print("  [INFO] 无数据或接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 7. 股东户数 ============
print("\n" + "=" * 70)
print("【7】股东户数变化（东财）")
print("=" * 70)
try:
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{CODE}")',
        page_size=10,
        sort_columns="END_DATE", sort_types="-1",
    )
    if data:
        print(f"共 {len(data)} 期")
        for row in data:
            print(f"  {str(row.get('END_DATE',''))[:10]} 股东数:{row.get('HOLDER_NUM',0)} "
                  f"环比:{row.get('HOLDER_NUM_RATIO',0)}% 户均:{row.get('AVG_FREE_SHARES',0)}")
    else:
        print("  [INFO] 无数据或接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 8. 大宗交易 ============
print("\n" + "=" * 70)
print("【8】大宗交易（东财）")
print("=" * 70)
try:
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{CODE}")',
        page_size=10,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    if data:
        print(f"共 {len(data)} 笔")
        for row in data[:5]:
            close = row.get("CLOSE_PRICE") or 0
            deal_price = row.get("DEAL_PRICE") or 0
            premium = ((deal_price / close - 1) * 100) if close else 0
            print(f"  {str(row.get('TRADE_DATE',''))[:10]} 价格:{deal_price} 收盘:{close} "
                  f"溢价:{premium:.2f}% 金额:{(row.get('DEAL_AMT',0) or 0)/1e4:.0f}万")
    else:
        print("  [INFO] 无数据或接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 9. 分红送转 ============
print("\n" + "=" * 70)
print("【9】分红送转历史（东财）")
print("=" * 70)
try:
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{CODE}")',
        page_size=10,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    if data:
        print(f"共 {len(data)} 次")
        for row in data[:5]:
            print(f"  {str(row.get('EX_DIVIDEND_DATE',''))[:10]} 每股派息:{row.get('PRETAX_BONUS_RMB',0)}元 "
                  f"转增:{row.get('TRANSFER_RATIO',0)} 送股:{row.get('BONUS_RATIO',0)}")
    else:
        print("  [INFO] 无数据或接口不可用")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 10. 限售解禁 ============
print("\n" + "=" * 70)
print("【10】限售解禁日历（东财）")
print("=" * 70)
try:
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    
    hist = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{CODE}")',
        page_size=5,
        sort_columns="FREE_DATE", sort_types="-1",
    )
    upco = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{CODE}")(FREE_DATE>="{today}")(FREE_DATE<="{end_date}")',
        page_size=10,
        sort_columns="FREE_DATE", sort_types="1",
    )
    
    print(f"历史解禁 {len(hist)} 批:")
    for h in hist[:3]:
        print(f"  {str(h.get('FREE_DATE',''))[:10]} {h.get('LIMITED_STOCK_TYPE','')} "
              f"数量:{h.get('FREE_SHARES_NUM',0)} 占比:{h.get('FREE_RATIO',0)}")
    print(f"未来90天待解禁 {len(upco)} 批:")
    for u in upco:
        print(f"  {str(u.get('FREE_DATE',''))[:10]} {u.get('LIMITED_STOCK_TYPE','')} "
              f"数量:{u.get('FREE_SHARES_NUM',0)} 占比:{u.get('FREE_RATIO',0)}")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 11. 龙虎榜 ============
print("\n" + "=" * 70)
print("【11】龙虎榜（近60日，东财）")
print("=" * 70)
try:
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{today}')(SECURITY_CODE=\"{CODE}\")",
        page_size=10,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    if data:
        print(f"近60日上龙虎榜 {len(data)} 次")
        for r in data[:3]:
            print(f"  {str(r.get('TRADE_DATE',''))[:10]} 原因:{r.get('EXPLANATION','')} "
                  f"净买:{(r.get('BILLBOARD_NET_AMT') or 0)/1e4:.0f}万")
    else:
        print("  近60日未上龙虎榜")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

# ============ 12. 新浪利润表 ============
print("\n" + "=" * 70)
print("【12】新浪利润表（最近4期）")
print("=" * 70)
try:
    prefix = "sh" if CODE.startswith("6") else "sz"
    paper_code = f"{prefix}{CODE}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code, "source": "lrb",
        "type": "0", "page": "1", "num": "4",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15, proxies=proxies)
    report_list = r.json().get("result", {}).get("data", {}).get("report_list", {}) or {}
    
    for period in sorted(report_list.keys(), reverse=True)[:4]:
        obj = report_list[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in obj.get("data", []) or []:
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None: continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""):
                rec[title + "_同比"] = tongbi
        
        print(f"\n  报告期: {rec.get('报告期')}")
        for k in ["营业总收入", "营业总收入_同比", "归母净利润", "归母净利润_同比",
                  "扣非净利润", "扣非净利润_同比", "每股收益"]:
            if k in rec:
                print(f"    {k}: {rec[k]}")
except Exception as e:
    print(f"  [ERROR] {str(e)[:80]}")

print("\n" + "=" * 70)
print("数据拉取完成")
print("=" * 70)
