"""CTC Market Bot - Discord bot for daily movers, price alerts and a shared watchlist."""
import asyncio
import json
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
import yfinance as yf
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
DATA_FILE = Path(os.getenv("DATA_FILE", "data.json"))
ET = ZoneInfo("America/New_York")

# ---------- storage ----------
def load():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"watchlist": [], "alerts": []}

def save(d):
    DATA_FILE.write_text(json.dumps(d, indent=2))

data = load()

# ---------- market data ----------
def _quote(ticker):
    hist = yf.Ticker(ticker).history(period="5d")
    if len(hist) < 2:
        return None
    last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
    return {"ticker": ticker.upper(), "price": float(last), "chg": float((last / prev - 1) * 100)}

async def quote(ticker):
    return await asyncio.to_thread(_quote, ticker)

def fmt(q):
    arrow = "🟢" if q["chg"] >= 0 else "🔴"
    return f"{arrow} **{q['ticker']}** ${q['price']:.2f} ({q['chg']:+.2f}%)"

# ---------- bot ----------
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    await bot.tree.sync()
    daily_movers.start()
    check_alerts.start()
    print(f"Logged in as {bot.user}")

@bot.tree.command(description="Get a stock price")
async def price(inter: discord.Interaction, ticker: str):
    await inter.response.defer()
    q = await quote(ticker)
    await inter.followup.send(fmt(q) if q else f"Couldn't find `{ticker}`.")

watch = app_commands.Group(name="watch", description="Manage the CTC watchlist")

@watch.command(description="Add a ticker")
async def add(inter: discord.Interaction, ticker: str):
    t = ticker.upper()
    if t not in data["watchlist"]:
        data["watchlist"].append(t); save(data)
    await inter.response.send_message(f"Added **{t}**.")

@watch.command(description="Remove a ticker")
async def remove(inter: discord.Interaction, ticker: str):
    t = ticker.upper()
    if t in data["watchlist"]:
        data["watchlist"].remove(t); save(data)
    await inter.response.send_message(f"Removed **{t}**.")

@watch.command(name="list", description="Show watchlist with prices")
async def list_(inter: discord.Interaction):
    await inter.response.defer()
    if not data["watchlist"]:
        return await inter.followup.send("Watchlist is empty.")
    qs = await asyncio.gather(*(quote(t) for t in data["watchlist"]))
    await inter.followup.send("\n".join(fmt(q) for q in qs if q))

bot.tree.add_command(watch)

@bot.tree.command(description="Set a price alert")
@app_commands.choices(direction=[
    app_commands.Choice(name="above", value="above"),
    app_commands.Choice(name="below", value="below")])
async def alert(inter: discord.Interaction, ticker: str, direction: app_commands.Choice[str], target: float):
    data["alerts"].append({"ticker": ticker.upper(), "dir": direction.value,
                           "target": target, "user": inter.user.id})
    save(data)
    await inter.response.send_message(f"Alert set: **{ticker.upper()}** {direction.value} ${target:.2f}")

@bot.tree.command(description="List active alerts")
async def alerts(inter: discord.Interaction):
    if not data["alerts"]:
        return await inter.response.send_message("No active alerts.")
    lines = [f"{i+1}. {a['ticker']} {a['dir']} ${a['target']:.2f}" for i, a in enumerate(data["alerts"])]
    await inter.response.send_message("\n".join(lines))

# ---------- scheduled jobs ----------
@tasks.loop(time=time(16, 15, tzinfo=ET))
async def daily_movers():
    ch = bot.get_channel(CHANNEL_ID)
    if not ch or not data["watchlist"]:
        return
    qs = [q for q in await asyncio.gather(*(quote(t) for t in data["watchlist"])) if q]
    if not qs:
        return
    qs.sort(key=lambda q: q["chg"], reverse=True)
    embed = discord.Embed(title="📊 CTC Daily Close", color=0x2B6CB0)
    embed.add_field(name="Top gainers", value="\n".join(fmt(q) for q in qs[:3]), inline=False)
    embed.add_field(name="Top losers", value="\n".join(fmt(q) for q in qs[-3:][::-1]), inline=False)
    await ch.send(embed=embed)

@tasks.loop(minutes=5)
async def check_alerts():
    ch = bot.get_channel(CHANNEL_ID)
    if not ch or not data["alerts"]:
        return
    fired = []
    for a in data["alerts"]:
        q = await quote(a["ticker"])
        if q and ((a["dir"] == "above" and q["price"] >= a["target"]) or
                  (a["dir"] == "below" and q["price"] <= a["target"])):
            await ch.send(f"🔔 <@{a['user']}> {fmt(q)} hit your target ${a['target']:.2f}")
            fired.append(a)
    if fired:
        data["alerts"] = [a for a in data["alerts"] if a not in fired]
        save(data)

if __name__ == "__main__":
    bot.run(TOKEN)
