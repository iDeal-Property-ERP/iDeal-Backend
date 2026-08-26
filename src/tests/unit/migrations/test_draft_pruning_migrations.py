from importlib import import_module

PROPERTY_MIGRATION = import_module("property.migrations.0013_alter_oneoffdeal_status_and_more")
INVENTORY_MIGRATION = import_module("inventory.migrations.0002_alter_inventoryact_status")


def test_property_photo_primary_normalization_is_deterministic():
    rows_ordered_by_property_and_id = [
        (10, 101, False),
        (10, 102, False),
        (20, 201, True),
        (20, 202, True),
        (30, 301, False),
        (30, 302, True),
    ]

    assert PROPERTY_MIGRATION._choose_primary_photo_ids(rows_ordered_by_property_and_id) == [101, 201, 302]
