from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OcdsDocument:
    title: str
    agency: str | None
    buyer: str | None
    procurement_id: str | None
    source_id: str | None
    description_text: str
    raw_metadata: dict = field(default_factory=dict)


def normalize_ocds(raw: dict, source_path: str) -> OcdsDocument:
    ocid = raw.get("ocid") or raw.get("id") or source_path

    title = (
        _nested(raw, "tender", "title")
        or raw.get("id")
        or ocid
    )

    buyer = _nested(raw, "buyer", "name")
    agency = _nested(raw, "procuringEntity", "name") or buyer

    procurement_id = (
        _nested(raw, "tender", "id")
        or ocid
    )

    description_parts: list[str] = []

    tender_desc = _nested(raw, "tender", "description")
    if tender_desc:
        description_parts.append(tender_desc)

    tender_rationale = _nested(raw, "tender", "procurementMethodRationale")
    if tender_rationale:
        description_parts.append(tender_rationale)

    for award in raw.get("awards") or []:
        award_desc = award.get("description")
        if award_desc:
            description_parts.append(award_desc)

    for contract in raw.get("contracts") or []:
        contract_desc = contract.get("description")
        if contract_desc:
            description_parts.append(contract_desc)

    description_text = "\n\n".join(description_parts).strip()

    if not description_text:
        description_text = title

    return OcdsDocument(
        title=title,
        agency=agency,
        buyer=buyer,
        procurement_id=procurement_id,
        source_id=ocid,
        description_text=description_text,
        raw_metadata=_prune_metadata(raw),
    )


def _prune_metadata(raw: dict) -> dict:
    tender = raw.get("tender") or {}
    return {
        "ocid": raw.get("ocid"),
        "id": raw.get("id"),
        "date": raw.get("date"),
        "tender_status": tender.get("status"),
        "tender_value": tender.get("value"),
        "tender_method": tender.get("procurementMethod"),
        "tender_period": tender.get("tenderPeriod"),
        "tender_items_count": len(tender.get("items") or []),
        "awards_count": len(raw.get("awards") or []),
        "contracts_count": len(raw.get("contracts") or []),
        "language": raw.get("language"),
    }


def _nested(d: dict, *keys: str) -> str | None:
    current: object = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None
