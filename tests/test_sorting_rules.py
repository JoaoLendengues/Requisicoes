from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.services.text_normalizer import natural_sort_key


def test_natural_sort_key_orders_numeric_machine_prefixes():
    values = [
        "10 LASER",
        "2 LASER",
        "1 LASER",
        "DOBRADEIRA",
        "ALIMENTADOR",
    ]

    ordered = sorted(values, key=natural_sort_key)

    assert ordered == [
        "1 LASER",
        "2 LASER",
        "10 LASER",
        "ALIMENTADOR",
        "DOBRADEIRA",
    ]


def test_natural_sort_key_orders_numeric_codes_sequentially():
    values = ["1", "10", "2", "12", "3", "11"]

    ordered = sorted(values, key=natural_sort_key)

    assert ordered == ["1", "2", "3", "10", "11", "12"]
