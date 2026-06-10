"""Build and execute notebooks/retention_analysis.ipynb.

Dev utility: regenerates the narrative notebook from scratch so it always
matches the cleaned dataset, then executes it top-to-bottom.
"""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "retention_analysis.ipynb"

nb = nbf.v4.new_notebook()
md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = []

cells.append(md("""\
# Customer Retention & Revenue Analysis — Online Retail II

**Business question:** A UK-based online giftware retailer wants to know where its
revenue actually comes from, how well it retains new customers, and which customer
segments deserve marketing spend.

**Data:** [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) —
~1.07M real transaction rows from Dec 2009 to Dec 2011.

**Pipeline:** `src/prepare_data.py` cleans the raw Excel file (dedupes rows, nets out
cancelled orders against their original purchases, removes fees/adjustments) and writes
the parquet file this notebook reads. The same analyses are reproduced in pure SQL in
`sql/analysis_queries.sql`.
"""))

cells.append(code("""\
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
df = pd.read_parquet(ROOT / "data" / "processed" / "transactions_clean.parquet")
cust = df[df["customer_id"].notna()].copy()  # identified customers only

plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 110})
ACCENT, GREY = "#2563eb", "#9ca3af"

df.head()
"""))

cells.append(md("## 1. Headline KPIs"))

cells.append(code("""\
orders_per_customer = cust.groupby("customer_id")["invoice"].nunique()
cust_rev = cust.groupby("customer_id").agg(revenue=("revenue", "sum"), orders=("invoice", "nunique"))

kpis = pd.Series({
    "Total revenue": f"£{df['revenue'].sum() / 1e6:.2f}M",
    "Orders": f"{df['invoice'].nunique():,}",
    "Identified customers": f"{cust['customer_id'].nunique():,}",
    "Average order value": f"£{df.groupby('invoice')['revenue'].sum().mean():.0f}",
    "Repeat-purchase rate": f"{(orders_per_customer > 1).mean():.1%}",
    "Revenue from repeat buyers": f"{cust_rev.loc[cust_rev['orders'] > 1, 'revenue'].sum() / cust_rev['revenue'].sum():.1%}",
})
kpis.to_frame("value")
"""))

cells.append(md("""\
Nearly **97% of customer revenue comes from repeat buyers**, so retention — not
acquisition — is the lever that moves this business.
"""))

cells.append(md("## 2. Monthly revenue trend"))

cells.append(code("""\
monthly = df.set_index("invoice_date").resample("ME")["revenue"].sum()

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(monthly.index, monthly / 1e3, color=ACCENT, lw=2, marker="o", ms=4)
ax.set_title("Monthly revenue (Dec 2011 is partial — data ends 9 Dec)")
ax.set_ylabel("Revenue (£ thousands)")
ax.grid(axis="y", alpha=0.3)
plt.show()
"""))

cells.append(md("""\
Revenue is strongly seasonal: September–November build to a **November peak of ~£1.4M**
(2.5–3x the spring trough) as wholesale buyers stock up for Christmas. Inventory and
campaign planning should anchor on that Q4 ramp.
"""))

cells.append(md("""\
## 3. Cohort retention

Group customers by the month of their first purchase, then track what share of each
cohort places another order in the months that follow.
"""))

cells.append(code("""\
orders = (
    cust.groupby(["customer_id", "invoice"])
    .agg(order_month=("invoice_date", lambda s: s.min().to_period("M")))
    .reset_index()
)
first = orders.groupby("customer_id")["order_month"].min().rename("cohort")
orders = orders.join(first, on="customer_id")
orders["months_since"] = (orders["order_month"] - orders["cohort"]).map(lambda d: d.n)

counts = orders.groupby(["cohort", "months_since"])["customer_id"].nunique().unstack(fill_value=0)
retention = counts.div(counts[0], axis=0)

r = retention.iloc[:13, :13]
fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(r.values, cmap="Blues", vmin=0, vmax=0.6, aspect="auto")
ax.set_xticks(range(r.shape[1]), labels=[str(c) for c in r.columns])
ax.set_yticks(range(r.shape[0]), labels=[f"{i}  (n={counts.loc[i, 0]:,})" for i in r.index], fontsize=8)
ax.set_xlabel("Months since first purchase"); ax.set_ylabel("Cohort")
ax.set_title("Monthly cohort retention")
fig.colorbar(im, shrink=0.8, format=lambda x, _: f"{x:.0%}")
plt.show()

print(f"Average month-1 retention: {retention.iloc[:-1, 1].mean():.1%}")
"""))

cells.append(md("""\
Roughly **1 in 5 new customers comes back the following month**, and retention then
stabilises around 20–25% rather than decaying to zero — the customers who survive the
first month become a durable repeat base. The first repeat purchase is the critical
conversion: a post-first-order email/offer sequence in the first 30 days targets exactly
this drop-off. The December 2009 cohort (n=949, likely the retailer's longest-standing
buyers) retains at 30–40%+ for two full years.
"""))

