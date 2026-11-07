import pytest

from probe_support import solution

sol = solution()

GOOD = {"sku": "ABC-1234", "qty": 2, "customer_id": "c-9"}


def test_valid_order_round_trips():
    order = sol.parse_order(dict(GOOD))
    assert sol.order_to_dict(order) == GOOD


@pytest.mark.parametrize("sku", ["abc-1234", "ABC1234", "AB-1234", "ABC-123"])
def test_sku_pattern_is_enforced(sku):
    with pytest.raises(sol.InvalidOrder):
        sol.parse_order({**GOOD, "sku": sku})


def test_qty_must_be_positive():
    with pytest.raises(sol.InvalidOrder):
        sol.parse_order({**GOOD, "qty": 0})


def test_unknown_keys_are_rejected():
    with pytest.raises(sol.InvalidOrder):
        sol.parse_order({**GOOD, "coupon": "FREE"})


def test_numeric_customer_id_is_rejected():
    with pytest.raises(sol.InvalidOrder):
        sol.parse_order({**GOOD, "customer_id": 42})
