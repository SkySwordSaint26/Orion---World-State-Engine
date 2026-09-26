"""
Command line (run from WSE/ with the WSE venv):

    python -m wse predict --gold-dir GOLD --out-dir PRED
        extracts every gold story's text -> PRED/<story_id>.json

    python -m wse score GOLD PRED [--json OUT.json]
        per-story and micro-averaged scores (backend metrics + coreference B-cubed)

GOLD is produced by the backend converter (from backend/):
    python -m app.evaluation convert ../accounts_from_a_lonely_broadcast_station_orion_annotation/*.json \
        --text-dir "../Accounts From a Lonely Broadcast Station" --out-dir ../WSE/data/gold
"""
import argparse
import json
import sys
import time
from pathlib import Path

from wse.evaluate import micro, score, table
from wse.pipeline import LISTS, extract


def gold_docs(gold_dir: str):
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(Path(gold_dir).glob("*.json"))]


def cmd_predict(args: argparse.Namespace) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for path, gold in gold_docs(args.gold_dir):
        t0 = time.time()
        doc = extract(gold["story_id"], gold["text"])
        (out / path.name).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{gold['story_id']}: {time.time() - t0:.1f}s, " + ", ".join(f"{len(doc[k])} {k}" for k in LISTS),
              flush=True)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    per_story = []
    for path, gold in gold_docs(args.gold_dir):
        pred_path = Path(args.pred_dir) / path.name
        pred = (json.loads(pred_path.read_text(encoding="utf-8")) if pred_path.exists()
                else {"text": gold["text"], **{k: [] for k in LISTS}})
        per_story.append(score(pred, gold))
        print(f"\n== {gold['story_id']}{'' if pred_path.exists() else '  (no prediction)'}\n{table(per_story[-1])}")
    total = micro(per_story)
    print(f"\n== MICRO AVERAGE over {len(per_story)} stories\n{table(total)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"stories": per_story, "micro": total}, indent=1), encoding="utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wse", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--gold-dir", required=True)
    p.add_argument("--out-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("gold_dir")
    s.add_argument("pred_dir")
    s.add_argument("--json")
    args = ap.parse_args(argv)
    return {"predict": cmd_predict, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
