"""Tests for the standalone CSV inventory importer in scripts/inventory/import_csv.py."""

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "inventory" / "import_csv.py"
SAMPLES = TOOL.parent / "samples"
TEMPLATES = TOOL.parent / "templates"

spec = importlib.util.spec_from_file_location("inventory_import_csv", TOOL)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # jsonschema older than 4.0 has no Draft 2020-12 support.
    Draft202012Validator = None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


CONTRACT = read_json(ROOT / "contracts" / "openapi.json")
BASE_INVENTORY = read_json(ROOT / "test_data" / "expected_inventory.json")
EXTENSION = read_json(ROOT / "test_data" / "control_inventory_extension.json")
PRODUCTS = read_json(ROOT / "test_data" / "mock_sap_products.json")
INVENTORY_HEADER = "slot_id,pallet_id\n"
PRODUCT_HEADER = "hu_id,sku,product_name,batch,lifecycle_status,quality_status,stock_status\n"
PRODUCT_ROW = "P001,EL-440,Series 440 control relay,EL-2408,DISCONTINUED,RELEASED,ON_HAND\n"


class ImporterTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.out = self.tmp / "out"

    def csv(self, name, text, encoding="utf-8"):
        path = self.tmp / name
        path.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
        return path

    def inventory(self, rows, header=INVENTORY_HEADER):
        return self.csv("inventory.csv", header + rows)

    def products(self, rows, header=PRODUCT_HEADER):
        return self.csv("products.csv", header + rows)

    def run_import(self, inventory=None, products=None, **kwargs):
        kwargs.setdefault("output_dir", self.out)
        return importer.run_import(inventory, products, **kwargs)

    def issues(self, result):
        return [(issue.row, issue.field) for issue in result.errors]

    def assert_single_error(self, result, row, field, text):
        self.assertFalse(result.ok)
        self.assertEqual(self.issues(result), [(row, field)], [str(issue) for issue in result.errors])
        self.assertIn(text, result.errors[0].message)
        self.assertFalse(self.out.exists())


class ValidImportTests(ImporterTestCase):
    def test_valid_samples_reproduce_existing_backend_json(self):
        result = self.run_import(SAMPLES / "inventory_valid.csv", SAMPLES / "products_valid.csv")
        self.assertTrue(result.ok, [str(issue) for issue in result.errors])
        self.assertEqual(result.warnings, [])
        self.assertEqual((result.locations, result.products), (11, 9))
        self.assertEqual(sorted(path.name for path in result.written),
                         ["expected_inventory.json", "mock_sap_products.json"])
        inventory = read_json(self.out / "expected_inventory.json")
        self.assertEqual(inventory, {**BASE_INVENTORY,
                                     "locations": BASE_INVENTORY["locations"] + EXTENSION["locations"]})
        self.assertEqual(read_json(self.out / "mock_sap_products.json"), PRODUCTS)

    def test_valid_inventory_only(self):
        rows = "".join(f"{row['slot_id']},{row['pallet_id'] or ''}\n" for row in BASE_INVENTORY["locations"])
        result = self.run_import(inventory=self.inventory(rows))
        self.assertTrue(result.ok)
        self.assertEqual(read_json(self.out / "expected_inventory.json"), BASE_INVENTORY)
        self.assertFalse((self.out / "mock_sap_products.json").exists())

    def test_valid_products_only(self):
        result = self.run_import(products=SAMPLES / "products_valid.csv")
        self.assertTrue(result.ok)
        self.assertEqual(read_json(self.out / "mock_sap_products.json"), PRODUCTS)
        self.assertFalse((self.out / "expected_inventory.json").exists())

    def test_empty_pallet_means_location_expected_empty(self):
        self.run_import(inventory=self.inventory("A-01-04,\n"))
        self.assertEqual(read_json(self.out / "expected_inventory.json")["locations"],
                         [{"slot_id": "A-01-04", "pallet_id": None}])

    def test_columns_may_be_in_any_order_and_output_keeps_backend_key_order(self):
        result = self.run_import(inventory=self.inventory("P001,A-01-01\n", header="pallet_id,slot_id\n"))
        self.assertTrue(result.ok)
        text = (self.out / "expected_inventory.json").read_text(encoding="utf-8")
        self.assertLess(text.index('"slot_id"'), text.index('"pallet_id"'))

    def test_utf8_bom_quoted_fields_and_windows_line_endings_are_accepted(self):
        products = self.csv("products.csv", "﻿" + PRODUCT_HEADER.replace("\n", "\r\n")
                            + 'P001,EL-440,"Relay, series 440",EL-2408,ACTIVE,RELEASED,ON_HAND\r\n', encoding="utf-8")
        result = self.run_import(products=products)
        self.assertTrue(result.ok, [str(issue) for issue in result.errors])
        self.assertEqual(read_json(self.out / "mock_sap_products.json")["handling_units"][0]["product_name"],
                         "Relay, series 440")

    def test_unplaced_product_is_a_warning_not_an_error(self):
        result = self.run_import(self.inventory("A-01-01,P001\n"),
                                 self.products(PRODUCT_ROW + PRODUCT_ROW.replace("P001", "P002", 1)))
        self.assertTrue(result.ok)
        self.assertEqual([(w.severity, w.field) for w in result.warnings], [("warning", "hu_id")])
        self.assertIn("P002", result.warnings[0].message)


