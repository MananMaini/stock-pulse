"""StockPulse - real-time stock watchlist with per-stock pop-up alerts."""
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="StockPulse")
app.mount("/static", StaticFiles(directory="static"), name="static")
pool = ThreadPoolExecutor(max_workers=8)


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    try:
        res = yf.Search(q, max_results=8).quotes
    except Exception:
        return []
    return [
        {"symbol": r["symbol"], "name": r.get("shortname") or r.get("longname") or "",
         "exchange": r.get("exchDisp", "")}
        for r in res if r.get("quoteType") in ("EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY")
    ]


def _quote(sym: str):
    try:
        t = yf.Ticker(sym)
        fi = t.fast_info
        price, prev = float(fi["lastPrice"]), float(fi["previousClose"])
        intraday = t.history(period="1d", interval="5m")["Close"].dropna().round(2).tolist()
        return {
            "symbol": sym, "price": round(price, 2), "prevClose": round(prev, 2),
            "change": round(price - prev, 2), "changePct": round((price / prev - 1) * 100, 2),
            "dayHigh": round(float(fi["dayHigh"]), 2), "dayLow": round(float(fi["dayLow"]), 2),
            "currency": fi.get("currency", "USD"), "spark": intraday[-78:],
        }
    except Exception as e:
        return {"symbol": sym, "error": str(e)}


@app.get("/api/quotes")
def quotes(symbols: str):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:25]
    return list(pool.map(_quote, syms))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
