"""Validate inventory and product CSV files and convert them to Rackonaut JSON.

The importer reads two CSV formats and writes the JSON documents that the
Mock SAP backend loads:

* inventory CSV -> ``expected_inventory.json`` (the ``Inventory`` component
  of ``contracts/openapi.json``)
* product CSV   -> ``mock_sap_products.json`` (the structure of
  ``test_data/mock_sap_products.json``)

Every input is validated completely before anything is written. If any
error is found, no JSON file is written and every problem is reported with
its file, CSV row and field. The tool uses only the Python standard library
and runs without ROS 2, Gazebo or the backend environment.

Run from the repository root::

    python3 scripts/inventory/import_csv.py --inventory inventory.csv --products products.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "openapi.json"
DEFAULT_OUTPUT_DIR = ROOT / ".rackonaut-data" / "inventory-import"
INVENTORY_OUTPUT = "expected_inventory.json"
PRODUCTS_OUTPUT = "mock_sap_products.json"
# Generated files must never replace the demo data, contracts or backend code.
PROTECTED_DIRS = tuple(ROOT / name for name in ("test_data", "contracts", "backend"))

SOURCE = "mock_sap"
INVENTORY_COLUMNS = ("slot_id", "pallet_id")
PRODUCT_COLUMNS = (
    "hu_id",
    "sku",
    "product_name",
    "batch",
    "lifecycle_status",
    "quality_status",
    "stock_status",
)
# backend/intelligence.py interprets exactly these lifecycle values.
LIFECYCLE_STATUSES = ("ACTIVE", "DISCONTINUED", "BLOCKED", "UNKNOWN")
# Values used by the Mock SAP product master in test_data/mock_sap_products.json.
QUALITY_STATUSES = ("RELEASED", "ON_HOLD", "PENDING")
STOCK_STATUSES = ("ON_HAND", "RESTRICTED")
STATUS_FIELDS = {
    "lifecycle_status": LIFECYCLE_STATUSES,
    "quality_status": QUALITY_STATUSES,
    "stock_status": STOCK_STATUSES,
}


def contract_patterns(path=CONTRACT_PATH):
    """Read the slot and pallet ID patterns from the shared OpenAPI contract."""
    contract = json.loads(Path(path).read_text(encoding="utf-8"))
    location = contract["components"]["schemas"]["ExpectedLocation"]["properties"]
    slot = location["slot_id"]["pattern"]
    pallet = next(option["pattern"] for option in location["pallet_id"]["anyOf"] if option.get("type") == "string")
    return re.compile(slot), re.compile(pallet)


SLOT_ID, PALLET_ID = contract_patterns()


@dataclass(frozen=True)
class Issue:
    """One validation problem. ``row`` is the CSV line number; the header is row 1."""

    file: str
    row: object
    field: object
    message: str
    severity: str = "error"

    def __str__(self):
        parts = [self.file]
        if self.row is not None:
            parts.append(f"row {self.row}")
        if self.field is not None:
            parts.append(self.field)
        return f"{self.severity.upper()}: {', '.join(parts)}: {self.message}"


@dataclass
class ImportResult:
    errors: list
    warnings: list
    written: list
    locations: int = 0
    products: int = 0

    @property
    def ok(self):
        return not self.errors


def read_rows(path, columns, errors):
    """Return ``[(row_number, {column: value})]`` or None when the file cannot be used.

    Problems are appended to ``errors``. Values are returned exactly as written.
    """
    name = str(path)
    if Path(path).is_dir():
        errors.append(Issue(name, None, None, "Expected a CSV file but found a directory."))
        return None
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            records = []
            reader = csv.reader(handle, strict=True)
            line = 0
            for values in reader:
                records.append((line + 1, values))
                line = reader.line_num
    except FileNotFoundError:
        errors.append(Issue(name, None, None, "File not found."))
        return None
    except UnicodeDecodeError as exc:
        errors.append(Issue(name, None, None, f"File is not valid UTF-8 text (byte {exc.start}). Save the CSV as UTF-8."))
        return None
    except csv.Error as exc:
        errors.append(Issue(name, reader.line_num, None, f"Malformed CSV: {exc}."))
        return None
    except OSError as exc:
        errors.append(Issue(name, None, None, f"Cannot read file: {exc.strerror or exc}."))
        return None

    records = [(row, values) for row, values in records if values]
    if not records:
        errors.append(Issue(name, None, None, f"File is empty. Expected the header: {','.join(columns)}"))
        return None

    header_row, header = records[0]
    if not check_header(name, header_row, header, columns, errors):
        return None

    if len(records) == 1:
        errors.append(Issue(name, None, None, "File has a header but no data rows."))
        return None
    rows = []
    for row, values in records[1:]:
        if len(values) > len(header):
            errors.append(Issue(name, row, None,
                                f"Row has {len(values)} values but the header has {len(header)} columns."))
            continue
        padded = values + [None] * (len(header) - len(values))
        rows.append((row, dict(zip(header, padded))))
    return rows


def check_header(name, row, header, columns, errors):
    """Check the header row. Columns may appear in any order but must match exactly."""
    ok = True
    if len(header) == 1 and ";" in header[0]:
        errors.append(Issue(name, row, None, "Header uses semicolons. Save the file with comma separators."))
        return False
    seen = set()
    for column in header:
        if column in seen:
            errors.append(Issue(name, row, column, "Column appears more than once in the header."))
            ok = False
        seen.add(column)
        if column not in columns:
            errors.append(Issue(name, row, column or "(blank)",
                                f"Unknown column. Expected exactly: {','.join(columns)}"))
            ok = False
    for column in columns:
        if column not in seen:
            errors.append(Issue(name, row, column, "Required column is missing from the header."))
            ok = False
    return ok


def check_text(name, row, field, value, errors, required=True):
    """Check that a value is present and has no surrounding spaces. Returns True when usable."""
    if value is None:
        errors.append(Issue(name, row, field, "Value is missing (the row has too few columns)."))
        return False
    if value == "":
        if required:
            errors.append(Issue(name, row, field, "Required value is empty."))
        return False
    if value != value.strip():
        errors.append(Issue(name, row, field, f"Value {value!r} has leading or trailing spaces."))
        return False
    return True


def validate_inventory(path):
    """Validate an inventory CSV. Returns ``(locations, rows_by_pallet, errors)``."""
    errors = []
    name = str(path)
    rows = read_rows(path, INVENTORY_COLUMNS, errors)
    if rows is None:
        return None, {}, errors

    locations = []
    slot_rows = {}
    pallet_rows = {}
    for row, record in rows:
        slot_id, pallet_id = record["slot_id"], record["pallet_id"]
        slot_ok = check_text(name, row, "slot_id", slot_id, errors)
        if slot_ok and not SLOT_ID.match(slot_id):
            errors.append(Issue(name, row, "slot_id",
                                f"{slot_id!r} is not a valid slot ID. Use aisle letter, bay and level, e.g. A-01-02."))
            slot_ok = False
        if slot_ok:
            if slot_id in slot_rows:
                errors.append(Issue(name, row, "slot_id",
                                    f"Duplicate location {slot_id}; it is already defined in row {slot_rows[slot_id]}."))
            else:
                slot_rows[slot_id] = row

        pallet_ok = check_text(name, row, "pallet_id", pallet_id, errors, required=False)
        if pallet_ok and not PALLET_ID.match(pallet_id):
            errors.append(Issue(name, row, "pallet_id",
                                f"{pallet_id!r} is not a valid pallet ID. Use P and three digits, e.g. P001, "
                                "or leave the value empty for a location expected to be empty."))
            pallet_ok = False
        if pallet_ok:
            if pallet_id in pallet_rows:
                first_row, first_slot = pallet_rows[pallet_id]
                errors.append(Issue(name, row, "pallet_id",
                                    f"Conflicting assignment: pallet {pallet_id} is already assigned to "
                                    f"{first_slot} in row {first_row}."))
            else:
                pallet_rows[pallet_id] = (row, slot_id)

        locations.append({"slot_id": slot_id, "pallet_id": pallet_id or None})
    return locations, {pallet: row for pallet, (row, _) in pallet_rows.items()}, errors


def validate_products(path):
    """Validate a product CSV. Returns ``(handling_units, errors)``."""
    errors = []
    name = str(path)
    rows = read_rows(path, PRODUCT_COLUMNS, errors)
    if rows is None:
        return None, errors

    units = []
    hu_rows = {}
    for row, record in rows:
        for field in PRODUCT_COLUMNS:
            check_text(name, row, field, record[field], errors)
        hu_id = record["hu_id"]
        if hu_id and hu_id == hu_id.strip():
            if not PALLET_ID.match(hu_id):
                errors.append(Issue(name, row, "hu_id",
                                    f"{hu_id!r} is not a valid handling unit ID. Use P and three digits, e.g. P001."))
            elif hu_id in hu_rows:
                errors.append(Issue(name, row, "hu_id",
                                    f"Duplicate handling unit {hu_id}; it is already defined in row {hu_rows[hu_id]}."))
            else:
                hu_rows[hu_id] = row
        for field, allowed in STATUS_FIELDS.items():
            value = record[field]
            if value and value == value.strip() and value not in allowed:
                hint = f" Did you mean {value.upper()}?" if value.upper() in allowed else ""
                errors.append(Issue(name, row, field,
                                    f"Unsupported status {value!r}. Supported values: {', '.join(allowed)}.{hint}"))
        units.append({field: record[field] for field in PRODUCT_COLUMNS})
    return units, errors


def check_references(inventory_name, pallet_rows, products_name, units):
    """Cross-check inventory pallets against product records.

    A pallet expected in the inventory without a product record is an error.
    A product that no location expects is reported as a warning: the backend
    accepts it and reports ``expected_slot`` as null.
    """
    errors, warnings = [], []
    products = {unit["hu_id"] for unit in units}
    for pallet, row in sorted(pallet_rows.items(), key=lambda item: item[1]):
        if pallet not in products:
            errors.append(Issue(inventory_name, row, "pallet_id",
                                f"Pallet {pallet} has no product record in {products_name}."))
    placed = set(pallet_rows)
    seen = set()
    for unit in units:
        hu_id = unit["hu_id"]
        if hu_id not in placed and hu_id not in seen and PALLET_ID.match(hu_id or ""):
            warnings.append(Issue(products_name, None, "hu_id",
                                  f"Handling unit {hu_id} is not assigned to any location in {inventory_name}.",
                                  severity="warning"))
        seen.add(hu_id)
    return errors, warnings


def inventory_document(locations):
    return {"source": SOURCE, "locations": locations}


def products_document(units):
    return {"source": SOURCE, "synthetic": True, "handling_units": units}


def check_output_dir(output_dir):
    """Refuse output directories that would replace demo data, contracts or backend files."""
    resolved = Path(output_dir).resolve()
    for protected in PROTECTED_DIRS:
        if resolved == protected or protected in resolved.parents:
            return Issue(str(output_dir), None, None,
                         f"Refusing to write into {protected.relative_to(ROOT)}/. Choose a separate output directory.")
    if resolved.exists() and not resolved.is_dir():
        return Issue(str(output_dir), None, None, "Output path exists and is not a directory.")
    return None


def write_json(directory, filename, document):
    """Write JSON atomically: a temporary file in the same directory, then rename."""
    target = directory / filename
    descriptor, temporary = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def run_import(inventory=None, products=None, output_dir=DEFAULT_OUTPUT_DIR, check_only=False):
    """Validate the given CSV files and, if all are valid, write their JSON documents.

    Nothing is written when any input has an error.
    """
    if inventory is None and products is None:
        raise ValueError("Provide an inventory CSV, a product CSV, or both.")
    errors, warnings = [], []
    locations = units = None
    pallet_rows = {}

    if not check_only:
        problem = check_output_dir(output_dir)
        if problem:
            errors.append(problem)
    if inventory is not None:
        locations, pallet_rows, found = validate_inventory(inventory)
        errors.extend(found)
    if products is not None:
        units, found = validate_products(products)
        errors.extend(found)
    if locations is not None and units is not None:
        found, warned = check_references(str(inventory), pallet_rows, str(products), units)
        errors.extend(found)
        warnings.extend(warned)

    result = ImportResult(errors, warnings, [],
                          locations=len(locations or []), products=len(units or []))
    if errors or check_only:
        return result

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if locations is not None:
        result.written.append(write_json(directory, INVENTORY_OUTPUT, inventory_document(locations)))
    if units is not None:
        result.written.append(write_json(directory, PRODUCTS_OUTPUT, products_document(units)))
    return result


def report(result, check_only, stdout, stderr):
    for warning in result.warnings:
        print(warning, file=stderr)
    if not result.ok:
        for error in sorted(result.errors, key=lambda item: (item.file, item.row or 0)):
            print(error, file=stderr)
        files = len({error.file for error in result.errors})
        print(f"Validation failed: {len(result.errors)} error(s) in {files} file(s). No JSON files were written.",
              file=stderr)
        return 1
    counts = []
    if result.locations:
        counts.append(f"{result.locations} location(s)")
    if result.products:
        counts.append(f"{result.products} product(s)")
    if check_only:
        print(f"Validation passed: {' and '.join(counts)}. No files were written (--check).", file=stdout)
    else:
        print(f"Import succeeded: {' and '.join(counts)}.", file=stdout)
        for path in result.written:
            print(f"Wrote {path}", file=stdout)
    return 0


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = argparse.ArgumentParser(
        description="Validate inventory and product CSV files and generate Rackonaut Mock SAP JSON.")
    parser.add_argument("--inventory", type=Path, help="Inventory CSV with columns: " + ",".join(INVENTORY_COLUMNS))
    parser.add_argument("--products", type=Path, help="Product CSV with columns: " + ",".join(PRODUCT_COLUMNS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory for generated JSON (default: .rackonaut-data/inventory-import).")
    parser.add_argument("--check", action="store_true", help="Validate only; do not write any files.")
    args = parser.parse_args(argv)
    if args.inventory is None and args.products is None:
        parser.error("provide --inventory, --products, or both")
    result = run_import(args.inventory, args.products, args.output_dir, args.check)
    return report(result, args.check, stdout, stderr)


if __name__ == "__main__":
    sys.exit(main())
