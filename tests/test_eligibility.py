from __future__ import annotations

from app.data.providers.nse_bhavcopy import NseBhavcopyProvider, filter_fo_options
from app.data.providers.nse_option_chain import _normalize_chain_payload
from app.models.schemas import DataStatus, Eligibility, InstrumentType
from app.scoring.engine import score_pre_chain


def test_normalize_empty_chain():
    payload = _normalize_chain_payload({}, "TCS")
    assert payload["status"] == "DATA_UNAVAILABLE"


def test_bhav_provider_symbol_filter():
    import pandas as pd

    provider = NseBhavcopyProvider(lookback_days=3)
    df = pd.DataFrame(
        {
            "TckrSymb": ["RELIANCE", "TCS", "RELIANCE"],
            "FinInstrmTp": ["STO", "STO", "STF"],
            "OptnTp": ["CE", "PE", None],
        }
    )
    out = provider.symbol_options(df, "RELIANCE")
    assert len(out) == 1
    assert out.iloc[0]["OptnTp"] == "CE"
    assert filter_fo_options(df, "RELIANCE", option_type="CE").iloc[0]["OptnTp"] == "CE"


def test_eligibility_state_watch_default():
    row = score_pre_chain(
        symbol="INFY",
        instrument_type=InstrumentType.STOCK,
        features=None,
        data_status=DataStatus.DATA_STALE,
    )
    assert row.eligibility == Eligibility.EXCLUDE
