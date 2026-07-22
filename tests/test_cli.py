import json
import os
import subprocess
import sys

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
CONFIG = os.path.join(FIXTURES, "specquotes.toml")


def run_spectate(args, input_text=None):
    return subprocess.run(
        [sys.executable, "-m", "greatspectations", *args],
        input=input_text,
        capture_output=True,
        text=True,
    )


def write_source(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_check_bolt_success(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer:\n"
        "#  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_check_bolt_failure_reports_file_and_line(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: this text does not appear anywhere in the spec\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 1
    assert "example.c:1:cannot find match" in result.stderr


def test_check_bip_success(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BIP #340: A signer MUST use a 32-byte private key.\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 0, result.stderr


def test_check_cmdata_spec_section_hints_avoid_cross_match(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# CMDATA-SPEC/Reader Requirements: A reader: - MUST fail parsing if the length is wrong.\n"
        "# CMDATA-SPEC/Writer Requirements: A writer: - MUST fail parsing if the length is wrong.\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 0, result.stderr


def test_check_cmdata_spec_wrong_hint_fails(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# CMDATA-SPEC/Rationale: A reader: - MUST fail parsing if the length is wrong.\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 1
    assert "example.c:1:" in result.stderr


def test_check_keep_going_reports_all_failures(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: nope one\n"
        "# BOLT #11: nope two\n",
    )
    result = run_spectate(["check", "--config", CONFIG, "-k", source])
    assert result.returncode == 1
    assert result.stderr.count("cannot find match") == 2


def test_check_without_keep_going_stops_at_first_failure(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: nope one\n"
        "# BOLT #11: nope two\n",
    )
    result = run_spectate(["check", "--config", CONFIG, source])
    assert result.returncode == 1
    assert result.stderr.count("cannot find match") == 1


def test_check_json_format(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer:\n"
        "#  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.\n",
    )
    result = run_spectate(["check", "--config", CONFIG, "--format", "json", source])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"] == {"total": 1, "failed": 0}
    assert payload["results"][0]["ok"] is True
    assert payload["results"][0]["source"] == "bolt"
    assert payload["results"][0]["id"] == 11


def test_check_writes_coverage_file(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer:\n"
        "#  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.\n",
    )
    coverage_path = tmp_path / "coverage.txt"
    result = run_spectate(
        ["check", "--config", CONFIG, "--coverage", str(coverage_path), source]
    )
    assert result.returncode == 0, result.stderr
    lines = coverage_path.read_text().splitlines()
    assert len(lines) == 1
    fields = lines[0].split()
    assert fields[0] == "bolt"
    assert fields[1] == "11"


def test_coverage_reports_uncovered_requirement(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer: - MUST set `payment_hash` to the SHA256 of "
        "`payment_preimage`.\n",
    )
    coverage_path = tmp_path / "coverage.txt"
    check_result = run_spectate(
        ["check", "--config", CONFIG, "--coverage", str(coverage_path), source]
    )
    assert check_result.returncode == 0, check_result.stderr

    result = run_spectate(
        ["coverage", "--config", CONFIG, "--coverage", str(coverage_path), "--source", "bolt:11"]
    )
    assert result.returncode == 1
    assert "payment_secret" in result.stdout


def test_coverage_json_format(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer: - MUST set `payment_hash` to the SHA256 of "
        "`payment_preimage`.\n",
    )
    coverage_path = tmp_path / "coverage.txt"
    run_spectate(["check", "--config", CONFIG, "--coverage", str(coverage_path), source])

    result = run_spectate(
        ["coverage", "--config", CONFIG, "--coverage", str(coverage_path),
         "--source", "bolt:11", "--format", "json"]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert any("payment_secret" in g["text"] for g in payload)


def test_coverage_fully_covered_exits_zero(tmp_path):
    source = write_source(
        tmp_path, "example.c",
        "# BOLT #11: A writer: - MUST set `payment_hash` to the SHA256 of "
        "`payment_preimage`. - MUST set `payment_secret` to a fresh, random "
        "value.\n",
    )
    coverage_path = tmp_path / "coverage.txt"
    check_result = run_spectate(
        ["check", "--config", CONFIG, "--coverage", str(coverage_path), source]
    )
    assert check_result.returncode == 0, check_result.stderr

    result = run_spectate(
        ["coverage", "--config", CONFIG, "--coverage", str(coverage_path), "--source", "bolt:11"]
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_check_missing_config_reports_error(tmp_path):
    source = write_source(tmp_path, "example.c", "# BOLT #11: text\n")
    result = run_spectate(
        ["check", "--config", str(tmp_path / "nonexistent.toml"), source]
    )
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_no_command_prints_help():
    result = run_spectate([])
    assert result.returncode == 0
    assert "spectate" in result.stdout
