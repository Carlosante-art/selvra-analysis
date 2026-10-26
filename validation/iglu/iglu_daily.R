# Reference implementation of the daily CGM metrics, computed with iglu
# (Broll et al., PLoS ONE 2021; https://github.com/irinagain/iglu), an independent,
# peer-reviewed R package. Used to check fct_glucose_daily, never by the pipeline itself.
#
# Usage: Rscript iglu_daily.R readings.csv out.csv
#   readings.csv: id (local date), time (ISO 8601, UTC), gl (mg/dL), is_artefact (true/false),
#                 plus the thresholds in mg/dL as columns low, high, low2, high2 (same on every row)

suppressPackageStartupMessages(library(iglu))

args <- commandArgs(trailingOnly = TRUE)
raw <- read.csv(args[1], stringsAsFactors = FALSE)
lo <- raw$low[1]; hi <- raw$high[1]; lo2 <- raw$low2[1]; hi2 <- raw$high2[1]

data <- data.frame(
  id = raw$id,
  time = as.POSIXct(raw$time, format = "%Y-%m-%dT%H:%M:%S", tz = "UTC"),
  gl = raw$gl
)
clean <- data[raw$is_artefact %in% c("false", "False", FALSE), ]

second <- function(df) df[[2]]

metrics <- function(d) {
  data.frame(
    id             = mean_glu(d)$id,
    mean_mgdl      = second(mean_glu(d)),
    sd_mgdl        = second(sd_glu(d)),
    cv_pct         = second(cv_glu(d)),
    gmi_pct        = second(gmi(d)),
    tir_pct        = second(in_range_percent(d, target_ranges = list(c(lo, hi)))),
    tar_pct        = second(above_percent(d, targets_above = hi)),
    tar_level2_pct = second(above_percent(d, targets_above = hi2)),
    tbr_pct        = second(below_percent(d, targets_below = lo)),
    tbr_level2_pct = second(below_percent(d, targets_below = lo2))
  )
}

all <- metrics(data)
cl <- metrics(clean)[, c("id", "mean_mgdl", "tir_pct", "tbr_pct")]
names(cl) <- c("id", "mean_mgdl_clean", "tir_pct_clean", "tbr_pct_clean")
out <- merge(all, cl, by = "id", all.x = TRUE)
out$iglu_version <- as.character(packageVersion("iglu"))
write.csv(out, args[2], row.names = FALSE)
