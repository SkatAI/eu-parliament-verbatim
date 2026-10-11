from eu_verbatim.build import item_numbers


def test_item_numbers():
    assert item_numbers("CRE-10-2026-10-05-ITM-012") == (12, None)
    assert item_numbers("CRE-10-2026-10-06-ITM-009-07") == (9, 7)
    ids = ["CRE-10-2026-10-06-ITM-010", "CRE-10-2026-10-06-ITM-009-02", "CRE-10-2026-10-06-ITM-009"]
    ordered = sorted(ids, key=lambda i: (item_numbers(i)[0], item_numbers(i)[1] or 0))
    assert ordered == ["CRE-10-2026-10-06-ITM-009", "CRE-10-2026-10-06-ITM-009-02", "CRE-10-2026-10-06-ITM-010"]
