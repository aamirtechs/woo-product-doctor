"""woo-product-doctor: audit a WooCommerce products CSV export.

Reads a WooCommerce products CSV export and checks every product
for common catalog problems, offline:

* duplicate SKUs
* missing SKUs
* missing or placeholder images
* missing or thin descriptions (below a word threshold)
* missing or zero prices
* sale price above regular price
* invalid or duplicate GTINs (with GS1 check-digit validation
  for GTIN-8, GTIN-12, GTIN-13, and GTIN-14)
* uncategorised products
* variations with missing prices

Money uses Decimal and is rounded to cents, so float errors never
leak into a report.

Input format: a CSV file with a header row. Column names are matched
case-insensitively, and common WooCommerce export variants are
accepted. Required columns:

    id: "ID", "Product ID", or "Product ID"
    name: "Name", "Product Name", or "Title"

Optional columns (a check is skipped when its column is absent):

    type: "Type" or "Product Type" (simple, variable, variation,
        grouped, external; defaults to simple)
    published: "Published", "Status", or "Product Status"
        (1, true, yes, or published means published; 0, false,
        no, or draft means draft)
    sku: "SKU"
    short_description: "Short Description", "Short Description",
        or "Excerpt"
    description: "Description", "Long Description", or
        "Product Description"
    regular_price: "Regular Price", "Regular Price", or "Price"
    sale_price: "Sale Price" or "Sale Price"
    categories: "Categories", "Category", or "Product Categories"
    images: "Images", "Image", "Product Images", or "Image URL"
    gtin: "GTIN", "Barcode", "EAN", "UPC", "GTIN-8", "GTIN-12",
        "GTIN-13", "GTIN-14", "Meta: _gtin", or "Meta: gtin"

Rules:

* A duplicate SKU is an error on the second and later rows. The
  comparison is case-insensitive, so WID-001 and wid-001 count
  as the same SKU.
* A missing SKU is an error for simple and external products and
  a warning for variable, grouped, and variation products.
* A published product with no image is an error; a draft product
  with no image is a warning. A placeholder image (a URL
  containing "placeholder", or a known placeholder host such as
  placehold.co, via.placeholder.com, dummyimage.com, or
  picsum.photos) is an error for a published product and a
  warning for a draft. Variations are not checked for images:
  they inherit the parent product image.
* A product with no description text at all is an error when
  published and a warning when a draft. Description text is the
  Description column when it is non-empty, otherwise the Short
  Description column. A description below --min-words (default
  20) is a warning. Variations are not checked for descriptions.
* A simple or external product with a missing or zero regular
  price is an error. A variation with a missing or zero regular
  price is an error under its own check, "variation missing
  price". Variable and grouped products have no price of their
  own, so they are skipped. A negative regular or sale price is
  an error.
* A sale price above the regular price is an error. A sale price
  equal to the regular price passes.
* A GTIN must be 8, 12, 13, or 14 digits after spaces and hyphens
  are stripped, and its final digit must match the GS1 mod-10
  check digit computed from the other digits. A GTIN that fails
  any of those rules is an error. A GTIN that appears on more
  than one product is an error on the second and later rows.
  An empty GTIN cell is fine: GTINs are optional.
* A product with no categories, or with only the default
  "Uncategorized" category, is a warning. Variations are not
  checked for categories.
* With --check, exit 1 when any error finding exists. With
  --strict, warnings fail the check too. Otherwise exit 0.
* Exit 2 means bad input: missing file, missing required columns,
  a row with a missing product id, a bad price, or a bad option
  value. The error goes to stderr.

Usage:

    python3 woo_product_doctor.py examples/sample.csv
    python3 woo_product_doctor.py examples/sample.csv --json
    python3 woo_product_doctor.py examples/sample.csv --check
    python3 woo_product_doctor.py examples/sample.csv --min-words 10
    python3 woo_product_doctor.py examples/sample.csv --status draft
    cat examples/sample.csv | python3 woo_product_doctor.py -
"""

import argparse
import csv
import io
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

__version__ = "1.0.0"

CENT = Decimal("0.01")
CURRENCY_CHARS = "$£€"
DEFAULT_MIN_WORDS = 20
GTIN_LENGTHS = {8, 12, 13, 14}
PLACEHOLDER_HOSTS = {
    "placehold.co",
    "placehold.it",
    "via.placeholder.com",
    "dummyimage.com",
    "picsum.photos",
    "loremflickr.com",
    "placekitten.com",
}

