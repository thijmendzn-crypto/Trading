"""
Technical indicator calculations.
All functions take a DataFrame with OHLCV columns and return a Series or float.
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = atr(df, period)

    up_move = high.diff()
    down_move = -low.diff()

    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    pos_dm_s = pd.Series(pos_dm, index=df.index).ewm(span=period, adjust=False).mean()
    neg_dm_s = pd.Series(neg_dm, index=df.index).ewm(span=period, adjust=False).mean()

    pdi = 100 * pos_dm_s / tr
    ndi = 100 * neg_dm_s / tr

    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP for intraday use. Groups by date."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]

    cum_vol = vol.groupby(df.index.date).cumsum()
    cum_tp_vol = (typical * vol).groupby(df.index.date).cumsum()

    return cum_tp_vol / cum_vol


def volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Current volume vs SMA of volume."""
    avg_vol = sma(df["volume"], period)
    return df["volume"] / avg_vol.replace(0, np.nan)
