# woo-product-doctor
**Live tool:** https://aamirtechs.github.io/woo-product-doctor/ (runs in your browser, no install)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/woo-product-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/woo-product-doctor/issues)

A zero-dependency Python CLI that audits a WooCommerce products CSV
export for common catalog problems, offline. It flags duplicate
SKUs, missing SKUs, missing or placeholder images, missing or thin
descriptions, missing or zero prices, sale prices above the regular
price, invalid or duplicate GTINs with GS1 check-digit validation,
uncategorised products, and variations with missing prices, and
doubles as a CI gate with `--check`.

A WooCommerce catalog is usually eyeballed in a spreadsheet, and a
duplicated SKU or a sale price higher than the regular price slips
through unnoticed until a feed is rejected or a customer is
overcharged. This tool reads the export, does the money math with
Decimal cents arithmetic, validates every GTIN check digit, and
prints every problem in one list.

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard library.

```bash
pip install woo-product-doctor
```

Or run it straight from the source checkout:

```bash
python3 woo_product_doctor.py examples/sample.csv
```

It also runs as a module:

```bash
python3 -m woo_product_doctor examples/sample.csv
```

## Input format

A CSV file with a header row. Column names are matched
case-insensitively, and common WooCommerce export variants are
accepted. Required columns:

| Field | Accepted headers |
| --- | --- |
| Product ID | `ID`, `Product ID` |
| Name | `Name`, `Product Name`, `Title` |

Optional columns (a check is skipped when its column is absent, so
a minimal export is never punished for columns it never had):

| Field | Accepted headers |
| --- | --- |
| Type | `Type`, `Product Type` |
| Published | `Published`, `Status`, `Product Status` |
| SKU | `SKU` |
| Short description | `Short Description`, `Excerpt` |
| Description | `Description`, `Long Description`, `Product Description` |
| Regular price | `Regular Price`, `Price` |
| Sale price | `Sale Price` |
| Categories | `Categories`, `Category`, `Product Categories` |
| Images | `Images`, `Image`, `Product Images`, `Image URL` |
| GTIN | `GTIN`, `Barcode`, `EAN`, `UPC`, `GTIN-8`, `GTIN-12`, `GTIN-13`, `GTIN-14`, `Meta: _gtin`, `Meta: gtin` |

Product types are `simple`, `variable`, `variation`, `grouped`,
and `external`, defaulting to `simple` when the Type column is
absent. Published status is normalized from `1`, `true`, `yes`,
or `published` to `published`, and from `0`, `false`, `no`, or
`draft` to `draft`, so `1` and `published` mean the same thing.
Amounts may carry a currency symbol and thousands commas, for
example `$1,234.56`. Images are a comma-separated list of URLs
inside one cell. Categories are a comma-separated list, with `>`
for hierarchy, for example `Tools > Widgets, Clothing`.

## Checks

| Check | Severity | Rule |
| --- | --- | --- |
| duplicate sku | error | A SKU appears more than once in the export (case-insensitive) |
| missing sku | error for simple/external, warning otherwise | A product has no SKU |
| missing image | error if published, warning if draft | A product has no image |
| placeholder image | error if published, warning if draft | An image URL contains `placeholder` or uses a known placeholder host (`placehold.co`, `placehold.it`, `via.placeholder.com`, `dummyimage.com`, `picsum.photos`) |
| missing description | error if published, warning if draft | No description and no short description |
| thin description | warning | Description text below `--min-words` (default 20) |
| missing or zero price | error | A simple or external product has no regular price, or a regular price of zero |
| variation missing price | error | A variation has no regular price, or a regular price of zero |
| sale above regular price | error | Sale price is above the regular price |
| negative price | error | Regular or sale price is below zero |
| invalid gtin | error | GTIN is not 8, 12, 13, or 14 digits, contains non-digits, or fails the GS1 check digit |
| duplicate gtin | error | A GTIN appears on more than one product |
| uncategorised product | warning | No categories, or only the default `Uncategorized` category |