COLUMN_ALIASES = {
    "id": {"id", "product id", "product_id"},
    "name": {"name", "product name", "title"},
    "type": {"type", "product type"},
    "published": {"published", "status", "product status"},
    "sku": {"sku"},
    "short_description": {"short description", "short_description", "excerpt"},
    "description": {"description", "long description", "product description"},
    "regular_price": {"regular price", "regular_price", "price"},
    "sale_price": {"sale price", "sale_price"},
    "categories": {"categories", "category", "product categories"},
    "images": {"images", "image", "product images", "image url"},
    "gtin": {"gtin", "barcode", "ean", "upc", "gtin-8", "gtin-12",
             "gtin-13", "gtin-14", "meta: _gtin", "meta: gtin",
             "meta: _barcode", "meta: barcode"},
}

CHECKS = [
    "duplicate sku",
    "missing sku",
    "missing image",
    "placeholder image",
    "missing description",
    "thin description",
    "missing or zero price",
    "variation missing price",
    "sale above regular price",
    "negative price",
    "invalid gtin",
    "duplicate gtin",
    "uncategorised product",
]

PRICED_TYPES = {"simple", "external"}
SKU_ERROR_TYPES = {"simple", "external"}


class InputError(ValueError):
    """Raised for any bad input that should exit 2."""


def parse_money(value, field, label):
    if isinstance(value, bool):
        raise InputError(f"{label}: {field} must be a number, got {value!r}")
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise InputError(f"{label}: {field} is not a valid amount: {value!r}")
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        for symbol in CURRENCY_CHARS:
            text = text.replace(symbol, "")
        text = text.strip()
        if not text:
            raise InputError(f"{label}: {field} must not be empty")
        try:
            return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise InputError(f"{label}: {field} is not a valid amount: {value!r}")
    raise InputError(f"{label}: {field} must be a number, got {value!r}")


def parse_optional_money(value, field, label):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return parse_money(value, field, label)


def normalize_published(raw):
    text = raw.strip().lower()
    if text in {"1", "true", "yes", "published", "publish"}:
        return "published"
    if text in {"0", "false", "no", "draft"}:
        return "draft"
    if text in {"private", "pending"}:
        return text
    return text or "published"


def normalize_type(raw):
    text = raw.strip().lower()
    return text or "simple"


def word_count(text):
    return len(text.split())


def split_cells(cell):
    if cell is None:
        return []
    return [part.strip() for part in str(cell).split(",") if part.strip()]


def is_placeholder_image(url):
    lowered = url.strip().lower()
    if "placeholder" in lowered:
        return True
    try:
        host = urlparse(lowered).netloc
    except ValueError:
        return False
    if host.startswith("www."):
        host = host[4:]
    return host in PLACEHOLDER_HOSTS


def gtin_check_digit(body):
    """Return the GS1 mod-10 check digit for the digits in body."""
    total = 0
    for index, char in enumerate(reversed(body)):
        total += int(char) * (3 if index % 2 == 0 else 1)
    return (10 - total % 10) % 10


def validate_gtin(raw):
    """Return (normalized, problem) for a GTIN cell.

    normalized is the digits-only GTIN when it is valid, else None.
    problem is a short reason when it is invalid, else None.
    An empty cell returns (None, None): GTINs are optional.
    """
    if raw is None:
        return None, None
    text = str(raw).strip().replace(" ", "").replace("-", "")
    if not text:
        return None, None
    if not text.isdigit():
        return None, "GTIN must contain digits only"
    if len(text) not in GTIN_LENGTHS:
        return None, (f"GTIN must be 8, 12, 13, or 14 digits, "
                      f"got {len(text)} digits")
    if str(gtin_check_digit(text[:-1])) != text[-1]:
        return None, "GTIN check digit does not match"
    return text, None


def resolve_columns(fieldnames):
    if not fieldnames:
        raise InputError("CSV has no header row")
    lookup = {}
    for raw_name in fieldnames:
        if raw_name is None:
            continue
        lookup[raw_name.strip().lower()] = raw_name
    resolved = {}
    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                resolved[logical] = lookup[alias]
                break
    missing = [name for name in ("id", "name") if name not in resolved]
    if missing:
        raise InputError(f"missing required column(s): {', '.join(missing)}")
    return resolved