class OutputStructureTests(ImporterTestCase):
    def test_inventory_output_matches_contract_patterns(self):
        self.run_import(SAMPLES / "inventory_valid.csv")
        document = read_json(self.out / "expected_inventory.json")
        self.assertEqual(set(document), {"source", "locations"})
        self.assertEqual(document["source"], "mock_sap")
        for location in document["locations"]:
            self.assertEqual(set(location), {"slot_id", "pallet_id"})
            self.assertTrue(importer.SLOT_ID.match(location["slot_id"]))
            self.assertTrue(location["pallet_id"] is None or importer.PALLET_ID.match(location["pallet_id"]))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema 4.x is required for OpenAPI 3.1 schemas")
    def test_inventory_output_validates_against_openapi_inventory_schema(self):
        self.run_import(SAMPLES / "inventory_valid.csv")
        Draft202012Validator({"$ref": "#/components/schemas/Inventory",
                              "components": CONTRACT["components"]}).validate(
            read_json(self.out / "expected_inventory.json"))

    def test_product_output_matches_mock_sap_product_structure(self):
        self.run_import(products=SAMPLES / "products_valid.csv")
        document = read_json(self.out / "mock_sap_products.json")
        self.assertEqual(list(document), list(PRODUCTS))
        self.assertEqual(document["source"], PRODUCTS["source"])
        self.assertIs(document["synthetic"], True)
        expected_keys = list(PRODUCTS["handling_units"][0])
        for unit in document["handling_units"]:
            self.assertEqual(list(unit), expected_keys)
            self.assertIn(unit["lifecycle_status"], importer.LIFECYCLE_STATUSES)

    def test_contract_patterns_are_read_from_openapi(self):
        location = CONTRACT["components"]["schemas"]["ExpectedLocation"]["properties"]
        self.assertEqual(importer.SLOT_ID.pattern, location["slot_id"]["pattern"])
        self.assertEqual(importer.PALLET_ID.pattern, location["pallet_id"]["anyOf"][0]["pattern"])

    def test_supported_statuses_cover_repository_product_data(self):
        for unit in PRODUCTS["handling_units"]:
            self.assertIn(unit["lifecycle_status"], importer.LIFECYCLE_STATUSES)
            self.assertIn(unit["quality_status"], importer.QUALITY_STATUSES)
            self.assertIn(unit["stock_status"], importer.STOCK_STATUSES)

    def test_lifecycle_statuses_match_backend_intelligence_rules(self):
        source = (ROOT / "backend" / "intelligence.py").read_text(encoding="utf-8")
        for status in importer.LIFECYCLE_STATUSES:
            self.assertIn(f'"{status}"', source)


