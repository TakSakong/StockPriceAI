import pandas as pd


def test_calculate_rsi_returns_valid_range():
    from app.features import calculate_rsi

    prices = pd.Series([1.0, 2.0, 1.5, 2.5, 3.0, 2.0, 2.2, 2.8, 3.1, 2.9, 3.5, 3.2, 3.8, 4.0, 4.5])
    rsi = calculate_rsi(prices, window=5)

    assert len(rsi) == len(prices)
    assert rsi.iloc[0] == 50.0
    assert rsi.dropna().between(0, 100).all()


def test_calculate_macd_shapes_match_input():
    from app.features import calculate_macd

    prices = pd.Series([1.0, 1.1, 1.2, 1.15, 1.18, 1.21, 1.23, 1.25, 1.22, 1.28, 1.31, 1.29, 1.35])
    macd, signal, hist = calculate_macd(prices)

    assert len(macd) == len(prices)
    assert len(signal) == len(prices)
    assert len(hist) == len(prices)
    assert (macd - signal).equals(hist)


def test_calculate_bollinger_bands_returns_three_series():
    from app.features import calculate_bollinger_bands

    prices = pd.Series([10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.0, 11.4, 11.8, 12.0])
    upper, middle, lower = calculate_bollinger_bands(prices, window=3)

    assert len(upper) == len(prices)
    assert len(middle) == len(prices)
    assert len(lower) == len(prices)
    assert (upper >= middle).all()
    assert (middle >= lower).all()


def test_add_all_indicators_includes_target_and_basic_columns():
    from app.features import add_all_indicators

    df = pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "High": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            "Low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
            "Close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "Volume": [1000, 1200, 1100, 1300, 1400, 1500, 1600, 1700, 1800, 1900],
        }
    )
    result = add_all_indicators(df)

    assert "Target" in result.columns
    assert "RSI14" in result.columns
    assert "MACD" in result.columns
    assert "BB_Position" in result.columns
    assert result["Target"].iloc[-1] == 0
    assert result["Target"].iloc[0] in (0, 1)