def normalize_product(row, columns, index):
    label = f"row {index}"
    product_id = (row.get(columns["id"]) or "").strip()
    if not product_id:
        raise InputError(f"{label}: missing required field 'id'")
    label = f"product {product_id}"
    name = ""
    if "name" in columns:
        name = (row.get(columns["name"]) or "").strip()
    if not name:
        raise InputError(f"{label}: missing required field 'name'")
    product_type = "simple"
    if "type" in columns:
        product_type = normalize_type(str(row.get(columns["type"]) or ""))
    published = "published"
    if "published" in columns:
        published = normalize_published(str(row.get(columns["published"]) or ""))
    sku = ""
    if "sku" in columns:
        sku = (row.get(columns["sku"]) or "").strip()
    short_description = ""
    if "short_description" in columns:
        short_description = (row.get(columns["short_description"]) or "").strip()
    description = ""
    if "description" in columns:
        description = (row.get(columns["description"]) or "").strip()
    regular_price = None
    if "regular_price" in columns:
        regular_price = parse_optional_money(
            row.get(columns["regular_price"]), "regular_price", label)
    sale_price = None
    if "sale_price" in columns:
        sale_price = parse_optional_money(
            row.get(columns["sale_price"]), "sale_price", label)
    categories = []
    if "categories" in columns:
        categories = split_cells(row.get(columns["categories"]))
    images = []
    if "images" in columns:
        images = split_cells(row.get(columns["images"]))
    gtin_raw = ""
    if "gtin" in columns:
        gtin_raw = (row.get(columns["gtin"]) or "").strip()
    return {
        "id": product_id,
        "name": name,
        "type": product_type,
        "published": published,
        "sku": sku,
        "short_description": short_description,
        "description": description,
        "regular_price": regular_price,
        "sale_price": sale_price,
        "categories": categories,
        "images": images,
        "gtin_raw": gtin_raw,
        # Logical column names actually present in the CSV. Checks
        # for an absent column are skipped, so a minimal export is
        # never punished for columns it never had.
        "columns_present": frozenset(columns.keys()),
    }


def load_products(text):
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        columns = resolve_columns(reader.fieldnames)
        products = []
        for index, row in enumerate(reader, start=2):
            if row is None:
                continue
            if all(value is None or not str(value).strip()
                   for value in row.values()):
                continue
            products.append(normalize_product(row, columns, index))
        return products
    except csv.Error as exc:
        raise InputError(f"invalid CSV: {exc}")


def audit_products(products, min_words):
    findings = []
    seen_skus = set()
    seen_gtins = set()
    status_counts = {}
    type_counts = {}
    for product in products:
        status_counts[product["published"]] = status_counts.get(product["published"], 0) + 1
        type_counts[product["type"]] = type_counts.get(product["type"], 0) + 1
        product_id = product["id"]
        name = product["name"]
        is_published = product["published"] == "published"
        is_variation = product["type"] == "variation"

        def add(check, severity, message):
            findings.append({
                "product_id": product_id,
                "name": name,
                "check": check,
                "severity": severity,
                "message": message,
            })

        sku = product["sku"]
        if "sku" in product["columns_present"]:
            if sku:
                key = sku.lower()
                if key in seen_skus:
                    add("duplicate sku", "error",
                        f"SKU {sku} appears more than once in the export")
                else:
                    seen_skus.add(key)
            else:
                severity = "error" if product["type"] in SKU_ERROR_TYPES else "warning"
                add("missing sku", severity, "product has no SKU")

        if (not is_variation
                and "images" in product["columns_present"]):
            if not product["images"]:
                severity = "error" if is_published else "warning"
                add("missing image", severity, "product has no image")
            else:
                placeholders = [url for url in product["images"]
                                if is_placeholder_image(url)]
                if placeholders:
                    severity = "error" if is_published else "warning"
                    add("placeholder image", severity,
                        f"image looks like a placeholder: {placeholders[0]}")

        if (not is_variation
                and ("description" in product["columns_present"]
                     or "short_description" in product["columns_present"])):
            description_text = product["description"] or product["short_description"]
            if not description_text:
                severity = "error" if is_published else "warning"
                add("missing description", severity,
                    "product has no description or short description")
            elif word_count(description_text) < min_words:
                count = word_count(description_text)
                add("thin description", "warning",
                    f"description has {count} word{'s' if count != 1 else ''}, "
                    f"below the {min_words} word threshold")

        regular = product["regular_price"]
        sale = product["sale_price"]
        has_prices = "regular_price" in product["columns_present"]
        if has_prices and regular is not None and regular < 0:
            add("negative price", "error",
                f"regular price is negative: {money_str(regular)}")
        if (has_prices and "sale_price" in product["columns_present"]
                and sale is not None and sale < 0):
            add("negative price", "error",
                f"sale price is negative: {money_str(sale)}")
        if has_prices and product["type"] in PRICED_TYPES:
            if regular is None or regular == 0:
                add("missing or zero price", "error",
                    "product has no regular price" if regular is None
                    else "regular price is zero")
        elif has_prices and product["type"] == "variation":
            if regular is None or regular == 0:
                add("variation missing price", "error",
                    "variation has no regular price" if regular is None
                    else "variation regular price is zero")
        if (has_prices and regular is not None and regular > 0
                and sale is not None and sale > regular):
            add("sale above regular price", "error",
                f"sale price {money_str(sale)} is above regular price "
                f"{money_str(regular)}")

        gtin, problem = validate_gtin(product["gtin_raw"])
        if problem is not None:
            add("invalid gtin", "error",
                f"GTIN {product['gtin_raw']!r} is invalid: {problem}")
        elif gtin is not None:
            if gtin in seen_gtins:
                add("duplicate gtin", "error",
                    f"GTIN {gtin} appears more than once in the export")
            else:
                seen_gtins.add(gtin)

        if (not is_variation
                and "categories" in product["columns_present"]):
            real_categories = [cat for cat in product["categories"]
                               if cat.lower() != "uncategorized"]
            if not real_categories:
                add("uncategorised product", "warning",
                    "product has no category")
    errors = sum(1 for item in findings if item["severity"] == "error")
    warnings = sum(1 for item in findings if item["severity"] == "warning")
    return {
        "min_words": min_words,
        "total_products": len(products),
        "status_counts": status_counts,
        "type_counts": type_counts,
        "findings": findings,
        "error_count": errors,
        "warning_count": warnings,
    }