Description text is the Description column when it is non-empty,
otherwise the Short Description column. Variable and grouped
products have no price of their own, so they are skipped by the
price checks. Variations inherit images, descriptions, and
categories from their parent, so those checks skip them. An empty
GTIN cell is fine: GTINs are optional in WooCommerce.

## Usage

Audit an export:

```bash
python3 woo_product_doctor.py examples/sample.csv
```

Read from stdin (omit the argument, or pass `-`):

```bash
cat examples/sample.csv | python3 woo_product_doctor.py -
```

Gate a job on it (exit 1 if any error finding exists, else exit 0):

```bash
python3 woo_product_doctor.py examples/sample.csv --check
```

Fail on warnings too:

```bash
python3 woo_product_doctor.py examples/sample.csv --check --strict
```

Emit JSON instead of text:

```bash
python3 woo_product_doctor.py examples/sample.csv --json
```

Only audit products with one status:

```bash
python3 woo_product_doctor.py examples/sample.csv --status draft
```

Change the description word threshold:

```bash
python3 woo_product_doctor.py examples/sample.csv --min-words 10
```

## Captured output: the sample audit

The sample file has 17 products: one clean simple product, one
thin description, one duplicate SKU, one missing SKU, one missing
price, one zero price, one sale price above the regular price, one
missing image, one placeholder image, one missing description, one
uncategorised product, one invalid GTIN, one duplicate GTIN, one
clean variable parent, one variation with a missing price, one
variation with a missing SKU but a price, and one draft product
with a missing image and a thin description.

```bash
python3 woo_product_doctor.py examples/sample.csv
```

Captured output:

```
WooCommerce products audit: examples/sample.csv
Description word threshold: 20 words

Products: 17 total
Statuses: draft: 1, published: 16
Types: simple: 14, variable: 1, variation: 2

Findings: 16 (11 errors, 5 warnings)

Check                      Errors Warnings
duplicate sku                   1        0
missing sku                     1        1
missing image                   1        1
placeholder image               1        0
missing description             1        0
thin description                0        2
missing or zero price           2        0
variation missing price         1        0
sale above regular price        1        0
invalid gtin                    1        0
duplicate gtin                  1        0
uncategorised product           0        1

Findings:
[warning] product 102 (Red Gadget): description has 7 words, below the 20 word threshold
[error] product 103 (Blue Widget Copy): SKU WID-001 appears more than once in the export
[error] product 104 (Green Thing): product has no SKU
[error] product 105 (Yellow Doohickey): product has no regular price
[error] product 106 (Purple Gizmo): regular price is zero
[error] product 107 (Orange Widget): sale price 19.99 is above regular price 15.00
[error] product 108 (Black Gadget): product has no image
[error] product 109 (White Widget): image looks like a placeholder: https://example.com/images/woocommerce-placeholder.png
[error] product 110 (Grey Gizmo): product has no description or short description
[warning] product 111 (Pink Thing): product has no category
[error] product 112 (Brown Gadget): GTIN '5901234123456' is invalid: GTIN check digit does not match
[error] product 113 (Silver Widget): GTIN 5901234123457 appears more than once in the export
[error] product 115 (T-Shirt - Small): variation has no regular price
[warning] product 116 (T-Shirt - Medium): product has no SKU
[warning] product 117 (Draft Product): product has no image
[warning] product 117 (Draft Product): description has 1 word, below the 20 word threshold
```

## Captured output: --check

The sample has 11 error findings, so the gate fails:

```bash
python3 woo_product_doctor.py examples/sample.csv --check
```

Captured output (exit code 1, report above plus this last line):

```
CHECK FAILED: 11 error(s), 5 warning(s)
```

The clean sample has no findings, so the gate passes:

```bash
python3 woo_product_doctor.py examples/clean.csv --check
```

Captured output (exit code 0, report above plus this last line):

