from pydantic import BaseModel, Extra, StrictStr, ValidationError, conint, constr


class InvalidOrder(Exception):
    pass


class Order(BaseModel):
    sku: constr(regex=r"^[A-Z]{3}-\d{4}$")
    qty: conint(ge=1)
    customer_id: StrictStr

    class Config:
        extra = Extra.forbid


def parse_order(payload: dict) -> Order:
    try:
        return Order(**payload)
    except (ValidationError, TypeError) as exc:
        raise InvalidOrder(str(exc)) from exc


def order_to_dict(order: Order) -> dict:
    return order.dict()