class FieldValidationTests(ImporterTestCase):
    def test_missing_required_values(self):
        self.assert_single_error(self.run_import(self.inventory(",P001\n")), 2, "slot_id", "Required value is empty")
        for column in importer.PRODUCT_COLUMNS:
            with self.subTest(column=column):
                values = dict(zip(importer.PRODUCT_COLUMNS, PRODUCT_ROW.strip().split(",")))
                values[column] = ""
                result = self.run_import(products=self.products(",".join(values.values()) + "\n"))
                self.assertIn((2, column), self.issues(result))

    def test_too_few_values_is_reported_per_missing_field(self):
        result = self.run_import(products=self.products("P001,EL-440\n"))
        self.assertEqual(self.issues(result), [(2, column) for column in importer.PRODUCT_COLUMNS[2:]])
        self.assertIn("too few columns", result.errors[0].message)

    def test_too_many_values(self):
        self.assert_single_error(self.run_import(self.inventory("A-01-01,P001,extra\n")), 2, None,
                                 "3 values but the header has 2 columns")

    def test_invalid_slot_ids(self):
        for value in ("A-1-01", "a-01-01", "A01-01", "AA-01-01", "A-01-001", "A_01_01"):
            with self.subTest(value=value):
                self.assert_single_error(self.run_import(self.inventory(f"{value},P001\n")), 2, "slot_id",
                                         "not a valid slot ID")

    def test_invalid_pallet_ids(self):
        for value in ("P1", "P0001", "p001", "X001", "PALLET-1", "null"):
            with self.subTest(value=value):
                self.assert_single_error(self.run_import(self.inventory(f"A-01-01,{value}\n")), 2, "pallet_id",
                                         "not a valid pallet ID")

    def test_invalid_handling_unit_id(self):
        self.assert_single_error(self.run_import(products=self.products(PRODUCT_ROW.replace("P001", "HU-001", 1))),
                                 2, "hu_id", "not a valid handling unit ID")

    def test_surrounding_spaces_are_rejected_not_trimmed(self):
        self.assert_single_error(self.run_import(self.inventory(" A-01-01,P001\n")), 2, "slot_id",
                                 "leading or trailing spaces")
        self.assert_single_error(self.run_import(products=self.products(PRODUCT_ROW.replace("EL-440", "EL-440 "))),
                                 2, "sku", "leading or trailing spaces")

    def test_unsupported_product_statuses(self):
        cases = (("DISCONTINUED", "RETIRED", "lifecycle_status"),
                 ("RELEASED", "QUARANTINE", "quality_status"),
                 ("ON_HAND", "IN_TRANSIT", "stock_status"))
        for valid, invalid, field in cases:
            with self.subTest(field=field):
                result = self.run_import(products=self.products(PRODUCT_ROW.replace(valid, invalid)))
                self.assert_single_error(result, 2, field, f"Unsupported status '{invalid}'")

    def test_lowercase_status_gets_a_hint_but_is_not_corrected(self):
        result = self.run_import(products=self.products(PRODUCT_ROW.replace("DISCONTINUED", "discontinued")))
        self.assert_single_error(result, 2, "lifecycle_status", "Did you mean DISCONTINUED?")


class DuplicateAndReferenceTests(ImporterTestCase):
    def test_duplicate_location(self):
        result = self.run_import(self.inventory("A-01-01,P001\nA-01-02,P002\nA-01-01,P003\n"))
        self.assert_single_error(result, 4, "slot_id", "Duplicate location A-01-01; it is already defined in row 2")

    def test_duplicate_location_with_identical_pallet_is_still_an_error(self):
        result = self.run_import(self.inventory("A-01-04,\nA-01-04,\n"))
        self.assert_single_error(result, 3, "slot_id", "Duplicate location A-01-04")

    def test_conflicting_pallet_assignment(self):
        result = self.run_import(self.inventory("A-01-01,P001\nA-01-02,P001\n"))
        self.assert_single_error(result, 3, "pallet_id", "pallet P001 is already assigned to A-01-01 in row 2")

    def test_several_empty_locations_are_not_a_conflict(self):
        self.assertTrue(self.run_import(self.inventory("A-01-01,\nA-01-02,\n")).ok)

    def test_duplicate_handling_unit(self):
        result = self.run_import(products=self.products(PRODUCT_ROW + PRODUCT_ROW))
        self.assert_single_error(result, 3, "hu_id", "Duplicate handling unit P001; it is already defined in row 2")

    def test_inventory_pallet_without_product_record(self):
        result = self.run_import(self.inventory("A-01-01,P001\nA-01-02,P002\n"), self.products(PRODUCT_ROW))
        self.assert_single_error(result, 3, "pallet_id", "Pallet P002 has no product record")
        self.assertEqual(result.errors[0].file, str(self.tmp / "inventory.csv"))

    def test_references_are_not_checked_for_a_single_file(self):
        self.assertTrue(self.run_import(self.inventory("A-01-01,P999\n")).ok)


