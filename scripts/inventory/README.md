# CSV inventory import

`import_csv.py` validates warehouse inventory and product CSV files and converts them into the JSON documents used by the Mock SAP backend. It is a standalone tool: it does not start or change the backend, and it runs without ROS 2, Gazebo or the backend virtual environment.

| Input | Generated file | Structure |
| --- | --- | --- |
| Inventory CSV | `expected_inventory.json` | `Inventory` in the [OpenAPI contract](../../contracts/openapi.json), like [expected_inventory.json](../../test_data/expected_inventory.json) |
| Product CSV | `mock_sap_products.json` | Same fields as [mock_sap_products.json](../../test_data/mock_sap_products.json) |

The tool reads all given files completely and reports every problem it finds. It writes JSON only when every input is valid. If any file has an error, it writes nothing and exits with status 1.

## Requirements

Python 3.10 or later, standard library only. The project's Python 3.10 (Ubuntu/WSL) and 3.13 (Windows) interpreters both work, inside or outside `.venv-backend`.

## CSV columns

Files are UTF-8 (a byte order mark from Excel is accepted), comma-separated, with a header row. Columns may appear in any order. Unknown, duplicated and missing columns are errors. Values are used exactly as written: surrounding spaces, lowercase status values and other near misses are reported, never corrected.

Inventory ([template](templates/inventory_template.csv)):

| Column | Required | Rule |
| --- | --- | --- |
| `slot_id` | Yes | Aisle letter, two-digit bay, two-digit level, e.g. `A-01-02`. Each location appears once. |
| `pallet_id` | No | `P` and three digits, e.g. `P001`. Leave empty for a location expected to be empty (JSON `null`). A pallet can be assigned to only one location. |

The slot and pallet patterns are read from `contracts/openapi.json` at run time.

Products ([template](templates/products_template.csv)):

| Column | Required | Rule |
| --- | --- | --- |
| `hu_id` | Yes | Handling unit ID in pallet format, e.g. `P001`. Each HU appears once. |
| `sku`, `product_name`, `batch` | Yes | Free text. |
| `lifecycle_status` | Yes | `ACTIVE`, `DISCONTINUED`, `BLOCKED` or `UNKNOWN`, the values interpreted by `backend/intelligence.py`. |
| `quality_status` | Yes | `RELEASED`, `ON_HOLD` or `PENDING`, as used by the Mock SAP product data. |
| `stock_status` | Yes | `ON_HAND` or `RESTRICTED`, as used by the Mock SAP product data. |

When both files are imported together, every pallet in the inventory needs a product record. A product that no location expects is reported as a warning and is still imported; the backend then reports its `expected_slot` as `null`.

## Running the importer

From the repository root:

```bash
python3 scripts/inventory/import_csv.py \
  --inventory scripts/inventory/samples/inventory_valid.csv \
  --products scripts/inventory/samples/products_valid.csv
```

On Windows, use `python` in PowerShell with the same arguments.

| Option | Meaning |
| --- | --- |
| `--inventory FILE` | Inventory CSV. |
| `--products FILE` | Product CSV. Give one or both files. |
| `--output-dir DIR` | Where to write JSON. Default: `.rackonaut-data/inventory-import/`, which Git ignores. Created if missing. |
| `--check` | Validate only. Nothing is written. |

The tool refuses to write into `test_data/`, `contracts/` or `backend/`, so the demo data cannot be overwritten. Each file is written to a temporary file and then renamed into place. A failed run leaves any earlier output in the directory unchanged, so check the exit status and the last line of output before using the files. To use the generated data in a demo, copy it deliberately; the backend reads `test_data/` and is not changed by this tool.

## Successful import

The samples contain the repository's demo data: the eight A locations, the three B locations of the Control Center extension and the nine Mock SAP handling units. Their import reproduces the existing JSON exactly.

```text
$ python3 scripts/inventory/import_csv.py --inventory scripts/inventory/samples/inventory_valid.csv --products scripts/inventory/samples/products_valid.csv
Import succeeded: 11 location(s) and 9 product(s).
Wrote <repository>/.rackonaut-data/inventory-import/expected_inventory.json
Wrote <repository>/.rackonaut-data/inventory-import/mock_sap_products.json
```

```json
{
  "source": "mock_sap",
  "locations": [
    {
      "slot_id": "A-01-01",
      "pallet_id": "P001"
    },
    {
      "slot_id": "A-01-04",
      "pallet_id": null
    }
  ]
}
```

(Excerpt; the full file has all 11 locations.)

## Validation errors

Errors go to standard error as `ERROR: <file>, row <n>, <field>: <message>`. Row numbers are CSV line numbers, where the header is row 1. File-level problems such as a missing file, invalid UTF-8 or malformed quoting have no row or field.

```text
$ python3 scripts/inventory/import_csv.py --inventory scripts/inventory/samples/inventory_invalid.csv --products scripts/inventory/samples/products_invalid.csv
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 3, slot_id: 'A-1-02' is not a valid slot ID. Use aisle letter, bay and level, e.g. A-01-02.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 5, slot_id: Duplicate location A-01-03; it is already defined in row 4.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 6, pallet_id: Conflicting assignment: pallet P001 is already assigned to A-01-01 in row 2.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 7, slot_id: Required value is empty.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 8, pallet_id: 'P07' is not a valid pallet ID. Use P and three digits, e.g. P001, or leave the value empty for a location expected to be empty.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 9: Row has 3 values but the header has 2 columns.
ERROR: scripts/inventory/samples/inventory_invalid.csv, row 10, pallet_id: Pallet P009 has no product record in scripts/inventory/samples/products_invalid.csv.
ERROR: scripts/inventory/samples/products_invalid.csv, row 3, lifecycle_status: Unsupported status 'RETIRED'. Supported values: ACTIVE, DISCONTINUED, BLOCKED, UNKNOWN.
ERROR: scripts/inventory/samples/products_invalid.csv, row 4, sku: Required value is empty.
ERROR: scripts/inventory/samples/products_invalid.csv, row 5, hu_id: Duplicate handling unit P003; it is already defined in row 4.
ERROR: scripts/inventory/samples/products_invalid.csv, row 6, hu_id: 'HU-005' is not a valid handling unit ID. Use P and three digits, e.g. P001.
ERROR: scripts/inventory/samples/products_invalid.csv, row 6, lifecycle_status: Unsupported status 'active'. Supported values: ACTIVE, DISCONTINUED, BLOCKED, UNKNOWN. Did you mean ACTIVE?
ERROR: scripts/inventory/samples/products_invalid.csv, row 7, quality_status: Unsupported status 'QUARANTINE'. Supported values: RELEASED, ON_HOLD, PENDING.
Validation failed: 13 error(s) in 2 file(s). No JSON files were written.
```

| Exit status | Meaning |
| --- | --- |
| 0 | All inputs valid; JSON written (or validated with `--check`). |
| 1 | Validation failed; nothing written. |
| 2 | Invalid command-line usage. |

## Tests

The tests are in [`tests/test_inventory_import.py`](../../tests/test_inventory_import.py) and run with the project's contract tests.

```bash
.venv-backend/bin/python -m unittest discover -s tests -v
python3 -m unittest tests.test_inventory_import -v
```

The second command runs only the importer tests and needs no backend packages. One test validates the output against the OpenAPI `Inventory` schema and is skipped when `jsonschema` 4 is not installed.
