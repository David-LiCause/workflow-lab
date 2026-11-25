"""Tests for text_to_structured_data. Unit tests use MockLLM only. Live tests: integration/."""

import json

import pytest
from pydantic import BaseModel, Field

from agents_playground.components.text_to_structured_data import (
    ExtractionResult,
    extract,
    split_into_chunks,
)
from agents_playground.llm import MockLLM


class Company(BaseModel):
    name: str = Field(description="Company name as written in the text.")
    funding_usd: int | None = Field(None, description="Total funding raised, in whole US dollars.")


def item(data: dict | str, confidence: float = 0.9, notes: str = "") -> dict:
    """One raw row as the LLM returns it."""
    data_json = data if isinstance(data, str) else json.dumps(data)
    return {"data_json": data_json, "extraction_confidence": confidence, "extraction_notes": notes}


def reply(*items: dict) -> dict:
    return {"rows": list(items)}


def run(llm: MockLLM, text: str = "Acme raised $5M.", **kwargs) -> ExtractionResult[Company]:
    return extract(text, Company, llm, **kwargs)


def make_text(n_paragraphs: int, lines_per: int = 3) -> str:
    return "\n\n".join(
        "\n".join(f"line {p}.{i} " + "x" * 20 for i in range(lines_per))
        for p in range(n_paragraphs)
    )


# R1


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_r1_empty_text_returns_empty_result_without_llm_call(text):
    llm = MockLLM()
    result = run(llm, text)
    assert result.rows == [] and result.rejected == []
    assert llm.calls == []


# R2


def test_r2_short_text_is_one_chunk_and_one_call():
    llm = MockLLM(structured_replies=[reply(item({"name": "Acme"}))])
    result = run(llm, "Acme raised $5M.", max_chunk_chars=1000)
    assert len(llm.calls) == 1
    assert [r.row for r in result.rows] == [Company(name="Acme")]
    assert split_into_chunks("short text", 1000) == ["short text"]


# R3


