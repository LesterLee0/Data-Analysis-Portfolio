"""Customer retention & revenue analysis for the Online Retail II dataset.

Produces every chart and headline number used in the README:

1. Headline KPIs (revenue, orders, customers, AOV, repeat rate)
2. Monthly revenue trend
3. Monthly cohort retention matrix + heatmap
4. RFM segmentation (segment sizes and revenue contribution)
5. Top products by revenue
6. Revenue by country (UK vs international)

Usage:  python src/analysis.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CHARTS = ROOT / "charts"

plt.rcParams.update({
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "font.family": "sans-serif",
})

ACCENT = "#2563eb"
GREY = "#9ca3af"


def money(x: float) -> str:
    if x >= 1e6:
        return f"£{x / 1e6:.2f}M"
    if x >= 1e3:
        return f"£{x / 1e3:.0f}K"
    return f"£{x:.0f}"


# ---------------------------------------------------------------- KPIs


def headline_kpis(df: pd.DataFrame, cust: pd.DataFrame) -> dict:
    orders_per_customer = cust.groupby("customer_id")["invoice"].nunique()
    repeat_customers = (orders_per_customer > 1).sum()
    repeat_rate = repeat_customers / len(orders_per_customer)

    cust_rev = cust.groupby("customer_id").agg(
        revenue=("revenue", "sum"), orders=("invoice", "nunique")
    )
    repeat_rev_share = cust_rev.loc[cust_rev["orders"] > 1, "revenue"].sum() / cust_rev["revenue"].sum()

    return {
        "total_revenue": float(df["revenue"].sum()),
        "total_orders": int(df["invoice"].nunique()),
        "identified_customers": int(cust["customer_id"].nunique()),
        "avg_order_value": float(df.groupby("invoice")["revenue"].sum().mean()),
        "repeat_rate": float(repeat_rate),
        "repeat_revenue_share": float(repeat_rev_share),
        "date_min": str(df["invoice_date"].min().date()),
        "date_max": str(df["invoice_date"].max().date()),
    }


# ------------------------------------------------------- monthly trend


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    m = (
        df.set_index("invoice_date")
        .resample("ME")
        .agg(revenue=("revenue", "sum"), orders=("invoice", "nunique"))
        .reset_index()
    )
    m["month"] = m["invoice_date"].dt.to_period("M").astype(str)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(m["invoice_date"][:-1], m["revenue"][:-1] / 1e3, color=ACCENT, lw=2.2, marker="o", ms=4)
    ax.plot(m["invoice_date"][-2:], m["revenue"][-2:] / 1e3, color=ACCENT, lw=2.2, ls="--",
            marker="o", ms=4, mfc="white")
    ax.annotate("Dec 2011 is partial\n(data ends 9 Dec)",
                xy=(m["invoice_date"].iloc[-1], m["revenue"].iloc[-1] / 1e3),
                xytext=(-115, 40), textcoords="offset points", fontsize=8, color="#6b7280")
    ax.set_title("Monthly revenue, Dec 2009 – Dec 2011")
    ax.set_ylabel("Revenue (£ thousands)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS / "monthly_revenue.png", bbox_inches="tight")
    plt.close(fig)
    return m


# ---------------------------------------------------- cohort retention


def cohort_retention(cust: pd.DataFrame) -> pd.DataFrame:
    orders = (
        cust.groupby(["customer_id", "invoice"])
        .agg(order_month=("invoice_date", lambda s: s.min().to_period("M")))
        .reset_index()
    )
    first = orders.groupby("customer_id")["order_month"].min().rename("cohort")
    orders = orders.join(first, on="customer_id")
    orders["months_since"] = (orders["order_month"] - orders["cohort"]).map(lambda d: d.n)

    counts = (
        orders.groupby(["cohort", "months_since"])["customer_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    sizes = counts[0]
    retention = counts.div(sizes, axis=0)

    # Heatmap: first 12 cohorts x first 12 months for readability
    r = retention.iloc[:13, :13]
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(r.values, cmap="Blues", vmin=0, vmax=0.6, aspect="auto")
    ax.set_xticks(range(r.shape[1]), labels=[str(c) for c in r.columns])
    ax.set_yticks(
        range(r.shape[0]),
        labels=[f"{idx}  (n={sizes[idx]:,})" for idx in r.index],
        fontsize=8,
    )
    for i in range(r.shape[0]):
        for j in range(r.shape[1]):
            v = r.values[i, j]
            if i == 0 and j == 0 or v == 0 and j > 0 and r.values[i, max(j - 1, 0)] == 0:
                continue
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.35 else "#1f2937")
    ax.set_title("Monthly cohort retention (share of cohort placing an order)")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("First-purchase cohort")
    fig.colorbar(im, ax=ax, shrink=0.8, format=lambda x, _: f"{x:.0%}")
    fig.tight_layout()
    fig.savefig(CHARTS / "cohort_retention.png", bbox_inches="tight")
    plt.close(fig)

    retention.to_csv(DATA / "cohort_retention_matrix.csv")
    return retention


# ------------------------------------------------------------- RFM


SEGMENT_RULES = [
    ("Champions", lambda r, f, m: r >= 4 and f >= 4),
    ("Loyal", lambda r, f, m: r >= 3 and f >= 3),
    ("Big spenders", lambda r, f, m: m >= 4 and r >= 2),
    ("Promising", lambda r, f, m: r >= 4),
    ("At risk", lambda r, f, m: r <= 2 and f >= 3),
    ("Hibernating", lambda r, f, m: True),
]


def rfm_segmentation(cust: pd.DataFrame) -> pd.DataFrame:
    snapshot = cust["invoice_date"].max() + pd.Timedelta(days=1)
    rfm = cust.groupby("customer_id").agg(
        recency_days=("invoice_date", lambda s: (snapshot - s.max()).days),
        frequency=("invoice", "nunique"),
        monetary=("revenue", "sum"),
    )
    rfm["R"] = pd.qcut(rfm["recency_days"], 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["F"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["M"] = pd.qcut(rfm["monetary"], 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def assign(row):
        for name, rule in SEGMENT_RULES:
            if rule(row["R"], row["F"], row["M"]):
                return name
        return "Other"

    rfm["segment"] = rfm.apply(assign, axis=1)
    rfm.to_csv(DATA / "rfm_segments.csv")

    seg = rfm.groupby("segment").agg(
        customers=("segment", "size"),
        revenue=("monetary", "sum"),
        avg_recency=("recency_days", "mean"),
        avg_orders=("frequency", "mean"),
    ).sort_values("revenue", ascending=False)
    seg["revenue_share"] = seg["revenue"] / seg["revenue"].sum()
    seg["customer_share"] = seg["customers"] / seg["customers"].sum()

    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = np.arange(len(seg))
    ax.bar(x - 0.2, seg["customer_share"] * 100, width=0.4, label="% of customers", color=GREY)
    ax.bar(x + 0.2, seg["revenue_share"] * 100, width=0.4, label="% of revenue", color=ACCENT)
    for xi, (cs, rs) in zip(x, zip(seg["customer_share"], seg["revenue_share"])):
        ax.text(xi - 0.2, cs * 100 + 0.8, f"{cs:.0%}", ha="center", fontsize=8, color="#4b5563")
        ax.text(xi + 0.2, rs * 100 + 0.8, f"{rs:.0%}", ha="center", fontsize=8, color=ACCENT)
    ax.set_xticks(x, labels=seg.index, rotation=15)
    ax.set_ylabel("Share (%)")
    ax.set_title("RFM segments: customer share vs revenue share")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "rfm_segments.png", bbox_inches="tight")
    plt.close(fig)

    seg.to_csv(DATA / "rfm_segment_summary.csv")
    return seg


# ----------------------------------------------------- products/geo


def top_products(df: pd.DataFrame) -> pd.DataFrame:
    top = (
        df.groupby(["stock_code", "description"])["revenue"]
        .sum()
        .nlargest(10)
        .reset_index()
        .sort_values("revenue")
    )
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = top["description"].str.title().str.slice(0, 38)
    ax.barh(labels, top["revenue"] / 1e3, color=ACCENT)
    ax.set_title("Top 10 products by revenue")
    ax.set_xlabel("Revenue (£ thousands)")
    fig.tight_layout()
    fig.savefig(CHARTS / "top_products.png", bbox_inches="tight")
    plt.close(fig)
    return top


def country_split(df: pd.DataFrame) -> pd.DataFrame:
    geo = df.groupby("country")["revenue"].sum().sort_values(ascending=False)
    top = geo.head(8)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    colors = [ACCENT if c == "United Kingdom" else GREY for c in top.index]
    ax.bar(top.index, top / 1e6, color=colors)
    ax.set_ylabel("Revenue (£ millions)")
    ax.set_title("Revenue by country (top 8)")
    ax.tick_params(axis="x", rotation=20)
    for i, v in enumerate(top / 1e6):
        ax.text(i, v + 0.1, f"£{v:.2f}M" if v >= 0.1 else f"£{v * 1e3:.0f}K",
                ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "revenue_by_country.png", bbox_inches="tight")
    plt.close(fig)
    return geo


def main() -> None:
    CHARTS.mkdir(exist_ok=True)
    df = pd.read_parquet(DATA / "transactions_clean.parquet")
    cust = df[df["customer_id"].notna()].copy()

    kpis = headline_kpis(df, cust)
    monthly = monthly_trend(df)
    retention = cohort_retention(cust)
    seg = rfm_segmentation(cust)
    top = top_products(df)
    geo = country_split(df)

    # Extra numbers for the README
    later = retention.iloc[:-3, 1:4]
    kpis["m1_retention_avg"] = float(retention.iloc[:-1, 1].mean())
    kpis["m1_3_retention_avg"] = float(later.mean().mean())
    kpis["uk_revenue_share"] = float(geo["United Kingdom"] / geo.sum())
    champ = seg.loc[["Champions"]] if "Champions" in seg.index else None
    if champ is not None:
        kpis["champions_customer_share"] = float(champ["customer_share"].iloc[0])
        kpis["champions_revenue_share"] = float(champ["revenue_share"].iloc[0])

    with open(DATA / "kpis.json", "w") as f:
        json.dump(kpis, f, indent=2)

    print(json.dumps(kpis, indent=2))
    print("\nSegment summary:\n", seg.round(3).to_string())
    print("\nTop products:\n", top[["description", "revenue"]].to_string(index=False))
    print(f"\nMonthly revenue range: {money(monthly['revenue'].min())} – {money(monthly['revenue'].max())}")
    print("Charts written to", CHARTS)


if __name__ == "__main__":
    main()
