# Synthetic fixtures

All records under this directory are synthetic. The expected inventory simulates SAP, and observation payloads represent manually authored examples of what a vision system can report. The same records feed the mock API and its validation tests.

| Case | Slot | Observed | Expected result |
| --- | --- | --- | --- |
| Correct pallet | A-01-01 | P001, as expected | `match` |
| Wrong location | A-01-02 | P003, assigned to A-01-03 | `wrong_pallet` |
| Missing pallet | A-01-03 | Empty, inventory expects P003 | `missing_pallet` |
| Unexpected pallet | A-01-04 | P999 in an expected empty slot | `unexpected_pallet` |
| Unreadable label | A-01-05 | Occupied with no readable ID | `unreadable_label` |
| Uninspected | A-01-06 | No assigned observation | `uninspected` |
| Uncertain | A-01-07 | Capture did not establish occupancy | `uncertain` |
| Repeated location | A-01-08 | First P998, then P008 | Two historical events and latest `match`. An identical POST retry leaves one row for that event ID. |

The seeded summary has 8 slots, 7 observed slots, 8 unique events and 5 discrepancies or review items. See the [API examples](api_examples.json) and [HTTP contract](../contracts/http.md).