def test_r3_long_text_splits_on_paragraph_boundaries_and_never_mid_line():
    text = make_text(6)
    chunks = split_into_chunks(text, 200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    original_lines = set(text.splitlines())
    assert all(line in original_lines for c in chunks for line in c.splitlines())
    # every chunk starts at a paragraph start, so paragraphs are intact
    assert all(c.splitlines()[0].endswith(".0 " + "x" * 20) for c in chunks)
    # nothing lost, order kept
    assert [ln for c in chunks for ln in c.splitlines() if ln] == [
        ln for ln in text.splitlines() if ln
    ]


def test_r3_heading_starts_a_new_chunk_even_without_blank_line():
    text = "# A\nrow a1\nrow a2\n# B\nrow b1\nrow b2"
    chunks = split_into_chunks(text, 25)
    assert chunks == ["# A\nrow a1\nrow a2", "# B\nrow b1\nrow b2"]


def test_r3_small_paragraphs_are_packed_together_up_to_the_limit():
    text = "aaaa\n\nbbbb\n\ncccc"
    assert split_into_chunks(text, 1000) == [text]
    assert len(split_into_chunks(text, 12)) == 2


# R4


def test_r4_oversize_paragraph_splits_between_lines():
    table = "\n".join(f"| co{i} | {i} |" for i in range(30))
    chunks = split_into_chunks(table, 100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    assert "\n".join(chunks) == table


def test_r4_single_line_longer_than_limit_is_its_own_unsplit_chunk():
    long_line = "y" * 300
    chunks = split_into_chunks(f"intro\n\n{long_line}\n\noutro", 50)
    assert long_line in chunks
    assert chunks == ["intro", long_line, "outro"]


# R5


def test_r5_chunks_are_extracted_separately_and_combined_in_order():
    text = make_text(4)
    n = len(split_into_chunks(text, 150))
    assert n > 1
    llm = MockLLM(structured_replies=[reply(item({"name": f"Co{i}"})) for i in range(n)])
    result = run(llm, text, max_chunk_chars=150)
    assert len(llm.calls) == n
    assert [r.row.name for r in result.rows] == [f"Co{i}" for i in range(n)]


def test_r5_prompt_contains_schema_instructions_and_chunk_text():
    llm = MockLLM(structured_replies=[reply()])
    run(llm, "Acme raised $5M.", instructions="Only count US companies.")
    prompt = "\n".join(m.content for m in llm.calls[0])
    assert "funding_usd" in prompt  # row model schema
    assert "Total funding raised, in whole US dollars." in prompt  # field description
    assert "Only count US companies." in prompt
    assert "Acme raised $5M." in prompt


def test_r5_prompt_omits_instructions_section_when_none_given():
    llm = MockLLM(structured_replies=[reply()])
    run(llm)
    assert "None" not in "\n".join(m.content for m in llm.calls[0])


# R6


def test_r6_valid_rows_keep_confidence_and_notes():
    llm = MockLLM(
        structured_replies=[
            reply(
                item({"name": "Acme", "funding_usd": 5_000_000}, 0.95, "from table"),
                item({"name": "Beta"}, 0.6),
            )
        ]
    )
    result = run(llm)
    assert result.rejected == []
    first, second = result.rows
    assert first.row == Company(name="Acme", funding_usd=5_000_000)
    assert first.extraction_confidence == 0.95
    assert first.extraction_notes == "from table"
    assert second.extraction_confidence == 0.6


# R7


def test_r7_invalid_row_is_rejected_with_validation_error_and_raw_data():
    bad = {"name": "Acme", "funding_usd": "lots"}
    llm = MockLLM(structured_replies=[reply(item(bad, 0.9, "n"), item({"name": "Good"}))])
    result = run(llm)
    assert [r.row.name for r in result.rows] == ["Good"]
    (rejected,) = result.rejected
    assert rejected.kind == "validation_error"
    assert rejected.raw == bad
    assert "funding_usd" in rejected.reason
    assert rejected.extraction_confidence == 0.9
    assert rejected.extraction_notes == "n"


# R8


@pytest.mark.parametrize("data_json", ["{not json", "[1, 2]", '"just a string"'])
def test_r8_non_object_json_is_rejected(data_json):
    llm = MockLLM(structured_replies=[reply(item(data_json))])
    result = run(llm)
    assert result.rows == []
    (rejected,) = result.rejected
    assert rejected.kind == "validation_error"
    assert rejected.raw == data_json or rejected.raw == json.loads(data_json)
    assert rejected.reason


# R9


def test_r9_low_confidence_row_is_rejected_but_threshold_itself_passes():
    llm = MockLLM(
        structured_replies=[
            reply(
                item({"name": "Low"}, 0.3, "guessed"),
                item({"name": "Edge"}, 0.5),
            )
        ]
    )
    result = run(llm, min_confidence=0.5)
    assert [r.row.name for r in result.rows] == ["Edge"]
    (rejected,) = result.rejected
    assert rejected.kind == "low_confidence"
    assert rejected.raw == {"name": "Low"}
    assert rejected.extraction_confidence == 0.3
    assert rejected.extraction_notes == "guessed"
    assert "0.3" in rejected.reason and "0.5" in rejected.reason


# R10


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_r10_confidence_outside_0_to_1_is_rejected(confidence):
    llm = MockLLM(structured_replies=[reply(item({"name": "Acme"}, confidence))])
    result = run(llm, min_confidence=0.0)
    assert result.rows == []
    assert result.rejected[0].kind == "validation_error"


# R11


def test_r11_invalid_and_low_confidence_is_reported_as_validation_error():
    llm = MockLLM(structured_replies=[reply(item({"funding_usd": 1}, 0.1))])
    result = run(llm)
    assert result.rejected[0].kind == "validation_error"
    assert "name" in result.rejected[0].reason


# R12


def test_r12_zero_extracted_rows_is_an_empty_result():
    llm = MockLLM(structured_replies=[reply()])
    result = run(llm, "Nothing relevant here.")
    assert result.rows == [] and result.rejected == []


# R13, R14


def test_r13_cache_writes_json_file_and_r14_hit_makes_no_llm_call(tmp_path):
    cache = tmp_path / "nested" / "cache"
    first_llm = MockLLM(structured_replies=[reply(item({"name": "Acme"}, 0.9, "note"))])
    first = run(first_llm, cache_dir=cache)
    files = list(cache.glob("*.json"))
    assert len(files) == 1
    json.loads(files[0].read_text())  # valid JSON

    second_llm = MockLLM()
    second = run(second_llm, cache_dir=cache)
    assert second_llm.calls == []
    assert second == first


def test_r14_cache_hit_with_multiple_chunks_replays_all_rows(tmp_path):
    text = make_text(4)
    n = len(split_into_chunks(text, 150))
    llm = MockLLM(structured_replies=[reply(item({"name": f"Co{i}"})) for i in range(n)])
    first = run(llm, text, max_chunk_chars=150, cache_dir=tmp_path)
    again = run(MockLLM(), text, max_chunk_chars=150, cache_dir=tmp_path)
    assert again == first
    assert len(again.rows) == n


# R15


def test_r15_cache_stores_raw_output_so_threshold_changes_need_no_llm_call(tmp_path):
    llm = MockLLM(structured_replies=[reply(item({"name": "Mid"}, 0.6))])
    strict = run(llm, min_confidence=0.9, cache_dir=tmp_path)
    assert strict.rows == [] and len(strict.rejected) == 1

    lenient_llm = MockLLM()
    lenient = run(lenient_llm, min_confidence=0.5, cache_dir=tmp_path)
    assert lenient_llm.calls == []
    assert [r.row.name for r in lenient.rows] == ["Mid"]


# R16


def test_r16_changing_text_schema_instructions_or_model_is_a_cache_miss(tmp_path):
    def fresh() -> MockLLM:
        return MockLLM(structured_replies=[reply(item({"name": "Acme"}))])

    class OtherRow(BaseModel):
        name: str = Field(description="Name.")

    base = fresh()
    run(base, cache_dir=tmp_path, instructions="a")
    assert len(base.calls) == 1

    variants = [
        (fresh(), dict(text="Different text.", instructions="a")),
        (fresh(), dict(instructions="b")),
        (MockLLM(structured_replies=[reply(item({"name": "Acme"}))], model="other"), {}),
    ]
    for llm, kwargs in variants:
        kwargs.setdefault("instructions", "a")
        text = kwargs.pop("text", "Acme raised $5M.")
        extract(text, Company, llm, cache_dir=tmp_path, **kwargs)
        assert len(llm.calls) == 1

    other_schema = fresh()
    extract("Acme raised $5M.", OtherRow, other_schema, instructions="a", cache_dir=tmp_path)
    assert len(other_schema.calls) == 1

    # and the original is still a hit
    same = MockLLM()
    run(same, cache_dir=tmp_path, instructions="a")
    assert same.calls == []


# R17


def test_r17_corrupt_cache_file_is_a_miss_and_is_overwritten(tmp_path):
    llm = MockLLM(structured_replies=[reply(item({"name": "Acme"}))])
    run(llm, cache_dir=tmp_path)
    (path,) = tmp_path.glob("*.json")
    path.write_text("{ corrupt")

    llm2 = MockLLM(structured_replies=[reply(item({"name": "Acme"}))])
    result = run(llm2, cache_dir=tmp_path)
    assert len(llm2.calls) == 1
    assert [r.row.name for r in result.rows] == ["Acme"]
    json.loads(path.read_text())  # repaired

    llm3 = MockLLM()
    run(llm3, cache_dir=tmp_path)
    assert llm3.calls == []


# R18


def test_r18_no_cache_dir_writes_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(MockLLM(structured_replies=[reply(item({"name": "Acme"}))]))
    assert list(tmp_path.iterdir()) == []


# Errors


@pytest.mark.parametrize(
    "kwargs", [{"min_confidence": 1.5}, {"min_confidence": -0.1}, {"max_chunk_chars": 0}]
)
def test_invalid_arguments_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        run(MockLLM(), **kwargs)


def test_llm_errors_propagate_and_nothing_is_cached(tmp_path):
    text = make_text(4)
    llm = MockLLM(structured_replies=[reply(item({"name": "Co0"})), RuntimeError("api down")])
    with pytest.raises(RuntimeError, match="api down"):
        run(llm, text, max_chunk_chars=150, cache_dir=tmp_path)
    assert list(tmp_path.glob("*.json")) == []


# R19


class Undescribed(BaseModel):
    name: str = Field(description="Company name.")
    hq: str | None = None
    raised: int | None = Field(None, description="  ")


@pytest.mark.parametrize("text", ["Acme raised $5M.", ""])
def test_r19_fields_without_description_raise_before_any_llm_call(text):
    llm = MockLLM()
    with pytest.raises(ValueError, match="hq, raised"):
        extract(text, Undescribed, llm)
    assert llm.calls == []
