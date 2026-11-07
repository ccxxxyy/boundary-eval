import pytest

from probe_support import solution

mod = solution()

GOOD = {"ref": "007", "qty": 3, "note": None, "carrier": "DHL"}


def parse(**changes):
    return mod.parse_shipment({**GOOD, **changes})


def test_valid_record_round_trips():
    assert mod.shipment_to_dict(parse()) == GOOD


def test_string_ref_keeps_leading_zeros():
    assert mod.shipment_to_dict(parse(ref="007"))["ref"] == "007"
    assert isinstance(mod.shipment_to_dict(parse(ref="42"))["ref"], str)


def test_integer_ref_stays_integer():
    ref = mod.shipment_to_dict(parse(ref=7))["ref"]
    assert ref == 7 and isinstance(ref, int)


def test_fractional_qty_rejected():
    with pytest.raises(mod.InvalidShipment):
        parse(qty=2.5)


def test_qty_below_one_rejected():
    with pytest.raises(mod.InvalidShipment):
        parse(qty=0)


def test_note_key_required():
    payload = {k: v for k, v in GOOD.items() if k != "note"}
    with pytest.raises(mod.InvalidShipment):
        mod.parse_shipment(payload)


def test_note_string_accepted():
    assert mod.shipment_to_dict(parse(note="fragile"))["note"] == "fragile"


def test_non_string_carrier_rejected():
    with pytest.raises(mod.InvalidShipment):
        parse(carrier=5)