```
CHECK PASSED: no error findings
```

Note: `--check` fails on errors only. A warnings-only export
passes `--check` and fails `--check --strict`, as shown here on a
one-product export whose only finding is a 4-word description:

```bash
printf 'ID,Type,SKU,Name,Published,Short description,Description,Regular price,Sale price,Categories,Images,GTIN\n401,simple,WID-401,Blue Widget,1,A sturdy blue widget.,Short text here only.,19.99,,Tools,https://example.com/images/blue.jpg,5901234123457\n' | python3 woo_product_doctor.py - --check
```

Captured output (exit code 0, last line):

```
CHECK PASSED: no error findings
```

```bash
printf 'ID,Type,SKU,Name,Published,Short description,Description,Regular price,Sale price,Categories,Images,GTIN\n401,simple,WID-401,Blue Widget,1,A sturdy blue widget.,Short text here only.,19.99,,Tools,https://example.com/images/blue.jpg,5901234123457\n' | python3 woo_product_doctor.py - --check --strict
```

Captured output (exit code 1, last line):

```
CHECK FAILED: 0 error(s), 1 warning(s)
```

## Captured output: --json

```bash
python3 woo_product_doctor.py examples/sample.csv --json
```

Captured output:

```
{
  "min_words": 20,
  "total_products": 17,
  "status_counts": {
    "published": 16,
    "draft": 1
  },
  "type_counts": {
    "simple": 14,
    "variable": 1,
    "variation": 2
  },
  "error_count": 11,
  "warning_count": 5,
  "findings": [
    {
      "product_id": "102",
      "name": "Red Gadget",
      "check": "thin description",
      "severity": "warning",
      "message": "description has 7 words, below the 20 word threshold"
    },
    {
      "product_id": "103",
      "name": "Blue Widget Copy",
      "check": "duplicate sku",
      "severity": "error",
      "message": "SKU WID-001 appears more than once in the export"
    },
    {
      "product_id": "104",
      "name": "Green Thing",
      "check": "missing sku",
      "severity": "error",
      "message": "product has no SKU"
    },
    {
      "product_id": "105",
      "name": "Yellow Doohickey",
      "check": "missing or zero price",
      "severity": "error",
      "message": "product has no regular price"
    },
    {
      "product_id": "106",
      "name": "Purple Gizmo",
      "check": "missing or zero price",
      "severity": "error",
      "message": "regular price is zero"
    },
    {
      "product_id": "107",
      "name": "Orange Widget",
      "check": "sale above regular price",
      "severity": "error",
      "message": "sale price 19.99 is above regular price 15.00"
    },
    {
      "product_id": "108",
      "name": "Black Gadget",
      "check": "missing image",
      "severity": "error",
      "message": "product has no image"
    },
    {
      "product_id": "109",
      "name": "White Widget",
      "check": "placeholder image",
      "severity": "error",
      "message": "image looks like a placeholder: https://example.com/images/woocommerce-placeholder.png"
    },
    {
      "product_id": "110",
      "name": "Grey Gizmo",
      "check": "missing description",
      "severity": "error",
      "message": "product has no description or short description"
    },
    {
      "product_id": "111",
      "name": "Pink Thing",
      "check": "uncategorised product",
      "severity": "warning",
      "message": "product has no category"
    },
    {
      "product_id": "112",
      "name": "Brown Gadget",
      "check": "invalid gtin",
      "severity": "error",
      "message": "GTIN '5901234123456' is invalid: GTIN check digit does not match"
    },
    {
      "product_id": "113",
      "name": "Silver Widget",
      "check": "duplicate gtin",
      "severity": "error",
      "message": "GTIN 5901234123457 appears more than once in the export"
    },
    {
      "product_id": "115",
      "name": "T-Shirt - Small",
      "check": "variation missing price",
      "severity": "error",
      "message": "variation has no regular price"
    },
    {
      "product_id": "116",
      "name": "T-Shirt - Medium",
      "check": "missing sku",
      "severity": "warning",
      "message": "product has no SKU"
    },
    {
      "product_id": "117",
      "name": "Draft Product",
      "check": "missing image",
      "severity": "warning",
      "message": "product has no image"
    },
    {
      "product_id": "117",
      "name": "Draft Product",
      "check": "thin description",
      "severity": "warning",
      "message": "description has 1 word, below the 20 word threshold"
    }
  ]
}
```

