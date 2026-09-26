"""
Command line (run from backend/):

    python -m app.evaluation convert ANNOTATION.json... --text-dir STORIES_DIR --out-dir GOLD_DIR
        teammate annotation files -> gold documents GOLD_DIR/<story_id>.json (+ <story_id>.issues.txt)

    python -m app.evaluation predict --gold-dir GOLD_DIR --out-dir PRED_DIR [--pipeline split|monolithic]
                                     [--log-calls CALLS.jsonl]
        runs the real extractor on each gold document's text -> PRED_DIR/<story_id>.json (+ .issues.txt);
        a failed extraction writes an empty prediction and records the error; --log-calls appends one JSON line
        per LLM call (story, stage, seconds, raw output or error)

    python -m app.evaluation score GOLD_DIR PRED_DIR [--json OUT.json]
        per-story and micro-averaged scores; a story without a prediction is scored as an empty prediction

    python -m app.evaluation demo (--text "A short passage." | --file PASSAGE.txt)
        live run of the four stages on a short passage, printing each stage's output, timing and offset checks
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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


def cmd_predict(args: argparse.Namespace) -> int:
    from app.contracts import project_to_gold                  # imported here: pulls in the pipeline and settings
    from app.pipeline.extractor import ExtractionOrchestrator
    from app.pipeline.llm_client import llm_client

    story = {"id": None}
    if args.log_calls:
        real_generate = llm_client.generate

        def logged_generate(*a: Any, **kw: Any) -> str:
            system = kw.get("system_prompt") or ""
            stage = system.split(" - ")[0] if system.startswith("STAGE") else "monolithic"
            rec = {"story_id": story["id"], "stage": stage, "raw": None, "error": None}
            t0 = time.time()
            try:
                rec["raw"] = real_generate(*a, **kw)
                return rec["raw"]
            except Exception as exc:
                rec["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                rec["seconds"] = round(time.time() - t0, 1)
                with open(args.log_calls, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        llm_client.generate = logged_generate                     # this process only; nothing on disk changes

    orchestrator = ExtractionOrchestrator(pipeline=args.pipeline)
    for gold_path in sorted(Path(args.gold_dir).glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        story["id"] = gold["story_id"]
        t0 = time.time()
        try:
            out = orchestrator.extract_chapter(gold["text"], chapter_number=1)
            proj = project_to_gold(out["observations"], story_id=gold["story_id"], text=gold["text"])
            doc, issues = proj.document, list(proj.issues)
        except Exception as exc:                                  # a failed chapter is a result, not a crash
            doc = {"schema_version": "1.0", "story_id": gold["story_id"], "text": gold["text"],
                   **{k: [] for k in LISTS}}
            issues = [f"extraction failed: {type(exc).__name__}: {exc}"]
        _write(Path(args.out_dir), gold["story_id"], doc, issues)
        status = "FAILED" if doc["mentions"] == [] and issues and issues[0].startswith("extraction failed") else "ok"
        print(f"{gold['story_id']}: {status} in {time.time() - t0:.0f}s, {len(doc['mentions'])} mentions, "
              f"{len(doc['events'])} events, {len(issues)} issues", flush=True)
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


def cmd_demo(args: argparse.Namespace) -> int:
    from app.evaluation.demo import run_demo                   # imported here: pulls in the pipeline and settings

    text = args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8")
    return 0 if run_demo(text) else 1


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.evaluation", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("annotations", nargs="+")
    c.add_argument("--text-dir", required=True)
    c.add_argument("--out-dir", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--gold-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pipeline", choices=("split", "monolithic"), default=None,
                   help="default: settings.EXTRACTION_PIPELINE")
    p.add_argument("--log-calls", help="append one JSON line per LLM call to this file")
    s = sub.add_parser("score")
    s.add_argument("gold_dir")
    s.add_argument("pred_dir")
    s.add_argument("--json")
    d = sub.add_parser("demo")
    src = d.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--file")
    args = ap.parse_args(argv)
    return {"convert": cmd_convert, "predict": cmd_predict, "score": cmd_score, "demo": cmd_demo}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
