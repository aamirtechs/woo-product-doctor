"""Tests for woo-product-doctor."""

import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from woo_product_doctor import (
    InputError,
    audit_products,
    gtin_check_digit,
    load_products,
    main,
    parse_money,
    validate_gtin,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "sample.csv"
CLEAN = ROOT / "examples" / "clean.csv"
INVALID = ROOT / "examples" / "invalid.csv"
SCRIPT = ROOT / "woo_product_doctor.py"

HEADER = ("ID,Type,SKU,Name,Published,Short description,Description,"
          "Regular price,Sale price,Categories,Images,GTIN\n")

LONG_DESC = ("This sturdy blue widget is built for everyday use around "
             "the home and the workshop, with a solid steel body and a "
             "comfortable grip that lasts for years.")
# LONG_DESC has 28 words, above the default 20 word threshold.
TWENTY_WORDS = ("one two three four five six seven eight nine ten eleven "
                "twelve thirteen fourteen fifteen sixteen seventeen "
                "eighteen nineteen twenty")
NINETEEN_WORDS = ("one two three four five six seven eight nine ten eleven "
                  "twelve thirteen fourteen fifteen sixteen seventeen "
                  "eighteen nineteen")


def csv_text(rows):
    return HEADER + "".join(rows)


def one_product(product_id="101", ptype="simple", sku="WID-001",
                name="Blue Widget", published="1",
                short="A sturdy blue widget.",
                description=LONG_DESC, regular="19.99", sale="",
                categories="Tools",
                image="https://example.com/images/blue-widget.jpg",
                gtin="5901234123457"):
    return (f'{product_id},{ptype},{sku},{name},{published},'
            f'"{short}","{description}",{regular},{sale},'
            f'"{categories}","{image}",{gtin}\n')


def audit(text, min_words=20):
    return audit_products(load_products(text), min_words)


def checks(report):
    return [(item["product_id"], item["check"], item["severity"])
            for item in report["findings"]]


def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True, cwd=ROOT)


class TestGtin(unittest.TestCase):
    def test_valid_gtin13(self):
        self.assertEqual(validate_gtin("5901234123457"),
                         ("5901234123457", None))

    def test_valid_gtin12(self):
        self.assertEqual(validate_gtin("036000291452"),
                         ("036000291452", None))

    def test_valid_gtin8(self):
        self.assertEqual(validate_gtin("96385074"), ("96385074", None))

    def test_valid_gtin14(self):
        self.assertEqual(validate_gtin("15901234123454"),
                         ("15901234123454", None))

    def test_bad_checksum_gtin13(self):
        normalized, problem = validate_gtin("5901234123456")
        self.assertIsNone(normalized)
        self.assertIn("check digit", problem)

    def test_bad_checksum_gtin12(self):
        normalized, problem = validate_gtin("036000291453")
        self.assertIsNone(normalized)
        self.assertIn("check digit", problem)

    def test_wrong_length_9_digits(self):
        normalized, problem = validate_gtin("590123412")
        self.assertIsNone(normalized)
        self.assertIn("9 digits", problem)

    def test_wrong_length_15_digits(self):
        normalized, problem = validate_gtin("590123412345678")
        self.assertIsNone(normalized)
        self.assertIn("15 digits", problem)

    def test_non_digit_characters(self):
        normalized, problem = validate_gtin("59012341234AB")
        self.assertIsNone(normalized)
        self.assertIn("digits only", problem)

    def test_spaces_and_hyphens_stripped(self):
        self.assertEqual(validate_gtin("5901 2341 2345 7"),
                         ("5901234123457", None))
        self.assertEqual(validate_gtin("5901-2341-2345-7"),
                         ("5901234123457", None))

    def test_empty_gtin_is_fine(self):
        self.assertEqual(validate_gtin(""), (None, None))
        self.assertEqual(validate_gtin(None), (None, None))

    def test_check_digit_known_values(self):
        self.assertEqual(gtin_check_digit("590123412345"), 7)
        self.assertEqual(gtin_check_digit("03600029145"), 2)
        self.assertEqual(gtin_check_digit("9638507"), 4)


class TestMoney(unittest.TestCase):
    def test_currency_symbol_and_commas(self):
        self.assertEqual(parse_money("$1,234.56", "total", "x"),
                         Decimal("1234.56"))

    def test_rounding_half_up(self):
        self.assertEqual(parse_money("10.005", "total", "x"),
                         Decimal("10.01"))

    def test_bad_amount_raises(self):
        with self.assertRaises(InputError):
            parse_money("not-a-price", "total", "x")


