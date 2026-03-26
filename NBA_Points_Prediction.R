# ============================================================
#  NBA Points Prediction Model
#  Author : Lester Lee | lesterlee@g.ucla.edu
#  Date   : Feb 2025 – Mar 2025
#  Tools  : R, tidyverse, ggplot2, lm()
#
#  Goal   : Identify which in-game statistics best predict
#           NBA team scoring and build a multiple linear
#           regression model to quantify their impact.
# ============================================================

# ── 0. Libraries ──────────────────────────────────────────────────────────────
library(tidyverse)
library(corrplot)
library(broom)

# ── 1. Load Data ──────────────────────────────────────────────────────────────
nba <- read_csv("nba_team_stats.csv")
glimpse(nba)
summary(nba)

# ── 2. Data Cleaning ──────────────────────────────────────────────────────────
cat("\nMissing values per column:\n")
colSums(is.na(nba))
nba_clean <- nba %>%
  filter(!is.na(points)) %>%
  mutate(win_flag = ifelse(win == TRUE | win == "W", 1, 0))
cat("\nRows after cleaning:", nrow(nba_clean), "\n")

# ── 3. Exploratory Data Analysis ──────────────────────────────────────────────
ggplot(nba_clean, aes(x = points)) +
  geom_histogram(bins = 30, fill = "#2b7be8", color = "white", alpha = 0.85) +
  geom_vline(aes(xintercept = mean(points)), color = "#e05252", linetype = "dashed", size = 1) +
  labs(title = "Distribution of Team Points Scored",
       x = "Points", y = "Count") +
  theme_minimal(base_size = 13)

ggplot(nba_clean, aes(x = as.factor(win_flag), y = points, fill = as.factor(win_flag))) +
  geom_boxplot(alpha = 0.8, outlier.shape = 21) +
  scale_fill_manual(values = c("#e05252", "#2b7be8"), labels = c("Loss", "Win")) +
  labs(title = "Points Scored: Wins vs Losses", x = "Game Result", y = "Points", fill = "Result") +
  theme_minimal(base_size = 13)

# ── 4. Correlation Analysis ───────────────────────────────────────────────────
numeric_vars <- nba_clean %>%
  select(points, assists, rebounds, fg_pct, fg3_pct, turnovers, steals, blocks, win_flag)
cor_matrix <- cor(numeric_vars, use = "complete.obs")
corrplot(cor_matrix, method = "color", type = "upper", tl.col = "black",
         addCoef.col = "black", number.cex = 0.7, title = "NBA Stats Correlation Matrix")

# ── 5. Multiple Linear Regression ──────────────────────────────────────────────
model <- lm(points ~ assists + fg_pct + fg3_pct + rebounds + turnovers, data = nba_clean)
summary(model)
tidy(model) %>% arrange(p.value) %>% mutate(across(where(is.numeric), ~ round(., 4))) %>% print()
glance(model) %>% select(r.squared, adj.r.squared, sigma, AIC) %>% print()

# ── 6. Model Evaluation ───────────────────────────────────────────────────────────
predictions <- predict(model, nba_clean)
residuals   <- nba_clean$points - predictions
rmse <- sqrt(mean(residuals^2))
r2   <- summary(model)$r.squared
mae  <- mean(abs(residuals))
cat(sprintf("RMSE: %.3f | R2: %.3f | MAE: %.3f\n", rmse, r2, mae))

# ── 7. Residual Diagnostics ───────────────────────────────────────────────────
par(mfrow = c(2, 2)); plot(model, which = c(1, 2, 3, 5)); par(mfrow = c(1, 1))
nba_clean <- nba_clean %>% mutate(fitted = fitted(model), residual = residuals(model))
ggplot(nba_clean, aes(x = fitted, y = residual)) +
  geom_point(alpha = 0.4, color = "#2b7be8") +
  geom_hline(yintercept = 0, color = "#e05252", linetype = "dashed") +
  labs(title = "Residuals vs Fitted Values", x = "Fitted", y = "Residuals") +
  theme_minimal(base_size = 13)
