-- Customer retention & revenue analysis — Online Retail II
-- Dialect: DuckDB (reads the cleaned parquet file directly).
-- Run from the project root:
--   duckdb -c ".read sql/analysis_queries.sql"
-- or via Python: duckdb.sql(open('sql/analysis_queries.sql').read())

CREATE OR REPLACE VIEW sales AS
SELECT * FROM 'data/processed/transactions_clean.parquet';

-- ============================================================
-- 1. Headline KPIs
-- ============================================================
SELECT
    ROUND(SUM(revenue), 0)                          AS total_revenue,
    COUNT(DISTINCT invoice)                         AS total_orders,
    COUNT(DISTINCT customer_id)                     AS identified_customers,
    ROUND(SUM(revenue) / COUNT(DISTINCT invoice), 2) AS avg_order_value
FROM sales;

-- ============================================================
-- 2. Monthly revenue and order trend
-- ============================================================
SELECT
    DATE_TRUNC('month', invoice_date)        AS month,
    ROUND(SUM(revenue), 0)                   AS revenue,
    COUNT(DISTINCT invoice)                  AS orders,
    COUNT(DISTINCT customer_id)              AS active_customers
FROM sales
GROUP BY 1
ORDER BY 1;

-- ============================================================
-- 3. Repeat-purchase economics
--    What share of customers come back, and how much revenue
--    do repeat buyers drive?
-- ============================================================
WITH per_customer AS (
    SELECT
        customer_id,
        COUNT(DISTINCT invoice) AS orders,
        SUM(revenue)            AS revenue
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY 1
)
SELECT
    COUNT(*)                                                    AS customers,
    ROUND(AVG(CASE WHEN orders > 1 THEN 1.0 ELSE 0 END), 4)     AS repeat_rate,
    ROUND(SUM(CASE WHEN orders > 1 THEN revenue END)
          / SUM(revenue), 4)                                    AS repeat_revenue_share
FROM per_customer;

-- ============================================================
-- 4. Monthly cohort retention matrix
--    Rows: first-purchase cohort. Columns via months_since.
-- ============================================================
WITH orders AS (
    SELECT
        customer_id,
        invoice,
        DATE_TRUNC('month', MIN(invoice_date)) AS order_month
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY 1, 2
),
cohorts AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM orders
    GROUP BY 1
),
activity AS (
    SELECT
        c.cohort_month,
        DATEDIFF('month', c.cohort_month, o.order_month) AS months_since,
        COUNT(DISTINCT o.customer_id)                    AS active_customers
    FROM orders o
    JOIN cohorts c USING (customer_id)
    GROUP BY 1, 2
),
cohort_sizes AS (
    SELECT cohort_month, active_customers AS cohort_size
    FROM activity
    WHERE months_since = 0
)
SELECT
    a.cohort_month,
    s.cohort_size,
    a.months_since,
    a.active_customers,
    ROUND(a.active_customers * 1.0 / s.cohort_size, 4) AS retention
FROM activity a
JOIN cohort_sizes s USING (cohort_month)
ORDER BY a.cohort_month, a.months_since;

-- ============================================================
-- 5. RFM segmentation (quintile scores)
--    Note: NTILE breaks ties differently from pandas qcut, so
--    segment counts differ slightly (~5%) from the Python output.
-- ============================================================
WITH rfm_base AS (
    SELECT
        customer_id,
        DATEDIFF('day', MAX(invoice_date),
                 (SELECT MAX(invoice_date) + INTERVAL 1 DAY FROM sales)) AS recency_days,
        COUNT(DISTINCT invoice) AS frequency,
        SUM(revenue)            AS monetary
    FROM sales
    WHERE customer_id IS NOT NULL
    GROUP BY 1
),
scored AS (
    SELECT *,
        6 - NTILE(5) OVER (ORDER BY recency_days) AS r_score,
        NTILE(5) OVER (ORDER BY frequency)        AS f_score,
        NTILE(5) OVER (ORDER BY monetary)         AS m_score
    FROM rfm_base
),
segmented AS (
    SELECT *,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
            WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
            WHEN m_score >= 4 AND r_score >= 2 THEN 'Big spenders'
            WHEN r_score >= 4                  THEN 'Promising'
            WHEN r_score <= 2 AND f_score >= 3 THEN 'At risk'
            ELSE 'Hibernating'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                          AS customers,
    ROUND(SUM(monetary), 0)                           AS revenue,
    ROUND(SUM(monetary) / SUM(SUM(monetary)) OVER (), 4) AS revenue_share,
    ROUND(AVG(recency_days), 1)                       AS avg_recency_days,
    ROUND(AVG(frequency), 2)                          AS avg_orders
FROM segmented
GROUP BY 1
ORDER BY revenue DESC;

-- ============================================================
-- 6. Top 10 products by revenue
-- ============================================================
SELECT
    stock_code,
    ANY_VALUE(description)   AS description,
    ROUND(SUM(revenue), 0)   AS revenue,
    SUM(quantity)            AS units_sold
FROM sales
GROUP BY 1
ORDER BY revenue DESC
LIMIT 10;

-- ============================================================
-- 7. Revenue by country
-- ============================================================
SELECT
    country,
    ROUND(SUM(revenue), 0)                               AS revenue,
    ROUND(SUM(revenue) / SUM(SUM(revenue)) OVER (), 4)   AS revenue_share,
    COUNT(DISTINCT customer_id)                          AS customers
FROM sales
GROUP BY 1
ORDER BY revenue DESC
LIMIT 10;
