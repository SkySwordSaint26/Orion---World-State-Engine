"""Evaluation against the gold annotations (`orion_gold_v1.schema.json`): convert, score."""
from app.evaluation.convert import convert_annotation, span_problem
from app.evaluation.schema import SCHEMA_PATH, load_schema, schema_errors
from app.evaluation.score import format_table, micro_average, score_document

__all__ = ["SCHEMA_PATH", "convert_annotation", "format_table", "load_schema", "micro_average", "schema_errors",
           "score_document", "span_problem"]