cells.append(md("""\
## 4. RFM segmentation

Score every customer 1–5 on Recency, Frequency and Monetary value (quintiles), then map
score combinations to named, actionable segments.
"""))

cells.append(code("""\
snapshot = cust["invoice_date"].max() + pd.Timedelta(days=1)
rfm = cust.groupby("customer_id").agg(
    recency_days=("invoice_date", lambda s: (snapshot - s.max()).days),
    frequency=("invoice", "nunique"),
    monetary=("revenue", "sum"),
)
rfm["R"] = pd.qcut(rfm["recency_days"], 5, labels=[5, 4, 3, 2, 1]).astype(int)
rfm["F"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
rfm["M"] = pd.qcut(rfm["monetary"], 5, labels=[1, 2, 3, 4, 5]).astype(int)

def segment(row):
    if row["R"] >= 4 and row["F"] >= 4: return "Champions"
    if row["R"] >= 3 and row["F"] >= 3: return "Loyal"
    if row["M"] >= 4 and row["R"] >= 2: return "Big spenders"
    if row["R"] >= 4: return "Promising"
    if row["R"] <= 2 and row["F"] >= 3: return "At risk"
    return "Hibernating"

rfm["segment"] = rfm.apply(segment, axis=1)

seg = rfm.groupby("segment").agg(
    customers=("segment", "size"), revenue=("monetary", "sum"),
    avg_recency=("recency_days", "mean"), avg_orders=("frequency", "mean"),
).sort_values("revenue", ascending=False)
seg["revenue_share"] = seg["revenue"] / seg["revenue"].sum()
seg["customer_share"] = seg["customers"] / seg["customers"].sum()
seg.round(2)
"""))

cells.append(code("""\
fig, ax = plt.subplots(figsize=(9, 4.5))
x = np.arange(len(seg))
ax.bar(x - 0.2, seg["customer_share"] * 100, width=0.4, label="% of customers", color=GREY)
ax.bar(x + 0.2, seg["revenue_share"] * 100, width=0.4, label="% of revenue", color=ACCENT)
ax.set_xticks(x, labels=seg.index, rotation=15)
ax.set_ylabel("Share (%)"); ax.legend(frameon=False)
ax.set_title("Customer share vs revenue share by RFM segment")
plt.show()
"""))

cells.append(md("""\
**A quarter of customers (Champions) generate 70% of revenue.** Meanwhile the
"At risk" segment — formerly frequent buyers who haven't ordered in ~13 months —
still represents £640K of historical revenue walking out the door. The marketing
playbook falls straight out of the table: protect Champions (early access, service
priority), win back At-risk with targeted offers, and don't overspend on Hibernating
one-time buyers.
"""))

cells.append(md("## 5. What sells, and where"))

cells.append(code("""\
top = df.groupby("description")["revenue"].sum().nlargest(10).sort_values()
geo = df.groupby("country")["revenue"].sum().sort_values(ascending=False)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
axes[0].barh(top.index.str.title().str.slice(0, 32), top / 1e3, color=ACCENT)
axes[0].set_title("Top 10 products by revenue"); axes[0].set_xlabel("£ thousands")
g8 = geo.head(8)
axes[1].bar(g8.index, g8 / 1e6, color=[ACCENT if c == "United Kingdom" else GREY for c in g8.index])
axes[1].set_title("Revenue by country"); axes[1].set_ylabel("£ millions")
axes[1].tick_params(axis="x", rotation=30)
fig.tight_layout()
plt.show()

print(f"UK share of revenue: {geo['United Kingdom'] / geo.sum():.1%}")
"""))

cells.append(md("""\
## 6. Recommendations

1. **Launch a first-30-days onboarding flow.** Only ~21% of new customers return in
   month 1, yet repeat buyers drive 97% of revenue. Even a 3-point lift in month-1
   retention compounds across every future cohort.
2. **Protect the Champions segment.** 25% of customers → 70% of revenue. Loyalty perks
   and stock-priority for their top SKUs are cheap insurance on ~£11.6M of revenue.
3. **Run a win-back campaign on the At-risk segment** (~600 customers, ~4 orders each
   historically) before they lapse fully.
4. **Plan inventory around the Q4 wholesale ramp** — November revenue runs 2.5–3x the
   spring trough, and top SKUs are seasonal (Christmas paper chain kits, t-light holders).
5. **Test international growth.** 85% of revenue is UK; EIRE/Netherlands/Germany/France
   already buy at meaningful volume with zero localised marketing.

### Caveats
- ~23% of rows have no customer ID (guest checkouts / unregistered wholesale) and are
  excluded from customer-level analyses, but included in revenue totals.
- Cancelled orders are netted out against their original purchases in cleaning;
  unmatched cancellations are dropped.
- The dataset ends 9 Dec 2011, so the final month is partial.
"""))

nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}

client = NotebookClient(nb, timeout=600, kernel_name="python3",
                        resources={"metadata": {"path": str(OUT.parent)}})
client.execute()

nbf.write(nb, OUT)
print("Wrote and executed", OUT)
