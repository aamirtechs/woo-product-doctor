# Changelog

## 1.0.0 - 2026-11-07

Initial release.

* Reads a WooCommerce products CSV export (header row, common
  column-name variants accepted) with product id and name, plus
  optional type, published status, SKU, short description,
  description, regular and sale price, categories, images, and
  GTIN (also accepted as Barcode, EAN, or UPC).
* Thirteen checks: duplicate SKUs, missing SKUs, missing images,
  placeholder images, missing descriptions, thin descriptions
  below a word threshold, missing or zero prices, variations with
  missing prices, sale price above regular price, negative
  prices, invalid GTINs, duplicate GTINs, and uncategorised
  products.
* GS1 check-digit validation for GTIN-8, GTIN-12, GTIN-13, and
  GTIN-14, with spaces and hyphens stripped before validation.
* Published products get errors for missing images and missing
  descriptions; drafts get warnings for the same gaps.
  Variations inherit images, descriptions, and categories from
  their parent, so those checks skip them.
* A product with no categories, or with only the default
  "Uncategorized" category, counts as uncategorised.
* Decimal cents math for all prices, so float errors never leak
  into a report.
* Text and `--json` output, `--check` CI gate (exit 1 on any
  error finding, `--strict` also fails on warnings),
  `--min-words` and `--status` filters, and file or stdin input.
* Checks for a column are skipped when that column is absent, so
  a minimal export is never punished for columns it never had.
* Clear exit 2 errors on stderr for missing files, missing
  required columns, and rows that fail validation.
* Zero dependencies, Python 3.10 or newer.
