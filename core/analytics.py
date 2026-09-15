from collections import defaultdict


def evidence_for(campaign):
    groups = defaultdict(lambda: {"impressions": 0, "engagements": 0, "count": 0})
    ids = []
    dates = []
    sources = set()
    for obs in campaign.observations.order_by("observed_on"):
        if obs.impressions is None or obs.impressions == 0 or obs.engagements is None:
            continue
        key = f"{obs.channel} / {obs.format}"
        group = groups[key]
        group["impressions"] += obs.impressions
        group["engagements"] += obs.engagements
        group["count"] += 1
        ids.append(str(obs.id))
        dates.append(obs.observed_on)
        sources.add(obs.source)
    if len(groups) < 2:
        return None, []
    rows = []
    for name, counts in groups.items():
        rows.append(
            {
                "name": name,
                **counts,
                "rate": round(100 * counts["engagements"] / counts["impressions"], 2),
            }
        )
    rows.sort(key=lambda row: row["rate"], reverse=True)
    return {
        "groups": rows,
        "winner": rows[0]["name"],
        "period_start": min(dates).isoformat(),
        "period_end": max(dates).isoformat(),
        "sources": sorted(sources),
    }, ids