class TestColumns(unittest.TestCase):
    def test_missing_id_column(self):
        text = "Name,Type\nBlue Widget,simple\n"
        with self.assertRaises(InputError) as caught:
            load_products(text)
        self.assertIn("id", str(caught.exception))

    def test_missing_name_column(self):
        text = "ID,Type\n101,simple\n"
        with self.assertRaises(InputError) as caught:
            load_products(text)
        self.assertIn("name", str(caught.exception))

    def test_aliases_accepted(self):
        text = ("Product ID,Product Name,Type,SKU,Published,Description,"
                "Regular Price,Images,Barcode\n"
                f'201,Blue Widget,simple,WID-101,1,"{LONG_DESC}",19.99,'
                "https://example.com/images/blue.jpg,5901234123457\n")
        report = audit(text)
        self.assertEqual(report["findings"], [])

    def test_missing_optional_columns_skipped(self):
        text = "ID,Name,Type,SKU\n101,Blue Widget,simple,WID-001\n"
        report = audit(text)
        self.assertEqual(report["findings"], [])

    def test_bom_handled(self):
        report = audit("\ufeff" + csv_text([one_product()]))
        self.assertEqual(report["findings"], [])

    def test_blank_lines_skipped(self):
        report = audit(csv_text([one_product(), "\n"]))
        self.assertEqual(report["total_products"], 1)

    def test_missing_product_id_row(self):
        text = csv_text([one_product(product_id="")])
        with self.assertRaises(InputError) as caught:
            load_products(text)
        self.assertIn("id", str(caught.exception))

    def test_bad_price_exits_with_product_id(self):
        with self.assertRaises(InputError) as caught:
            load_products(INVALID.read_text())
        self.assertIn("301", str(caught.exception))


class TestSkuChecks(unittest.TestCase):
    def test_duplicate_sku_second_row_only(self):
        report = audit(csv_text([
            one_product(),
            one_product(product_id="102", gtin="036000291452"),
        ]))
        self.assertEqual(checks(report),
                         [("102", "duplicate sku", "error")])

    def test_duplicate_sku_case_insensitive(self):
        report = audit(csv_text([
            one_product(),
            one_product(product_id="102", sku="wid-001",
                        gtin="036000291452"),
        ]))
        self.assertEqual(checks(report),
                         [("102", "duplicate sku", "error")])

    def test_missing_sku_simple_is_error(self):
        report = audit(csv_text([one_product(sku="")]))
        self.assertEqual(checks(report),
                         [("101", "missing sku", "error")])

    def test_missing_sku_variation_is_warning(self):
        report = audit(csv_text([
            one_product(ptype="variation", sku="", regular="14.99")]))
        self.assertEqual(checks(report),
                         [("101", "missing sku", "warning")])

    def test_missing_sku_variable_is_warning(self):
        report = audit(csv_text([
            one_product(ptype="variable", sku="")]))
        self.assertEqual(checks(report),
                         [("101", "missing sku", "warning")])


class TestImageChecks(unittest.TestCase):
    def test_missing_image_published_is_error(self):
        report = audit(csv_text([one_product(image="")]))
        self.assertEqual(checks(report),
                         [("101", "missing image", "error")])

    def test_missing_image_draft_is_warning(self):
        report = audit(csv_text([one_product(image="", published="0")]))
        self.assertEqual(checks(report),
                         [("101", "missing image", "warning")])

    def test_placeholder_filename_is_error(self):
        report = audit(csv_text([one_product(
            image="https://example.com/images/woocommerce-placeholder.png")]))
        self.assertEqual(checks(report),
                         [("101", "placeholder image", "error")])

    def test_placeholder_host_is_error(self):
        report = audit(csv_text([one_product(
            image="https://placehold.co/600x400")]))
        self.assertEqual(checks(report),
                         [("101", "placeholder image", "error")])

    def test_placeholder_draft_is_warning(self):
        report = audit(csv_text([one_product(
            image="https://via.placeholder.com/300", published="0")]))
        self.assertEqual(checks(report),
                         [("101", "placeholder image", "warning")])

    def test_multiple_images_one_placeholder(self):
        report = audit(csv_text([one_product(
            image="https://example.com/images/blue.jpg, "
                  "https://dummyimage.com/600x400")]))
        self.assertEqual(checks(report),
                         [("101", "placeholder image", "error")])

    def test_real_image_passes(self):
        report = audit(csv_text([one_product()]))
        self.assertEqual(report["findings"], [])

    def test_variation_skips_image_check(self):
        report = audit(csv_text([
            one_product(ptype="variation", image="", regular="14.99",
                        short="", description="")]))
        self.assertEqual(report["findings"], [])