def money_str(amount):
    return f"{amount:.2f}"


def format_text(report, source):
    lines = []
    lines.append(f"WooCommerce products audit: {source}")
    lines.append(f"Description word threshold: {report['min_words']} words")
    lines.append("")
    lines.append(f"Products: {report['total_products']} total")
    if report["status_counts"]:
        breakdown = ", ".join(
            f"{status}: {count}"
            for status, count in sorted(report["status_counts"].items()))
        lines.append(f"Statuses: {breakdown}")
    if report["type_counts"]:
        breakdown = ", ".join(
            f"{kind}: {count}"
            for kind, count in sorted(report["type_counts"].items()))
        lines.append(f"Types: {breakdown}")
    lines.append("")
    lines.append(f"Findings: {len(report['findings'])} "
                 f"({report['error_count']} errors, {report['warning_count']} warnings)")
    if report["findings"]:
        lines.append("")
        lines.append(f"{'Check':<26} {'Errors':>6} {'Warnings':>8}")
        for check in CHECKS:
            errors = sum(1 for item in report["findings"]
                         if item["check"] == check and item["severity"] == "error")
            warnings = sum(1 for item in report["findings"]
                           if item["check"] == check and item["severity"] == "warning")
            if errors or warnings:
                lines.append(f"{check:<26} {errors:>6} {warnings:>8}")
        lines.append("")
        lines.append("Findings:")
        for item in report["findings"]:
            lines.append(f"[{item['severity']}] product {item['product_id']} "
                         f"({item['name']}): {item['message']}")
    return "\n".join(lines) + "\n"


def report_to_json(report):
    return {
        "min_words": report["min_words"],
        "total_products": report["total_products"],
        "status_counts": report["status_counts"],
        "type_counts": report["type_counts"],
        "error_count": report["error_count"],
        "warning_count": report["warning_count"],
        "findings": report["findings"],
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="woo-product-doctor",
        description="Audit a WooCommerce products CSV export for common catalog problems.",
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="CSV file path, or '-' / omitted for stdin")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if any error finding exists")
    parser.add_argument("--strict", action="store_true",
                        help="With --check, also exit 1 on warnings")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS,
                        help=f"Minimum description words before a description counts as thin (default: {DEFAULT_MIN_WORDS})")
    parser.add_argument("--status", default=None,
                        help="Only audit products with this status, for example published or draft")
    args = parser.parse_args(argv)
    if args.min_words < 0:
        parser.error("--min-words must be zero or more")
    if args.status is not None:
        args.status = normalize_published(args.status)
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.input is None or args.input == "-":
            text = sys.stdin.read()
            source = "stdin"
        else:
            try:
                with open(args.input, "r", encoding="utf-8-sig", newline="") as handle:
                    text = handle.read()
            except OSError as exc:
                print(f"error: cannot read {args.input}: {exc.strerror or exc}", file=sys.stderr)
                return 2
            source = args.input
        products = load_products(text)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.status is not None:
        products = [product for product in products
                    if product["published"] == args.status]
    report = audit_products(products, args.min_words)
    if args.json:
        print(json.dumps(report_to_json(report), indent=2))
    else:
        print(format_text(report, source), end="")
    if args.check:
        failed = report["error_count"] > 0 or (args.strict and report["warning_count"] > 0)
        if failed:
            if not args.json:
                print(f"CHECK FAILED: {report['error_count']} error(s), "
                      f"{report['warning_count']} warning(s)")
            return 1
        if not args.json:
            print("CHECK PASSED: no error findings"
                  + (" and no warnings" if args.strict else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
