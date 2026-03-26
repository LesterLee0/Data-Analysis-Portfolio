-- ============================================================
--  Pizza Sales Analysis
--  Author : Lester Lee | lesterlee@g.ucla.edu
--  Date   : Aug 2025 – Sep 2025
--  Tool   : MySQL
--
--  Goal   : Analyze 40K+ pizza sales transactions to calculate
--           KPIs and surface business insights on revenue,
--           product performance, and customer behavior.
-- ============================================================


-- ── SECTION 0: DATABASE & TABLE SETUP ────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS pizza_sales_db;
USE pizza_sales_db;

CREATE TABLE IF NOT EXISTS orders (
    order_id       INT            NOT NULL,
    order_date     DATE           NOT NULL,
    order_time     TIME           NOT NULL,
    PRIMARY KEY (order_id)
);

CREATE TABLE IF NOT EXISTS order_details (
    order_details_id  INT           NOT NULL,
    order_id          INT           NOT NULL,
    pizza_id          VARCHAR(50)   NOT NULL,
    quantity          INT           NOT NULL,
    PRIMARY KEY (order_details_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS pizza_types (
    pizza_type_id   VARCHAR(50)   NOT NULL,
    name            VARCHAR(100)  NOT NULL,
    category        VARCHAR(50)   NOT NULL,
    ingredients     TEXT,
    PRIMARY KEY (pizza_type_id)
);

CREATE TABLE IF NOT EXISTS pizzas (
    pizza_id        VARCHAR(50)   NOT NULL,
    pizza_type_id   VARCHAR(50)   NOT NULL,
    size            CHAR(1)       NOT NULL,
    price           DECIMAL(6,2)  NOT NULL,
    PRIMARY KEY (pizza_id),
    FOREIGN KEY (pizza_type_id) REFERENCES pizza_types(pizza_type_id)
);


-- ── SECTION 1: CORE KPIs ──────────────────────────────────────────────────────

-- 1a. Total Revenue
SELECT ROUND(SUM(od.quantity * p.price), 2) AS total_revenue
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id;

-- 1b. Average Order Value (AOV)
SELECT ROUND(SUM(od.quantity * p.price) / COUNT(DISTINCT od.order_id), 2) AS avg_order_value
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id;

-- 1c. Total Orders & Total Pizzas Sold
SELECT COUNT(DISTINCT order_id) AS total_orders, SUM(quantity) AS total_pizzas_sold
FROM order_details;

-- 1d. Full KPI Summary
SELECT
    COUNT(DISTINCT o.order_id)                                          AS total_orders,
    SUM(od.quantity)                                                    AS total_pizzas_sold,
    ROUND(SUM(od.quantity * p.price), 2)                                AS total_revenue,
    ROUND(SUM(od.quantity * p.price) / COUNT(DISTINCT o.order_id), 2)  AS avg_order_value,
    ROUND(SUM(od.quantity) / COUNT(DISTINCT o.order_id), 2)            AS avg_pizzas_per_order
FROM orders o
JOIN order_details od ON o.order_id = od.order_id
JOIN pizzas p         ON od.pizza_id = p.pizza_id;


-- ── SECTION 2: REVENUE TRENDS ────────────────────────────────────────────────

-- 2a. Monthly Revenue
SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS month,
    ROUND(SUM(od.quantity * p.price), 2) AS monthly_revenue,
    COUNT(DISTINCT o.order_id) AS total_orders
FROM orders o JOIN order_details od ON o.order_id = od.order_id JOIN pizzas p ON od.pizza_id = p.pizza_id
GROUP BY month ORDER BY month;

-- 2b. Revenue by Day of Week
SELECT DAYNAME(o.order_date) AS day_of_week, DAYOFWEEK(o.order_date) AS day_num,
    COUNT(DISTINCT o.order_id) AS total_orders, ROUND(SUM(od.quantity * p.price), 2) AS total_revenue
FROM orders o JOIN order_details od ON o.order_id = od.order_id JOIN pizzas p ON od.pizza_id = p.pizza_id
GROUP BY day_of_week, day_num ORDER BY day_num;

-- 2c. Hourly Order Volume (Peak Hours)
SELECT HOUR(o.order_time) AS hour_of_day, COUNT(DISTINCT o.order_id) AS total_orders, SUM(od.quantity) AS pizzas_sold
FROM orders o JOIN order_details od ON o.order_id = od.order_id
GROUP BY hour_of_day ORDER BY total_orders DESC;


-- ── SECTION 3: PRODUCT PERFORMANCE ───────────────────────────────────────────

-- 3a. Top 10 Best-Selling Pizzas by Revenue
SELECT pt.name AS pizza_name, pt.category, p.size,
    SUM(od.quantity) AS total_qty_sold, ROUND(SUM(od.quantity * p.price), 2) AS total_revenue
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id JOIN pizza_types pt ON p.pizza_type_id = pt.pizza_type_id
GROUP BY pt.name, pt.category, p.size ORDER BY total_revenue DESC LIMIT 10;

-- 3b. Bottom 10 Worst-Selling Pizzas
SELECT pt.name AS pizza_name, pt.category, p.size,
    SUM(od.quantity) AS total_qty_sold, ROUND(SUM(od.quantity * p.price), 2) AS total_revenue
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id JOIN pizza_types pt ON p.pizza_type_id = pt.pizza_type_id
GROUP BY pt.name, pt.category, p.size ORDER BY total_revenue ASC LIMIT 10;

-- 3c. Top 5 by Quantity
SELECT pt.name AS pizza_name, SUM(od.quantity) AS total_qty_sold
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id JOIN pizza_types pt ON p.pizza_type_id = pt.pizza_type_id
GROUP BY pt.name ORDER BY total_qty_sold DESC LIMIT 5;


-- ── SECTION 4: CATEGORY ANALYSIS ─────────────────────────────────────────────────

-- 4a. Revenue by Category (Classic / Supreme / Veggie / Chicken)
SELECT pt.category, SUM(od.quantity) AS total_qty,
    ROUND(SUM(od.quantity * p.price), 2) AS category_revenue,
    ROUND(SUM(od.quantity * p.price) * 100.0 / SUM(SUM(od.quantity * p.price)) OVER (), 2) AS revenue_pct
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id JOIN pizza_types pt ON p.pizza_type_id = pt.pizza_type_id
GROUP BY pt.category ORDER BY category_revenue DESC;

-- 4b. Revenue by Pizza Size
SELECT p.size, SUM(od.quantity) AS total_qty,
    ROUND(SUM(od.quantity * p.price), 2) AS size_revenue,
    ROUND(SUM(od.quantity * p.price) * 100.0 / SUM(SUM(od.quantity * p.price)) OVER (), 2) AS revenue_pct
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id
GROUP BY p.size ORDER BY size_revenue DESC;


-- ── SECTION 5: CUMULATIVE & RUNNING TOTALS ───────────────────────────────────────────

-- 5a. Cumulative Revenue by Month
SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS month,
    ROUND(SUM(od.quantity * p.price), 2) AS monthly_revenue,
    ROUND(SUM(SUM(od.quantity * p.price)) OVER (ORDER BY DATE_FORMAT(o.order_date, '%Y-%m')), 2) AS cumulative_revenue
FROM orders o JOIN order_details od ON o.order_id = od.order_id JOIN pizzas p ON od.pizza_id = p.pizza_id
GROUP BY month ORDER BY month;

-- 5b. Month-over-Month Revenue Change
WITH monthly AS (
    SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS month, ROUND(SUM(od.quantity * p.price), 2) AS revenue
    FROM orders o JOIN order_details od ON o.order_id = od.order_id JOIN pizzas p ON od.pizza_id = p.pizza_id
    GROUP BY month
)
SELECT month, revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND((revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100, 2) AS mom_change_pct
FROM monthly ORDER BY month;


-- ── SECTION 6: ADVANCED ANALYSIS ───────────────────────────────────────────────────

-- 6a. Rank pizzas by revenue within each category
SELECT pt.category, pt.name AS pizza_name,
    ROUND(SUM(od.quantity * p.price), 2) AS revenue,
    RANK() OVER (PARTITION BY pt.category ORDER BY SUM(od.quantity * p.price) DESC) AS revenue_rank_in_category
FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id JOIN pizza_types pt ON p.pizza_type_id = pt.pizza_type_id
GROUP BY pt.category, pt.name ORDER BY pt.category, revenue_rank_in_category;

-- 6b. High-value orders (above average)
WITH order_totals AS (
    SELECT od.order_id, ROUND(SUM(od.quantity * p.price), 2) AS order_total
    FROM order_details od JOIN pizzas p ON od.pizza_id = p.pizza_id GROUP BY od.order_id
)
SELECT order_id, order_total FROM order_totals
WHERE order_total > (SELECT AVG(order_total) FROM order_totals)
ORDER BY order_total DESC LIMIT 20;

-- 6c. Daily summary view
CREATE OR REPLACE VIEW v_daily_summary AS
SELECT o.order_date, COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(od.quantity) AS total_pizzas, ROUND(SUM(od.quantity * p.price), 2) AS daily_revenue
FROM orders o JOIN order_details od ON o.order_id = od.order_id JOIN pizzas p ON od.pizza_id = p.pizza_id
GROUP BY o.order_date;

SELECT * FROM v_daily_summary ORDER BY order_date;

-- ── END OF ANALYSIS ─────────────────────────────────────────────────────────────────────────
