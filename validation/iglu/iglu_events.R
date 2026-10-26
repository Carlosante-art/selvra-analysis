# Reference for int_glycaemic_events: iglu's own event classifier (the core of
# episode_calculation) run on exactly the readings and segments the pipeline used.
# iglu's interpolation step is deliberately not applied; see int_glycaemic_events.sql.
#
# Usage: Rscript iglu_events.R readings.csv out.csv
#   readings.csv: segment_id, rn, gl (mg/dL), plus thresholds low, high, low2, high2 (mg/dL)
#                 and n_min, n_end, n_ext (readings) on every row

suppressPackageStartupMessages(library(iglu))
event_class <- utils::getFromNamespace("event_class", "iglu")

args <- commandArgs(trailingOnly = TRUE)
raw <- read.csv(args[1])
n_min <- raw$n_min[1]; n_end <- raw$n_end[1]; n_ext <- raw$n_ext[1]
types <- list(
  hypo_level1   = list("hypo",  raw$low[1],   n_min),
  hypo_level2   = list("hypo",  raw$low2[1],  n_min),
  hypo_extended = list("hypo",  raw$low[1],   n_ext),
  hyper_level1  = list("hyper", raw$high[1],  n_min),
  hyper_level2  = list("hyper", raw$high2[1], n_min)
)

out <- list()
for (seg in split(raw, raw$segment_id)) {
  seg <- seg[order(seg$rn), ]
  d <- data.frame(id = 1, time = seq_len(nrow(seg)), gl = seg$gl)
  for (name in names(types)) {
    t <- types[[name]]
    label <- event_class(d, t[[1]], t[[2]], t[[3]], n_end)
    for (k in setdiff(unique(label), 0)) {
      idx <- which(label == k)
      out[[length(out) + 1]] <- data.frame(
        event_type = name, segment_id = seg$segment_id[1],
        start_rn = seg$rn[min(idx)], last_rn = seg$rn[max(idx)])
    }
  }
}
res <- if (length(out)) do.call(rbind, out) else
  data.frame(event_type = character(), segment_id = integer(), start_rn = integer(), last_rn = integer())
res$iglu_version <- as.character(packageVersion("iglu"))
write.csv(res, args[2], row.names = FALSE)
