"""Attach consistent provenance and use-risk labels to housing datasets."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List


def classify_source(row: Dict[str, str]) -> Dict[str, object]:
    url = (row.get("source_url") or "").lower()
    if not url:
        url = " ".join(
            (row.get(name) or "").lower()
            for name in ("source_url_real_estate", "source_url_lpr")
        )
    source_type = (row.get("source_type") or "").lower()
    methodology = (row.get("methodology") or "").lower()

    if "stats.gov.cn" in url or "official" in source_type:
        tier = "A_official"
        source_class = "government_statistics_or_registry"
        is_official = True
    elif "zjw.beijing.gov.cn" in url or "zfcxjw.cq.gov.cn" in url:
        tier = "A_official"
        source_class = "government_housing_transaction"
        is_official = True
    elif "cirea" in url or "cirea" in methodology:
        tier = "B_industry_index"
        source_class = "industry_price_index"
        is_official = False
    elif "creprice.cn" in url or "third_party" in source_type:
        tier = "C_public_third_party"
        source_class = "public_third_party_report"
        is_official = False
    else:
        tier = "D_unverified_or_derived"
        source_class = "unclassified"
        is_official = False

    if "listing" in methodology or "挂牌" in methodology:
        price_basis = "listing_price"
        is_transaction_price = False
        training_role = "exploratory_only"
    elif "online_signing" in methodology or "网签" in methodology:
        price_basis = "transaction_volume_area"
        is_transaction_price = False
        training_role = "primary_for_transaction_activity"
    elif "price_index" in source_class or "index" in methodology:
        price_basis = "price_index"
        is_transaction_price = False
        training_role = "primary_for_city_index"
    elif tier == "A_official":
        price_basis = "official_statistic"
        is_transaction_price = False
        training_role = "primary_official"
    else:
        price_basis = "unknown_or_derived"
        is_transaction_price = False
        training_role = "needs_review"

    if tier == "A_official" and "online_signing" in methodology:
        notes = "官方网签成交量/面积；不等于成交单价"
    elif tier == "A_official":
        notes = "官方统计；需按指标定义使用"
    elif tier == "B_industry_index":
        notes = "行业公开指数；不是政府原始网签明细"
    elif tier == "C_public_third_party":
        notes = "公开第三方报告；挂牌/市场均价，不能视为官方成交价"
    else:
        notes = "来源或口径未充分核验"

    return {
        "source_tier": tier,
        "source_class": source_class,
        "is_official_source": is_official,
        "price_basis": price_basis,
        "is_transaction_price": is_transaction_price,
        "training_role": training_role,
        "provenance_note": notes,
    }


def label_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    labelled = []
    for row in rows:
        output = dict(row)
        output.update({key: str(value) for key, value in classify_source(row).items()})
        labelled.append(output)
    return labelled


def label_csv(input_path: str | Path, output_path: str | Path) -> int:
    with open(input_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labelled = label_rows(rows)
    fields = list(labelled[0].keys()) if labelled else []
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(labelled)
    return len(labelled)
