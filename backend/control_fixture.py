"""Fixture profile for the Control Center's added aisle."""

from .mock_api import INVENTORY, create_app, read_json


extra = read_json("test_data/control_inventory_extension.json")
app = create_app({**INVENTORY, "locations": [*INVENTORY["locations"], *extra["locations"]]})
