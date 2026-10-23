"""
Command line (run from extractor/ with its venv):

    python -m extractor predict --gold-dir GOLD --out-dir PRED
        extracts every gold story's text -> PRED/<story_id>.json

    python -m extractor score GOLD PRED [--json OUT.json]
        per-story and micro-averaged scores (backend metrics + coreference B-cubed)

    python -m extractor run IN.txt OUT.json [--story-id ID]
        extracts one chapter's text -> OUT.json (the backend's extraction calls this)

    python -m extractor predict-v2 GOLD_V2_PATH... --out-dir PRED
        extracts each gold v2 chapter's text (files, or every ch*.json under a directory) -> PRED/<work_id>/chNN.json,
        the layout the backend's `score-v2` reads

GOLD is produced by the backend converter (from backend/):
    python -m app.evaluation convert ../accounts_from_a_lonely_broadcast_station_orion_annotation/*.json \
        --text-dir "../Accounts From a Lonely Broadcast Station" --out-dir ../extractor/data/gold
"""
import argparse
import json
import sys
import time
from pathlib import Path

from extractor.evaluate import corrected, micro, score, table
from extractor.pipeline import LISTS, extract

CORRECTIONS = Path(__file__).resolve().parents[1] / "data" / "gold_corrections.json"


def gold_docs(gold_dir: str):
    fixes = json.loads(CORRECTIONS.read_text(encoding="utf-8")) if CORRECTIONS.exists() else {}
    return [(p, corrected(d, fixes.get(d["story_id"])))
            for p in sorted(Path(gold_dir).glob("*.json")) for d in [json.loads(p.read_text(encoding="utf-8"))]]


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


def cmd_predict_v2(args: argparse.Namespace) -> int:
    paths = []
    for p in map(Path, args.gold):
        paths += sorted(p.rglob("ch*.json")) if p.is_dir() else [p]
    for path in paths:
        gold = json.loads(path.read_text(encoding="utf-8"))
        t0 = time.time()
        doc = {"doc_id": gold["doc_id"], **extract(gold["doc_id"], gold["text"])}
        out = Path(args.out_dir) / f"{gold['doc_id']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{gold['doc_id']}: {time.time() - t0:.1f}s, " + ", ".join(f"{len(doc[k])} {k}" for k in LISTS),
              flush=True)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    progress_file = Path(args.progress_file) if args.progress_file else None

    def report(stage: str, completed: int, total: int) -> None:
        if progress_file:
            with progress_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"stage": stage, "completed": completed, "total": total}) + "\n")
                stream.flush()

    doc = extract(args.story_id or Path(args.input).stem, Path(args.input).read_text(encoding="utf-8"), report)
    Path(args.output).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m extractor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--gold-dir", required=True)
    p.add_argument("--out-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("gold_dir")
    s.add_argument("pred_dir")
    s.add_argument("--json")
    r = sub.add_parser("run")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--story-id")
    r.add_argument("--progress-file")
    v = sub.add_parser("predict-v2")
    v.add_argument("gold", nargs="+")
    v.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    return {"predict": cmd_predict, "score": cmd_score, "run": cmd_run, "predict-v2": cmd_predict_v2}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
