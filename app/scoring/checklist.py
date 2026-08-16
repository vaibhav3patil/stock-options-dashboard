from __future__ import annotations

from app.models.schemas import Eligibility, SymbolRow


def _rule_status(row: SymbolRow, rule_id: str) -> str:
    if rule_id in row.failed_rules:
        return "FAIL"
    return "PASS"


def build_checklist(row: SymbolRow) -> list[dict[str, str]]:
    liq_rules = [r for r in row.failed_rules if r.startswith("L")]
    items = [
        {
            "rule_id": "IN12",
            "status": "PASS" if row.data_status.value == "OK" else "FAIL",
            "detail": row.data_status.value,
        },
        {
            "rule_id": "L1-L5",
            "status": "FAIL" if liq_rules else ("PASS" if row.oi_atm is not None else "PENDING"),
            "detail": (
                f"failed={liq_rules or '—'}; OI={row.oi_atm}; vol={row.volume_atm}; "
                f"bidask%={None if row.bid_ask_pct is None else round(row.bid_ask_pct * 100, 2)}"
            ),
        },
        {
            "rule_id": "M3",
            "status": _rule_status(row, "M3") if row.move_vs_premium_ratio is not None or "M3" in row.failed_rules else "PENDING",
            "detail": f"move/premium={row.move_vs_premium_ratio}",
        },
        {
            "rule_id": "V5",
            "status": "WARN" if "IV_RICH_VS_HV" in row.setup_tags else "INFO",
            "detail": f"ATM_IV={row.atm_iv}; HV20={row.hv_20}",
        },
        {
            "rule_id": "T1",
            "status": _rule_status(row, "T1") if "T1" in row.failed_rules else "INFO",
            "detail": f"Trend={row.trend.value}; bias={row.direction_bias.value}",
        },
        {
            "rule_id": "T2",
            "status": "INFO",
            "detail": f"RS20={row.rs_20}",
        },
        {
            "rule_id": "T4",
            "status": "INFO",
            "detail": f"Squeeze={row.squeeze}",
        },
        {
            "rule_id": "P5",
            "status": "INFO",
            "detail": f"PCR={row.pcr}",
        },
        {
            "rule_id": "IN10",
            "status": "FAIL" if "L4" in row.failed_rules else "INFO",
            "detail": f"premium/lot={row.premium_per_lot}; lot={row.lot_size}",
        },
        {
            "rule_id": "Eligibility",
            "status": "INFO",
            "detail": row.eligibility.value
            if row.eligibility != Eligibility.NAKED_BUY_OK
            else "NAKED_BUY_OK",
        },
        {
            "rule_id": "IN1",
            "status": "FAIL" if row.in_fno_ban or "IN1" in row.failed_rules else "PASS",
            "detail": "F&O ban" if row.in_fno_ban else "Not in ban list (or list unavailable)",
        },
        {
            "rule_id": "C1",
            "status": (
                "FAIL"
                if "C1" in row.failed_rules
                else ("INFO" if row.event_days is not None else "PENDING")
            ),
            "detail": (
                f"{row.event_kind or '—'} in {row.event_days}d ({row.event_date})"
                if row.event_days is not None
                else "No upcoming event found"
            ),
        },
        {
            "rule_id": "V3-V4",
            "status": (
                "FAIL"
                if "V3" in row.failed_rules
                else ("INFO" if row.iv_rank is not None else "PENDING")
            ),
            "detail": f"IV Rank={row.iv_rank}; IVP={row.iv_percentile}",
        },
    ]
    return items