class FileValidationTests(ImporterTestCase):
    def test_missing_file(self):
        result = self.run_import(self.tmp / "absent.csv")
        self.assertEqual(self.issues(result), [(None, None)])
        self.assertIn("File not found", result.errors[0].message)

    def test_directory_instead_of_file(self):
        self.assertIn("directory", self.run_import(self.tmp).errors[0].message)

    def test_empty_file_and_header_only(self):
        self.assertIn("empty", self.run_import(self.csv("inventory.csv", "")).errors[0].message)
        self.assertIn("no data rows", self.run_import(self.inventory("")).errors[0].message)

    def test_not_utf8(self):
        result = self.run_import(products=self.csv("products.csv", PRODUCT_HEADER + "P001,EL-440,Gr\xfc\xdfe,B,ACTIVE,RELEASED,ON_HAND\n",
                                                   encoding="latin-1"))
        self.assertIn("not valid UTF-8", result.errors[0].message)

    def test_malformed_quoting(self):
        result = self.run_import(self.inventory('A-01-01,"P001\n'))
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Malformed CSV", result.errors[0].message)

    def test_header_problems(self):
        cases = (
            ("slot_id\n", [(1, "pallet_id")], "missing"),
            ("slot_id,pallet_id,note\n", [(1, "note")], "Unknown column"),
            ("Slot_ID,pallet_id\n", [(1, "Slot_ID"), (1, "slot_id")], "Unknown column"),
            ("slot_id,pallet_id,slot_id\n", [(1, "slot_id")], "more than once"),
            ("slot_id;pallet_id\n", [(1, None)], "semicolons"),
        )
        for header, expected, text in cases:
            with self.subTest(header=header):
                result = self.run_import(self.inventory("A-01-01,P001\n", header=header))
                self.assertEqual(self.issues(result), expected, [str(issue) for issue in result.errors])
                self.assertIn(text, result.errors[0].message)


class ErrorReportingTests(ImporterTestCase):
    def test_multiple_errors_are_reported_in_one_run(self):
        result = self.run_import(SAMPLES / "inventory_invalid.csv", SAMPLES / "products_invalid.csv")
        inventory = str(SAMPLES / "inventory_invalid.csv")
        products = str(SAMPLES / "products_invalid.csv")
        found = [(issue.file, issue.row, issue.field) for issue in result.errors]
        self.assertEqual(sorted(found, key=lambda item: (item[0], item[1] or 0)), [
            (inventory, 3, "slot_id"),
            (inventory, 5, "slot_id"),
            (inventory, 6, "pallet_id"),
            (inventory, 7, "slot_id"),
            (inventory, 8, "pallet_id"),
            (inventory, 9, None),
            (inventory, 10, "pallet_id"),
            (products, 3, "lifecycle_status"),
            (products, 4, "sku"),
            (products, 5, "hu_id"),
            (products, 6, "hu_id"),
            (products, 6, "lifecycle_status"),
            (products, 7, "quality_status"),
        ])
        self.assertFalse(self.out.exists())

    def test_row_numbers_count_header_blank_lines_and_multiline_fields(self):
        text = PRODUCT_HEADER + "\n" + 'P001,EL-440,"Relay\nsecond line",EL-2408,ACTIVE,RELEASED,ON_HAND\n' \
            + "P002,MT-125,Bracket,MT-2611,RETIRED,RELEASED,ON_HAND\n"
        result = self.run_import(products=self.products(text[len(PRODUCT_HEADER):]))
        self.assertEqual(self.issues(result), [(5, "lifecycle_status")])

    def test_issue_text_contains_file_row_and_field(self):
        result = self.run_import(self.inventory("A-1-01,P001\n"))
        self.assertEqual(str(result.errors[0]),
                         f"ERROR: {self.tmp / 'inventory.csv'}, row 2, slot_id: 'A-1-01' is not a valid slot ID. "
                         "Use aisle letter, bay and level, e.g. A-01-02.")

    def test_one_invalid_file_blocks_output_for_both(self):
        result = self.run_import(SAMPLES / "inventory_valid.csv", self.products(PRODUCT_ROW.replace("ACTIVE", "X")
                                                                                .replace("DISCONTINUED", "X")))
        self.assertFalse(result.ok)
        self.assertEqual(result.written, [])
        self.assertFalse(self.out.exists())


