"""
Command line (run from backend/):

    python -m app.evaluation convert ANNOTATION.json... --text-dir STORIES_DIR --out-dir GOLD_DIR
        teammate annotation files -> gold documents GOLD_DIR/<story_id>.json (+ <story_id>.issues.txt)

    python -m app.evaluation score GOLD_DIR PRED_DIR [--json OUT.json]
        per-story and micro-averaged scores; a story without a prediction is scored as an empty prediction

Predictions come from ../extractor (`python -m extractor predict` there).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from app.evaluation.convert import convert_annotation
from app.evaluation.score import format_table, micro_average, score_document

LISTS = ("mentions", "coreference_clusters", "events", "relationships", "facts", "temporal_expressions",
         "temporal_relations")


def _write(out_dir: Path, story_id: str, doc: Dict[str, Any], issues: List[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{story_id}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"{story_id}.issues.txt").write_text("".join(f"{i}\n" for i in issues), encoding="utf-8")


def cmd_convert(args: argparse.Namespace) -> int:
    for path in args.annotations:
        ann = json.loads(Path(path).read_text(encoding="utf-8"))
        text = (Path(args.text_dir) / ann["source_file"]).read_text(encoding="utf-8")
        doc, issues = convert_annotation(ann, text)
        _write(Path(args.out_dir), doc["story_id"], doc, issues)
        schema = sum(i.startswith("schema:") for i in issues)
        print(f"{doc['story_id']}: {len(doc['mentions'])} mentions, {len(doc['events'])} events, "
              f"{len(issues)} issues ({schema} schema errors)")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    per_story = []
    for gold_path in sorted(Path(args.gold_dir).glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        pred_path = Path(args.pred_dir) / gold_path.name
        pred = (json.loads(pred_path.read_text(encoding="utf-8")) if pred_path.exists()
                else {"text": gold["text"], **{k: [] for k in LISTS}})
        s = score_document(pred, gold)
        per_story.append(s)
        print(f"\n== {gold['story_id']}{'' if pred_path.exists() else '  (no prediction)'}\n{format_table(s)}")
    total = micro_average(per_story)
    print(f"\n== MICRO AVERAGE over {len(per_story)} stories\n{format_table(total)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"stories": per_story, "micro": total}, indent=1), encoding="utf-8")
    return 0


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.evaluation", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("annotations", nargs="+")
    c.add_argument("--text-dir", required=True)
    c.add_argument("--out-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("gold_dir")
    s.add_argument("pred_dir")
    s.add_argument("--json")
    args = ap.parse_args(argv)
    return {"convert": cmd_convert, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
