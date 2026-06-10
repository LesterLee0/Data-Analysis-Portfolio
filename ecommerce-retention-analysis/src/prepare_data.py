"""Prepare the UCI Online Retail II dataset for analysis.

Reads both sheets of the raw Excel file (Dec 2009 - Dec 2011 transactions
for a UK-based online giftware retailer), applies cleaning rules, and writes
a tidy dataset to data/processed/.

Cleaning rules
--------------
1. Drop exact duplicate rows (same invoice, product, time, qty, price).
2. Net out cancellations: each cancellation row (invoice numbers starting
   with "C") is matched to a purchase row with the same customer, product,
   unit price and quantity, and BOTH rows are removed. This prevents
   cancelled mega-orders (e.g. the 80,995-unit "PAPER CRAFT, LITTLE BIRDIE"
   order that was reversed minutes later) from inflating revenue. Remaining
   unmatched cancellations are excluded, as are rows with non-positive
   quantity or price.
3. Remove non-product stock codes (postage, manual adjustments, bank charges,
   gift vouchers, test rows).
4. Keep rows without a Customer ID for revenue reporting, but customer-level
   analyses (cohorts, RFM) filter to identified customers downstream.

Usage:  python src/prepare_data.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_XLSX = ROOT / "data" / "raw" / "online_retail_II.xlsx"
PROCESSED_DIR = ROOT / "data" / "processed"

# Stock codes that are fees/adjustments rather than products.
NON_PRODUCT_CODES = {
    "POST", "D", "DOT", "M", "C2", "BANK CHARGES", "AMAZONFEE",
    "TEST001", "TEST002", "ADJUST", "ADJUST2", "S", "CRUK", "PADS", "B",
    "gift_0001_10", "gift_0001_20", "gift_0001_30", "gift_0001_40",
    "gift_0001_50", "GIFT",
}


def load_raw() -> pd.DataFrame:
    sheets = pd.read_excel(RAW_XLSX, sheet_name=["Year 2009-2010", "Year 2010-2011"])
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = [
        "invoice", "stock_code", "description", "quantity",
        "invoice_date", "price", "customer_id", "country",
    ]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates()
    print(f"Dropped {n0 - len(df):,} exact duplicate rows")

    df["invoice"] = df["invoice"].astype(str)
    df["stock_code"] = df["stock_code"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()
    df["customer_id"] = df["customer_id"].astype("Int64").astype(str).replace("<NA>", pd.NA)

    cancelled = df["invoice"].str.startswith("C")
    key = ["customer_id", "stock_code", "price"]

    cancels = df[cancelled & df["customer_id"].notna()].copy()
    cancels["abs_qty"] = -cancels["quantity"]
    cancels["seq"] = cancels.groupby(key + ["abs_qty"]).cumcount()

    purchases = df[~cancelled].copy()
    purchases["seq"] = purchases.groupby(key + ["quantity"]).cumcount()

    matched = purchases.reset_index().merge(
        cancels[key + ["abs_qty", "seq"]],
        left_on=key + ["quantity", "seq"],
        right_on=key + ["abs_qty", "seq"],
    )["index"]
    print(
        f"Netting out {len(matched):,} purchase rows reversed by a matching "
        f"cancellation ({cancels['seq'].size:,} matchable cancellation rows)"
    )
    df = df.drop(index=matched)

    cancelled = df["invoice"].str.startswith("C")
    print(f"Excluding {cancelled.sum():,} remaining cancellation rows")
    df = df[~cancelled]

    bad_values = (df["quantity"] <= 0) | (df["price"] <= 0)
    print(f"Excluding {bad_values.sum():,} rows with non-positive quantity/price")
    df = df[~bad_values]

    non_product = df["stock_code"].str.upper().isin({c.upper() for c in NON_PRODUCT_CODES})
    print(f"Excluding {non_product.sum():,} non-product rows (postage, fees, adjustments)")
    df = df[~non_product]

    df = df.assign(revenue=df["quantity"] * df["price"])
    return df.reset_index(drop=True)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = load_raw()
    print(f"Loaded {len(df):,} raw rows")
    df = clean(df)

    ided = df["customer_id"].notna()
    print(
        f"Final sales table: {len(df):,} rows, "
        f"{df['invoice'].nunique():,} invoices, "
        f"{ided.sum():,} rows ({ided.mean():.0%}) with a customer ID"
    )

    out = PROCESSED_DIR / "transactions_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
