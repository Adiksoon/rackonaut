import unittest

from jsonschema import Draft202012Validator

from backend.mock_api import (
    CONTRACT,
    EXPECTED_BY_SLOT,
    FIXTURES,
    INVENTORY,
    FixtureStore,
    check_observation,
    read_json,
)


class FixtureContractTests(unittest.TestCase):
    def validate(self, instance, component):
        validator = Draft202012Validator({
            "$ref": f"#/components/schemas/{component}",
            "components": CONTRACT["components"],
        })
        validator.validate(instance)

    def test_inventory_and_all_eight_scenarios(self):
        self.validate(INVENTORY, "Inventory")
        self.assertEqual(len(INVENTORY["locations"]), len(EXPECTED_BY_SLOT))
        scenarios = FIXTURES["scenarios"]
        self.assertTrue(FIXTURES["fixture"])
        self.assertEqual(len(scenarios), 8)
        self.assertEqual({case["slot_id"] for case in scenarios}, set(EXPECTED_BY_SLOT))
        keys = set()
        for case in scenarios:
            for event in case["events"]:
                with self.subTest(case=case["name"]):
                    observation = event["observation"]
                    self.assertEqual(observation["slot_id"], case["slot_id"])
                    self.assertEqual(observation["inspection_id"], FIXTURES["inspection_id"])
                    self.validate(observation, "Observation")
                    check_observation(observation)
                    self.assertNotIn(observation["observation_id"], keys)
                    keys.add(observation["observation_id"])

    def test_seeded_results_match_declared_scenarios(self):
        outcomes = FixtureStore()
        history = outcomes.history(FIXTURES["inspection_id"])
        slots = outcomes.slots(history)
        expected = {case["slot_id"]: case["expected_final_outcome"] for case in FIXTURES["scenarios"]}
        self.assertEqual({slot["slot_id"]: slot["outcome"] for slot in slots}, expected)
        for slot in slots:
            self.validate(slot, "SlotResult")

    def test_synthetic_examples_match_response_schemas(self):
        examples = read_json("test_data/api_examples.json")
        self.assertTrue(examples["fixture"])
        self.validate(examples["post_request"]["body"], "Observation")
        responses = examples["get_responses"]
        self.validate(responses["/health"], "Health")
        self.validate(responses["/api/summary"], "Summary")
        for slot in responses["/api/discrepancies"]:
            self.validate(slot, "SlotResult")

    def test_out_of_order_capture_and_equal_time_are_deterministic(self):
        store = FixtureStore()
        first = store.history(FIXTURES["inspection_id"])[0]
        newer = {**first, "inspection_id": "INS-TEST", "observation_id": "OBS-B"}
        same_time = {**newer, "observation_id": "OBS-A", "timestamp": "2026-11-25T12:00:01.000Z"}
        older = {**newer, "observation_id": "OBS-C", "timestamp": "2026-11-25T11:59:59Z"}
        for item in (newer, same_time, older):
            self.assertEqual(store.record(item), 201)
        history = store.history("INS-TEST")
        self.assertEqual([item["observation_id"] for item in history], ["OBS-C", "OBS-A", "OBS-B"])
        self.assertEqual(store.slots(history)[0]["observation_id"], "OBS-B")


if __name__ == "__main__":
    unittest.main()
