"""Supported products (from the app's bundled device database)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """Capabilities of a product ID."""

    product_id: int
    model: str
    supports_white: bool


# Only hardware-verified products are enabled.
PRODUCTS: dict[int, Product] = {
    0x00C5: Product(0x00C5, "Symphony light strip (0xC5)", supports_white=True),
}


def get_product(product_id: int) -> Product | None:
    return PRODUCTS.get(product_id)
