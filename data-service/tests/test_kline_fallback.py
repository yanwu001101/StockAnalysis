import json

import pandas as pd

import eastmoney


def test_validate_kline_rejects_invalid_ohlc():
    df = pd.DataFrame([{
        "日期": "2026-08-19", "开盘": 10, "收盘": 11,
        "最高": 9, "最低": 8, "成交量": 100,
    }])
    assert eastmoney._validate_kline(df, 1).empty


def test_ths_payload_mapping_matches_documented_order():
    payload = {"data": "20260818,10,12,9,11,1000,11000;20260819,11,13,10,12,1200,14400"}
    text = "callback(" + json.dumps(payload) + ")"
    obj = json.loads(text[text.index("(") + 1:text.rindex(")")])
    fields = obj["data"].split(";")[0].split(",")
    row = pd.DataFrame([{
        "日期": fields[0], "开盘": fields[1], "最高": fields[2],
        "最低": fields[3], "收盘": fields[4], "成交量": fields[5],
    }])
    valid = eastmoney._validate_kline(row, 1)
    assert valid.iloc[0]["最高"] == 12
    assert valid.iloc[0]["收盘"] == 11
