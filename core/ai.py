import json
import os
import re
import urllib.request
from datetime import timedelta


class AIError(Exception):
    pass


def _request(schema_name, instructions, payload):
    mode = os.getenv("AI_MODE", "demo")
    if mode == "demo":
        return None
    if mode != "openai" or not os.getenv("OPENAI_API_KEY"):
        raise AIError("AI provider is not configured.")
    body = json.dumps(
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": instructions + " Return only a JSON object.",
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.load(response)
        return json.loads(result["choices"][0]["message"]["content"])
    except Exception as exc:
        raise AIError(
            f"{schema_name} generation failed. Try again or switch to demo mode."
        ) from exc


def strategy(campaign):
    payload = {
        k: getattr(campaign, k)
        for k in (
            "name",
            "objective",
            "audience",
            "tone",
            "channels",
            "issue",
            "desired_outcome",
            "context",
        )
    }
    data = _request(
        "strategy",
        "Produce keys objective, audience, key_message, supporting_messages (array), pillars (array), kpis (array), risks (array). Ground all details in the supplied brief.",
        payload,
    )
    if data is None:
        data = {
            "objective": campaign.objective,
            "audience": campaign.audience,
            "key_message": campaign.desired_outcome or campaign.objective,
            "supporting_messages": [
                "Recognize the issue",
                "Take a practical protective action",
                "Share reliable guidance",
            ],
            "pillars": ["Recognize", "Protect", "Act"],
            "kpis": ["Engagement rate", "Click-through rate"],
            "risks": ["Avoid unsupported claims"],
        }
    required = {
        "objective": str,
        "audience": str,
        "key_message": str,
        "supporting_messages": list,
        "pillars": list,
        "kpis": list,
        "risks": list,
    }
    if not isinstance(data, dict) or any(
        not isinstance(data.get(k), t) for k, t in required.items()
    ):
        raise AIError("The AI returned an invalid strategy. Please retry.")
    return data


def plan(campaign, strategy_data):
    payload = {
        "brief": campaign.objective,
        "audience": campaign.audience,
        "channels": campaign.channels,
        "start": campaign.starts_on.isoformat(),
        "end": campaign.ends_on.isoformat(),
        "strategy": strategy_data,
    }
    data = _request(
        "plan",
        "Produce JSON key items, an array of 4 to 8 objects with title, channel, format, pillar, planned_on (YYYY-MM-DD). Use only provided channels and dates.",
        payload,
    )
    if data is None:
        channels = [x.strip() for x in campaign.channels.split(",") if x.strip()] or ["Website"]
        pillars = strategy_data["pillars"]
        days = max(1, (campaign.ends_on - campaign.starts_on).days + 1)
        data = {
            "items": [
                {
                    "title": title,
                    "channel": channels[i % len(channels)],
                    "format": fmt,
                    "pillar": pillars[i % len(pillars)],
                    "planned_on": (
                        campaign.starts_on + timedelta(days=min(days - 1, i * 3))
                    ).isoformat(),
                }
                for i, (title, fmt) in enumerate(
                    [
                        ("Spot the warning signs", "carousel"),
                        ("A real-world scenario", "short video"),
                        ("What to do next", "message"),
                        ("Quick safety checklist", "social post"),
                    ]
                )
            ]
        }
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not 1 <= len(items) <= 12:
        raise AIError("The AI returned an invalid plan. Please retry.")
    return items


def content(campaign, item, strategy_data):
    data = _request(
        "content",
        "Produce JSON key draft with concise, audience-appropriate campaign copy. Do not claim unverifiable facts.",
        {
            "campaign": campaign.name,
            "objective": campaign.objective,
            "audience": campaign.audience,
            "strategy": strategy_data,
            "item": {
                "title": item.title,
                "format": item.format,
                "channel": item.channel,
            },
        },
    )
    if data is None:
        return f"{item.title}\n\nFor {campaign.audience}: {strategy_data['key_message']}\n\nTake action: {campaign.desired_outcome or campaign.objective}"
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("draft"), str)
        or not data["draft"].strip()
    ):
        raise AIError("The AI returned invalid content. Please retry.")
    return data["draft"][:5000]


def explain(evidence):
    data = _request(
        "insight",
        "Produce JSON keys narrative and recommendation. Do not include any numbers; the application displays verified figures separately. Describe causes as possibilities, not facts.",
        evidence,
    )
    if data is None:
        return (
            f"{evidence['winner']} has the highest observed engagement rate in the entered data. This may indicate the format resonates with the audience.",
            f"Test one additional {evidence['winner']} item and compare its results.",
        )
    if not isinstance(data, dict) or not all(
        isinstance(data.get(k), str) for k in ("narrative", "recommendation")
    ):
        raise AIError("The AI returned an invalid insight. Please retry.")
    if re.search(r"\d", data["narrative"] + data["recommendation"]):
        raise AIError("The AI included an unverified numerical claim. Please retry.")
    return data["narrative"][:2000], data["recommendation"][:1000]