class OutputDirectoryTests(ImporterTestCase):
    def test_output_directory_is_created(self):
        nested = self.tmp / "a" / "b"
        result = self.run_import(SAMPLES / "inventory_valid.csv", output_dir=nested)
        self.assertEqual(result.written, [nested / "expected_inventory.json"])

    def test_default_output_directory_is_git_ignored_project_data(self):
        self.assertEqual(importer.DEFAULT_OUTPUT_DIR, ROOT / ".rackonaut-data" / "inventory-import")
        self.assertIn(".rackonaut-data/", (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_failed_import_keeps_previous_output_untouched(self):
        self.run_import(SAMPLES / "inventory_valid.csv")
        before = (self.out / "expected_inventory.json").read_bytes()
        result = self.run_import(self.inventory("A-1-01,P001\n"))
        self.assertFalse(result.ok)
        self.assertEqual((self.out / "expected_inventory.json").read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.out.iterdir()), ["expected_inventory.json"])

    def test_successful_import_replaces_previous_output(self):
        self.run_import(SAMPLES / "inventory_valid.csv")
        self.run_import(self.inventory("A-01-01,P001\n"))
        self.assertEqual(read_json(self.out / "expected_inventory.json")["locations"],
                         [{"slot_id": "A-01-01", "pallet_id": "P001"}])

    def test_protected_repository_directories_are_refused(self):
        for directory in (ROOT / "test_data", ROOT / "contracts", ROOT / "backend", ROOT / "test_data" / "sub"):
            with self.subTest(directory=directory):
                result = self.run_import(SAMPLES / "inventory_valid.csv", output_dir=directory)
                self.assertFalse(result.ok)
                self.assertIn("Refusing to write", result.errors[0].message)
        self.assertFalse((ROOT / "test_data" / "sub").exists())

    def test_output_path_that_is_a_file_is_refused(self):
        target = self.csv("occupied", "x")
        result = self.run_import(SAMPLES / "inventory_valid.csv", output_dir=target)
        self.assertIn("not a directory", result.errors[0].message)

    def test_check_mode_writes_nothing(self):
        result = self.run_import(SAMPLES / "inventory_valid.csv", SAMPLES / "products_valid.csv", check_only=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.written, [])
        self.assertFalse(self.out.exists())

    def test_no_temporary_files_are_left(self):
        self.run_import(SAMPLES / "inventory_valid.csv", SAMPLES / "products_valid.csv")
        self.assertEqual(sorted(path.name for path in self.out.iterdir()),
                         ["expected_inventory.json", "mock_sap_products.json"])


class CommandLineTests(ImporterTestCase):
    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = importer.main([*map(str, args)], stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_success_exit_code_and_message(self):
        code, out, err = self.cli("--inventory", SAMPLES / "inventory_valid.csv",
                                  "--products", SAMPLES / "products_valid.csv", "--output-dir", self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Import succeeded: 11 location(s) and 9 product(s).", out)
        self.assertIn(str(self.out / "expected_inventory.json"), out)

    def test_failure_exit_code_and_report(self):
        code, out, err = self.cli("--inventory", SAMPLES / "inventory_invalid.csv", "--output-dir", self.out)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("row 3, slot_id: 'A-1-02' is not a valid slot ID", err)
        self.assertIn("Validation failed: 6 error(s) in 1 file(s). No JSON files were written.", err)

    def test_check_flag(self):
        code, out, _ = self.cli("--check", "--products", SAMPLES / "products_valid.csv", "--output-dir", self.out)
        self.assertEqual(code, 0)
        self.assertIn("Validation passed: 9 product(s). No files were written", out)
        self.assertFalse(self.out.exists())

    def test_input_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            importer.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_script_runs_as_a_standalone_process(self):
        completed = subprocess.run(
            [sys.executable, str(TOOL), "--inventory", str(SAMPLES / "inventory_valid.csv"),
             "--output-dir", str(self.out)],
            capture_output=True, text=True, check=False, cwd=self.tmp)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((self.out / "expected_inventory.json").is_file())


class RepositoryFilesTests(unittest.TestCase):
    def test_templates_contain_only_the_expected_headers(self):
        self.assertEqual((TEMPLATES / "inventory_template.csv").read_text(encoding="utf-8"), INVENTORY_HEADER)
        self.assertEqual((TEMPLATES / "products_template.csv").read_text(encoding="utf-8"), PRODUCT_HEADER)

    def test_importing_samples_does_not_touch_demo_data(self):
        demo = sorted((ROOT / "test_data").glob("*.json"))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in demo}
        with tempfile.TemporaryDirectory() as tmp:
            importer.run_import(SAMPLES / "inventory_valid.csv", SAMPLES / "products_valid.csv", output_dir=tmp)
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in demo}, before)


if __name__ == "__main__":
    unittest.main()