class TestDescriptionChecks(unittest.TestCase):
    def test_missing_description_published_is_error(self):
        report = audit(csv_text([one_product(short="", description="")]))
        self.assertEqual(checks(report),
                         [("101", "missing description", "error")])

    def test_missing_description_draft_is_warning(self):
        report = audit(csv_text([
            one_product(short="", description="", published="0")]))
        self.assertEqual(checks(report),
                         [("101", "missing description", "warning")])

    def test_thin_description_warning_with_count(self):
        report = audit(csv_text([
            one_product(description="Short text here only.")]))
        self.assertEqual(checks(report),
                         [("101", "thin description", "warning")])
        self.assertIn("4 words", report["findings"][0]["message"])

    def test_description_exactly_at_threshold_passes(self):
        report = audit(csv_text([
            one_product(description=TWENTY_WORDS)]))
        self.assertEqual(report["findings"], [])

    def test_description_one_below_threshold_warns(self):
        report = audit(csv_text([
            one_product(description=NINETEEN_WORDS)]))
        self.assertEqual(checks(report),
                         [("101", "thin description", "warning")])

    def test_short_description_fallback(self):
        report = audit(csv_text([
            one_product(description="", short=LONG_DESC)]))
        self.assertEqual(report["findings"], [])

    def test_short_description_fallback_can_be_thin(self):
        report = audit(csv_text([
            one_product(description="", short="A short blurb.")]))
        self.assertEqual(checks(report),
                         [("101", "thin description", "warning")])

    def test_variation_skips_description_check(self):
        report = audit(csv_text([
            one_product(ptype="variation", short="", description="",
                        regular="14.99")]))
        self.assertEqual(report["findings"], [])


class TestPriceChecks(unittest.TestCase):
    def test_missing_price_simple_is_error(self):
        report = audit(csv_text([one_product(regular="")]))
        self.assertEqual(checks(report),
                         [("101", "missing or zero price", "error")])

    def test_zero_price_is_error(self):
        report = audit(csv_text([one_product(regular="0.00")]))
        self.assertEqual(checks(report),
                         [("101", "missing or zero price", "error")])

    def test_grouped_no_price_skipped(self):
        report = audit(csv_text([one_product(ptype="grouped", regular="")]))
        self.assertEqual(report["findings"], [])

    def test_variable_no_price_skipped(self):
        report = audit(csv_text([one_product(ptype="variable", regular="")]))
        self.assertEqual(report["findings"], [])

    def test_variation_missing_price_is_error(self):
        report = audit(csv_text([
            one_product(ptype="variation", regular="")]))
        self.assertEqual(checks(report),
                         [("101", "variation missing price", "error")])

    def test_variation_zero_price_is_error(self):
        report = audit(csv_text([
            one_product(ptype="variation", regular="0.00")]))
        self.assertEqual(checks(report),
                         [("101", "variation missing price", "error")])

    def test_sale_above_regular_is_error(self):
        report = audit(csv_text([one_product(sale="24.99")]))
        self.assertEqual(checks(report),
                         [("101", "sale above regular price", "error")])

    def test_sale_equal_to_regular_passes(self):
        report = audit(csv_text([one_product(sale="19.99")]))
        self.assertEqual(report["findings"], [])

    def test_sale_below_regular_passes(self):
        report = audit(csv_text([one_product(sale="14.99")]))
        self.assertEqual(report["findings"], [])

    def test_negative_regular_price_is_error(self):
        report = audit(csv_text([one_product(regular="-5.00")]))
        self.assertEqual(checks(report),
                         [("101", "negative price", "error")])

    def test_negative_sale_price_is_error(self):
        report = audit(csv_text([one_product(sale="-1.00")]))
        self.assertEqual(checks(report),
                         [("101", "negative price", "error")])


class TestGtinChecks(unittest.TestCase):
    def test_invalid_gtin_checksum_is_error(self):
        report = audit(csv_text([one_product(gtin="5901234123456")]))
        self.assertEqual(checks(report),
                         [("101", "invalid gtin", "error")])

    def test_invalid_gtin_length_is_error(self):
        report = audit(csv_text([one_product(gtin="123456789")]))
        self.assertEqual(checks(report),
                         [("101", "invalid gtin", "error")])

    def test_duplicate_gtin_second_row_only(self):
        report = audit(csv_text([
            one_product(),
            one_product(product_id="102", sku="WID-002"),
        ]))
        self.assertEqual(checks(report),
                         [("102", "duplicate gtin", "error")])

    def test_empty_gtin_is_fine(self):
        report = audit(csv_text([one_product(gtin="")]))
        self.assertEqual(report["findings"], [])


class TestCategoryChecks(unittest.TestCase):
    def test_uncategorised_empty_is_warning(self):
        report = audit(csv_text([one_product(categories="")]))
        self.assertEqual(checks(report),
                         [("101", "uncategorised product", "warning")])

    def test_uncategorised_default_category_is_warning(self):
        report = audit(csv_text([one_product(categories="Uncategorized")]))
        self.assertEqual(checks(report),
                         [("101", "uncategorised product", "warning")])

    def test_real_category_passes(self):
        report = audit(csv_text([one_product()]))
        self.assertEqual(report["findings"], [])

    def test_variation_skips_category_check(self):
        report = audit(csv_text([
            one_product(ptype="variation", categories="", regular="14.99")]))
        self.assertEqual(report["findings"], [])


