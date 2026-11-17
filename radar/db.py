import json
import pathlib
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices(ticker TEXT, date TEXT, close REAL, volume REAL, PRIMARY KEY(ticker,date));
CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY, date TEXT, source TEXT, title TEXT, text TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS scores(id TEXT PRIMARY KEY, date TEXT, source TEXT, title TEXT, cats TEXT,
    polarity REAL, tickers TEXT, techs TEXT, vol REAL DEFAULT 1);
CREATE TABLE IF NOT EXISTS gdelt(kind TEXT, key TEXT, date TEXT, vol REAL, tone REAL, PRIMARY KEY(kind,key,date));
CREATE TABLE IF NOT EXISTS earnings(ticker TEXT, date TEXT, eps_est REAL, eps_act REAL, surprise REAL, PRIMARY KEY(ticker,date));
CREATE TABLE IF NOT EXISTS earnings_fetch(ticker TEXT PRIMARY KEY, fetched TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS macro(symbol TEXT, date TEXT, close REAL, PRIMARY KEY(symbol,date));
CREATE TABLE IF NOT EXISTS watch_log(run_date TEXT, rank INTEGER, ticker TEXT, p5 REAL, resolved INTEGER DEFAULT 0,
    excess REAL, beat INTEGER, PRIMARY KEY(run_date,rank));
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sec_cik(ticker TEXT PRIMARY KEY, cik INTEGER);
CREATE TABLE IF NOT EXISTS fund_fetch(ticker TEXT PRIMARY KEY, fetched TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS fundamentals(ticker TEXT, concept TEXT, start TEXT, end TEXT, filed TEXT, form TEXT, val REAL);
CREATE INDEX IF NOT EXISTS i_fund ON fundamentals(ticker);
CREATE TABLE IF NOT EXISTS predictions(run_date TEXT, ticker TEXT, horizon INTEGER, p_up REAL, p_raw REAL,
    driver TEXT, kind TEXT, resolved INTEGER DEFAULT 0, realized REAL, hit INTEGER,
    PRIMARY KEY(run_date,ticker,horizon));
CREATE TABLE IF NOT EXISTS weights(kind TEXT, key TEXT, value REAL, n REAL, hits REAL, z REAL,
    PRIMARY KEY(kind,key));
"""


def connect(cfg, root="."):
    """Une base par mode : la démo ne peut jamais contaminer la base live."""
    path = pathlib.Path(root) / cfg["db_path"]
    if cfg["mode"] == "demo":
        path = path.with_name(path.stem + "_demo" + path.suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def get_weights(con, kind):
    return {k: v for k, v in con.execute("SELECT key,value FROM weights WHERE kind=?", (kind,))}


def meta_get(con, key, default=None):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def meta_set(con, key, value):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False, default=float)))
    con.commit()