## Captured output: --status

```bash
python3 woo_product_doctor.py examples/sample.csv --status draft
```

Captured output:

```
WooCommerce products audit: examples/sample.csv
Description word threshold: 20 words

Products: 1 total
Statuses: draft: 1
Types: simple: 1

Findings: 2 (0 errors, 2 warnings)

Check                      Errors Warnings
missing image                   0        1
thin description                0        1

Findings:
[warning] product 117 (Draft Product): product has no image
[warning] product 117 (Draft Product): description has 1 word, below the 20 word threshold
```

## Captured output: --min-words

Lowering the threshold to 5 words clears the 7-word thin
description but keeps the 1-word draft description:

```bash
python3 woo_product_doctor.py examples/sample.csv --min-words 5
```

Captured output (findings line only):

```
Findings: 15 (11 errors, 4 warnings)
```

## Captured output: bad input

`examples/invalid.csv` has a regular price that is not a number:

```bash
python3 woo_product_doctor.py examples/invalid.csv
```

Captured output on stderr (exit code 2):

```
error: product 301: regular_price is not a valid amount: 'not-a-price'
```

## Options

| Flag | Meaning |
| --- | --- |
| `input` | CSV file path, or `-` / omitted for stdin |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any error finding exists, else exit 0 |
| `--strict` | With `--check`, also exit 1 on warnings |
| `--min-words` | Minimum description words before a description counts as thin (default: 20) |
| `--status` | Only audit products with this status, for example published or draft |

Exit codes: 0 for a report (or a passed check), 1 for a failed
`--check`, 2 for bad input (missing file, missing required
columns, or a row that fails validation). Bad input errors go to
stderr.

## Edge cases

* Money is Decimal rounded to cents, so prices never carry float
  error into a report.
* A GTIN with spaces or hyphens (`5901 2341 2345 7`) is stripped
  before validation, and the GS1 check digit is verified for
  GTIN-8, GTIN-12, GTIN-13, and GTIN-14.
* A duplicate SKU is flagged on the second and later rows, not
  on the first occurrence, and the comparison is case-insensitive.
* A sale price equal to the regular price passes; only a sale
  price above the regular price is flagged.
* A description exactly `--min-words` long passes; one word
  shorter is flagged as thin.
* A product whose only category is the default `Uncategorized`
  counts as uncategorised.
* Missing images and missing descriptions are errors for
  published products and warnings for drafts.
* Variations are not checked for images, descriptions, or
  categories, since they inherit those from the parent product.
* Variable and grouped products are not checked for prices,
  since they have no price of their own.
* Checks for a column are skipped when that column is absent
  from the export.
* Amounts with currency symbols and thousands commas
  (`$1,234.56`) are accepted.
* A UTF-8 BOM at the start of the file is handled, and blank lines
  are skipped.

## Tests

```bash
python3 -m pytest tests/ -q
python3 -m unittest discover -s tests -v
```

80 tests, all passing: GTIN validation (all four lengths, valid
and bad check digits, wrong lengths, non-digits, spaces and
hyphens, empty GTIN), money parsing (currency symbols, commas,
rounding), column aliases and missing-column errors, each of the
thirteen checks with boundary cases, the sample totals (17
products, 11 errors, 5 warnings), the clean sample, plus CLI tests
for text and JSON output, `--check` pass and fail, `--strict`,
`--status` filtering, `--min-words`, stdin, module run, and exit
code 2 for bad input and bad option values.

## License

MIT. See [LICENSE](LICENSE).
