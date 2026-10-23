#!/usr/bin/env python3
"""Small local web server and quote proxy for Stockup (Python standard library only)."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timezone
import json
import re
import ssl
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
try:
    import certifi
    TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    TLS_CONTEXT = ssl.create_default_context()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/news":
            query = parse_qs(parsed.query)
            ticker = query.get("ticker", [""])[0].strip().upper()
            name = query.get("name", [""])[0].strip()
            if not re.fullmatch(r"[A-Z0-9^._=-]{1,24}", ticker) or not name:
                return self.send_json(400, {"error": "股票代码或名称无效"})
            params = urlencode({"q": f'"{ticker}" {name}', "hl": "zh-CN", "gl": "SG", "ceid": "SG:zh-Hans"})
            request = Request(f"https://news.google.com/rss/search?{params}", headers={"User-Agent": "Mozilla/5.0 Stockup personal portfolio tracker"})
            try:
                with urlopen(request, timeout=15, context=TLS_CONTEXT) as response:
                    root = ET.fromstring(response.read())
                items = []
                for item in root.findall("./channel/item")[:5]:
                    get = lambda key: (item.findtext(key) or "").strip()
                    items.append({"stock": f"{name} ({ticker})", "title": get("title"), "link": get("link"), "description": get("description"), "date": get("pubDate")})
                return self.send_json(200, {"items": items, "source": "Google News"})
            except (HTTPError, URLError, TimeoutError, ET.ParseError) as error:
                return self.send_json(502, {"error": f"新闻服务暂时不可用：{error}"})

        if parsed.path != "/api/quote":
            return super().do_GET()

        ticker = parse_qs(parsed.query).get("ticker", [""])[0].strip().upper()
        if not re.fullmatch(r"[A-Z0-9^._=-]{1,24}", ticker):
            return self.send_json(400, {"error": "股票代码格式无效"})

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?range=5d&interval=1d"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 Stockup personal portfolio tracker"})
        try:
            with urlopen(request, timeout=12, context=TLS_CONTEXT) as response:
                payload = json.load(response)
            chart = payload.get("chart", {})
            if chart.get("error"):
                return self.send_json(404, {"error": "没有找到该股票报价，请检查代码及交易所后缀"})
            result = (chart.get("result") or [None])[0]
            meta = result.get("meta", {}) if result else {}
            price = meta.get("regularMarketPrice")
            timestamp = meta.get("regularMarketTime")
            if not price and result:
                quotes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                timestamps = result.get("timestamp", [])
                valid = [(t, p) for t, p in zip(timestamps, quotes) if p is not None]
                if valid:
                    timestamp, price = valid[-1]
            if not price:
                return self.send_json(404, {"error": "暂时没有可用报价，请稍后重试"})
            stamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else datetime.now(timezone.utc).isoformat()
            return self.send_json(200, {
                "ticker": ticker,
                "name": meta.get("longName") or meta.get("shortName") or ticker,
                "price": price,
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName"),
                "timestamp": stamp,
                "source": "Yahoo Finance",
            })
        except HTTPError as error:
            return self.send_json(502, {"error": f"报价来源返回 HTTP {error.code}"})
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            return self.send_json(502, {"error": f"报价暂时不可用：{error}"})


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)
    print(f"Stockup running at http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, Handler).serve_forever()
