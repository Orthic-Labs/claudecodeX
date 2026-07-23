#!/usr/bin/env python3
"""Build the Codex model catalog for the proxied instance.

Codex's /model list comes from `model_catalog_json`. That file REPLACES the
built-in list rather than merging, so it must be complete and every entry must
match the shape Codex expects. Rather than hand-writing that shape, each entry
is cloned from a known-good entry in Codex's own cached catalog.

    python3 mac/make-codex-catalog.py [--out ~/.codex-proxy/catalog.json]

EDIT MODELS BELOW to change what `cdx` offers.
"""
import argparse, copy, json, pathlib

# (slug, display name, one-line description). Order is the picker order.
MODELS = [
    ("qwen3.8-max-preview", "Qwen 3.8 Max (preview)", "Alibaba flagship, newest preview."),
    ("qwen3.7-max",         "Qwen 3.7 Max",           "Alibaba flagship, stable."),
    ("qwen3.7-plus",        "Qwen 3.7 Plus",          "Balanced Qwen for everyday work."),
    ("qwen3.6-flash",       "Qwen 3.6 Flash",         "Fastest and cheapest Qwen tier."),
    ("glm-5.2",             "GLM 5.2",                "Zhipu, via the Alibaba Token Plan."),
    ("deepseek-v4-pro",     "DeepSeek V4 Pro",        "DeepSeek, via the Alibaba Token Plan."),
    ("MiniMax-M3",          "MiniMax M3",             "MiniMax, via your own MiniMax key."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(pathlib.Path.home() / ".codex-proxy" / "catalog.json"))
    ap.add_argument("--template", default=str(pathlib.Path.home() / ".codex" / "models_cache.json"))
    args = ap.parse_args()

    cache = json.loads(pathlib.Path(args.template).read_text(encoding="utf-8"))["models"]
    template = next(m for m in cache if m["slug"] == "gpt-5.6-terra")

    out = []
    for i, (slug, name, desc) in enumerate(MODELS, start=1):
        entry = copy.deepcopy(template)
        entry.update({"slug": slug, "display_name": name, "description": desc,
                      "priority": i, "visibility": "list", "supported_in_api": True})
        for volatile in ("comp_hash", "upgrade", "availability_nux"):
            entry.pop(volatile, None)
        out.append(entry)

    dest = pathlib.Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"models": out}, indent=1))
    print(f"{dest}: {len(out)} models")
    for slug, name, _ in MODELS:
        print(f"  {slug:22} {name}")


if __name__ == "__main__":
    main()
