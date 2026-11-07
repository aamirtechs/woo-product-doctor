# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Accept a JSON products export in addition to CSV

Title: Accept a JSON products export in addition to CSV

Description: Some stores export products as JSON, not CSV. Accept a
JSON file (a list of product objects, or an object with a `products`
list) with the same fields (id, type, sku, name, published,
short_description, description, regular_price, sale_price,
categories, images, gtin) when the input file ends in `.json`, and
produce exactly the same audit as the CSV path. The CSV behavior must
not change.

Difficulty: easy

Acceptance criteria:

* A JSON sample with the same products as `examples/sample.csv`
  produces the same finding count and the same findings.
* A JSON row with a bad price exits 2 with the product id in the
  error, just like the CSV path.
* An empty JSON list produces a report with zero totals.
* A test covers the JSON path and the bad price case.
* The README documents the JSON fields and the `.json` detection.

## 2. Add a --severity option to filter the findings list

Title: Add --severity to show only errors or only warnings

Description: Large exports can produce long findings lists, and
operators triaging errors first want to hide the warnings. Add
`--severity error` (errors only) and `--severity warning`
(warnings only). The summary counts must still describe the full
audit, and only the findings list and the per-check table change.

Difficulty: easy

Acceptance criteria:

* `--severity error` shows only error findings in text and JSON.
* `--severity warning` shows only warning findings.
* Without `--severity`, the findings list is unchanged.
* An invalid `--severity` value exits 2 with a clear message.
* Tests cover both filters and the unchanged default.
* The README documents the new flag.

## 3. Report the most common problem per check in text output

Title: Add a per-check most-common-value line to text output

Description: The per-check table shows counts, but an operator
wants to see the single most repeated value per check at a glance,
for example the SKU that is duplicated most often, or the GTIN
shared by the most products. Add one line per check that has
findings, naming the most frequent value for that check (SKU for
duplicate SKU, GTIN for duplicate GTIN, image URL for placeholder
image) and how many times it appears. Checks without a repeated
value just name the first product id.

Difficulty: medium

Acceptance criteria:

* A sample with a duplicated SKU and a duplicated GTIN shows both
  most-common lines with their counts.
* A sample with no findings shows no most-common lines.
* The JSON output is unchanged by this issue.
* Tests cover the ordering and the no-findings case.
* The README documents the new section.

## 4. Support WooCommerce HPOS date and sale schedule columns

Title: Support Date sale price starts and ends columns

Description: WooCommerce exports can carry `Date sale price starts`
and `Date sale price ends` columns. Accept both, and add a warning
when a product has a sale price but its sale window has already
ended, or when the sale start date is in the future so the sale is
not live yet. The existing sale-above-regular check must not
change.

Difficulty: medium

Acceptance criteria:

* A product whose sale ended before the reference date gets a
  warning naming the end date.
* A product whose sale starts in the future gets a warning naming
  the start date.
* A product with a live sale window gets no new finding.
* A bad date in either column exits 2 with the product id in the
  error.
* Tests cover all three cases and the bad date case.
* The README documents the new columns and the new check.