class TestSamples(unittest.TestCase):
    def test_sample_totals(self):
        report = audit(SAMPLE.read_text())
        self.assertEqual(report["total_products"], 17)
        self.assertEqual(report["error_count"], 11)
        self.assertEqual(report["warning_count"], 5)
        self.assertEqual(len(report["findings"]), 16)
        self.assertEqual(report["status_counts"],
                         {"published": 16, "draft": 1})
        self.assertEqual(report["type_counts"],
                         {"simple": 14, "variable": 1, "variation": 2})

    def test_clean_sample_has_no_findings(self):
        report = audit(CLEAN.read_text())
        self.assertEqual(report["total_products"], 3)
        self.assertEqual(report["findings"], [])

    def test_sample_finding_order(self):
        report = audit(SAMPLE.read_text())
        first = report["findings"][0]
        self.assertEqual((first["product_id"], first["check"]),
                         ("102", "thin description"))


class TestCli(unittest.TestCase):
    def test_text_output_contains_counts(self):
        result = run_cli(str(SAMPLE))
        self.assertEqual(result.returncode, 0)
        self.assertIn("Products: 17 total", result.stdout)
        self.assertIn("Findings: 16 (11 errors, 5 warnings)", result.stdout)
        self.assertIn("[error] product 103 (Blue Widget Copy)", result.stdout)

    def test_json_output_structure(self):
        result = run_cli(str(SAMPLE), "--json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["total_products"], 17)
        self.assertEqual(data["error_count"], 11)
        self.assertEqual(data["warning_count"], 5)
        self.assertEqual(len(data["findings"]), 16)
        self.assertEqual(data["findings"][0]["check"], "thin description")
        self.assertEqual(data["type_counts"]["variation"], 2)

    def test_check_fails_on_sample(self):
        result = run_cli(str(SAMPLE), "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CHECK FAILED: 11 error(s), 5 warning(s)",
                      result.stdout)

    def test_check_passes_on_clean(self):
        result = run_cli(str(CLEAN), "--check")
        self.assertEqual(result.returncode, 0)
        self.assertIn("CHECK PASSED: no error findings", result.stdout)

    def test_strict_fails_on_warnings_only(self):
        text = csv_text([one_product(description="Short text here only.")])
        result = run_cli("-", "--check", "--strict", stdin=text)
        self.assertEqual(result.returncode, 1)
        self.assertIn("CHECK FAILED: 0 error(s), 1 warning(s)",
                      result.stdout)

    def test_check_passes_warnings_only_without_strict(self):
        text = csv_text([one_product(description="Short text here only.")])
        result = run_cli("-", "--check", stdin=text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("CHECK PASSED: no error findings", result.stdout)

    def test_status_filter_published(self):
        result = run_cli(str(SAMPLE), "--status", "published")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Products: 16 total", result.stdout)
        self.assertIn("Findings: 14 (11 errors, 3 warnings)", result.stdout)

    def test_status_filter_draft(self):
        result = run_cli(str(SAMPLE), "--status", "draft")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Products: 1 total", result.stdout)
        self.assertIn("Findings: 2 (0 errors, 2 warnings)", result.stdout)

    def test_min_words_clears_thin_warnings(self):
        result = run_cli(str(SAMPLE), "--min-words", "5")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Findings: 15 (11 errors, 4 warnings)", result.stdout)

    def test_min_words_negative_exits_2(self):
        result = run_cli(str(SAMPLE), "--min-words", "-1")
        self.assertEqual(result.returncode, 2)

    def test_stdin_input(self):
        result = run_cli("-", stdin=SAMPLE.read_text())
        self.assertEqual(result.returncode, 0)
        self.assertIn("WooCommerce products audit: stdin", result.stdout)
        self.assertIn("Findings: 16 (11 errors, 5 warnings)", result.stdout)

    def test_module_run(self):
        result = subprocess.run(
            [sys.executable, "-m", "woo_product_doctor", str(CLEAN),
             "--check"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0)
        self.assertIn("CHECK PASSED", result.stdout)

    def test_missing_file_exits_2(self):
        result = run_cli("no-such-file.csv")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error: cannot read", result.stderr)

    def test_invalid_csv_exits_2(self):
        result = run_cli(str(INVALID))
        self.assertEqual(result.returncode, 2)
        self.assertIn("product 301", result.stderr)


if __name__ == "__main__":
    unittest.main()
