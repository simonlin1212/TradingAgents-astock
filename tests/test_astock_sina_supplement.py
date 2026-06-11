from pathlib import Path

import pandas as pd


def _mootdx_bars_until_0610():
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-06-10 15:00:00"]),
            "open": [50.8],
            "high": [55.8],
            "low": [50.5],
            "close": [53.45],
            "volume": [149046.0],
        }
    ).set_index("datetime")


def _sina_bars_until_0611():
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-06-10", "2026-06-11"]),
            "Open": [50.8, 53.29],
            "High": [55.8, 58.8],
            "Low": [50.5, 52.96],
            "Close": [53.45, 57.47],
            "Volume": [149046.0, 205219.0],
        }
    )


class _FakeMootdxClient:
    def bars(self, symbol, category, offset):
        return _mootdx_bars_until_0610()


def test_get_stock_data_supplements_stale_mootdx_with_sina(monkeypatch):
    from tradingagents.dataflows import a_stock

    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda: _FakeMootdxClient())
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", lambda *args: _sina_bars_until_0611())

    result = a_stock.get_stock_data("000628", "2026-06-10", "2026-06-11")

    assert "2026-06-11,53.29,58.8,52.96,57.47" in result
    assert "# Total records: 2" in result


def test_load_ohlcv_astock_supplements_fresh_cache_with_sina(tmp_path, monkeypatch):
    from tradingagents.dataflows import a_stock
    from tradingagents.dataflows import config as dataflow_config

    cache_file = Path(tmp_path) / "000628-astock-daily.csv"
    _mootdx_bars_until_0610().reset_index().rename(
        columns={
            "datetime": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    ).to_csv(cache_file, index=False)

    monkeypatch.setattr(dataflow_config, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda: _FakeMootdxClient())
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", lambda *args: _sina_bars_until_0611())

    result = a_stock._load_ohlcv_astock("000628", "2026-06-11")

    assert result["Date"].max() == pd.Timestamp("2026-06-11")
    assert result.loc[result["Date"] == pd.Timestamp("2026-06-11"), "Close"].item() == 57.47
