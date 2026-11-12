"""Unit tests for the pure helpers used by the pipeline.

These run in CI without the heavy OCR dependencies (PaddleOCR, Docling).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.pipeline.analyzer import (
    html_table_to_markdown,
    html_tables_to_markdown,
    resolve_image_refs,
)
from app.utils.parallel import split_into_buckets


# --------------------------------------------------------------------------- #
# Page bucketing
# --------------------------------------------------------------------------- #
def test_split_into_buckets_empty():
    assert split_into_buckets([], 4) == []


def test_split_into_buckets_covers_each_item_once_in_order():
    buckets = split_into_buckets(list(range(10)), 3)
    assert [page for bucket in buckets for page in bucket] == list(range(10))
    assert len(buckets) <= 3


def test_split_into_buckets_never_more_buckets_than_items():
    assert len(split_into_buckets([1, 2], 8)) == 2
    assert split_into_buckets([1, 2], 0) == [[1, 2]]


# --------------------------------------------------------------------------- #
# HTML table conversion
# --------------------------------------------------------------------------- #
def test_html_table_to_markdown():
    table = (
        "<table><tr><td>FIELD</td><td>VALUE</td></tr>"
        "<tr><td>UEID</td><td>ABC123</td></tr></table>"
    )
    lines = html_table_to_markdown(table).splitlines()
    assert lines[0] == "| FIELD | VALUE |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| UEID | ABC123 |"


def test_html_table_to_markdown_ignores_non_tables():
    assert html_table_to_markdown("") == ""
    assert html_table_to_markdown("<p>hello</p>") == ""


def test_html_tables_to_markdown_converts_embedded_table():
    text = "Before\n<table><tr><td>A</td><td>B</td></tr></table>\nAfter"
    out = html_tables_to_markdown(text)
    assert "<table" not in out.lower()
    assert "| A | B |" in out


# --------------------------------------------------------------------------- #
# Image reference resolution
# --------------------------------------------------------------------------- #
def test_resolve_image_refs_replaces_missing_files(tmp_path):
    markdown = '<div><img src="imgs/missing.jpg" alt="x"></div>'
    assert resolve_image_refs(markdown, base_dir=str(tmp_path)) == "<div>[Image]</div>"


def test_resolve_image_refs_keeps_existing_files(tmp_path):
    (tmp_path / "real.png").write_bytes(b"x")
    markdown = '<img src="real.png">'
    assert resolve_image_refs(markdown, base_dir=str(tmp_path)) == markdown


def test_resolve_image_refs_ignores_text_without_images():
    assert resolve_image_refs("plain text", base_dir="/nonexistent") == "plain text"
