from pathlib import Path

import pytest
from robot.api import get_model

import robocop
from robocop.config import Config
from robocop.exceptions import InvalidArgumentError
from robocop.rules import Message, Rule, RuleParam, RuleSeverity
from robocop.utils import issues_to_lsp_diagnostic


@pytest.fixture
def rule():
    return Rule(
        RuleParam(name="param_name", converter=int, default=1, desc=""),
        rule_id="0101",
        name="some-message",
        msg="Some description",
        severity=RuleSeverity.WARNING,
        help_url="https://fake.com/rules-docs",
    )


@pytest.fixture
def rule_without_help():
    return Rule(
        rule_id="0102",
        name="another-message",
        msg="Another description",
        severity=RuleSeverity.INFO,
    )


def run_check_on_string(in_memory, root="."):
    config = robocop.Config(root=root)
    robocop_runner = robocop.Robocop(config=config)
    robocop_runner.reload_config()

    ast_model = get_model(in_memory)
    file_path = str(Path(Path.home(), "directory", "file.robot"))
    return robocop_runner.run_check(ast_model, file_path, in_memory)


class TestAPI:
    def test_run_check_in_memory(self):
        in_memory = "*** Settings ***\n\n"
        issues = run_check_on_string(in_memory)
        expected_issues = {
            "Missing documentation in suite",
            "Section '*** Settings ***' is empty",
            "Too many blank lines at the end of file",
            "No tests in 'file.robot' file, consider renaming to 'file.resource'",
        }
        actual_issues = {issue.desc for issue in issues}
        assert expected_issues == actual_issues

    def test_run_check_in_memory_with_windows_line_endings(self):
        in_memory = "*** Settings *** \r\n\r\n"
        issues = run_check_on_string(in_memory)
        expected_issues = {
            "Missing documentation in suite",
            "Section '*** Settings ***' is empty",
            "Trailing whitespace at the end of line",
            "Too many blank lines at the end of file",
            "No tests in 'file.robot' file, consider renaming to 'file.resource'",
        }
        actual_issues = {issue.desc for issue in issues}
        assert expected_issues == actual_issues

    def test_run_check_in_memory_with_mac_line_endings(self):
        in_memory = "*** Settings *** \r\r"
        issues = run_check_on_string(in_memory)
        expected_issues = {
            "Missing documentation in suite",
            "Section '*** Settings ***' is empty",
            "Trailing whitespace at the end of line",
            "Too many blank lines at the end of file",
            "No tests in 'file.robot' file, consider renaming to 'file.resource'",
        }
        actual_issues = {issue.desc for issue in issues}
        assert expected_issues == actual_issues

    def test_run_check_in_memory_with_config(self):
        config_path = Path(Path(__file__).parent.parent, "test_data", "api_config")
        in_memory = "*** Settings ***\n\n"
        issues = run_check_on_string(in_memory, root=str(config_path))
        issues_by_desc = [issue.desc for issue in issues]
        assert "Missing documentation in suite" in issues_by_desc
        assert "Section is empty" not in issues_by_desc

    def test_invalid_config(self):
        config_path = Path(Path(__file__).parent.parent, "test_data", "api_invalid_config")

        with pytest.raises(InvalidArgumentError) as exception:
            Config(root=config_path)
        assert r"Invalid configuration for Robocop:\nunrecognized arguments: --some" in str(exception)

    def test_lsp_diagnostic(self, rule, rule_without_help):
        issues = [
            Message(
                rule=rule,
                msg=rule.get_message(),
                source=r"C:\directory\file.robot",
                node=None,
                lineno=10,
                col=10,
                end_lineno=11,
                end_col=50,
            ),
            Message(
                rule=rule_without_help,
                msg=rule_without_help.get_message(),
                source=r"C:\directory\file.robot",
                node=None,
                lineno=1,
                col=1,
                end_lineno=None,
                end_col=None,
            ),
        ]
        expected_diagnostic = [
            {
                "range": {
                    "start": {"line": 9, "character": 9},
                    "end": {"line": 10, "character": 49},
                },
                "severity": 2,
                "code": "0101",
                "source": "robocop",
                "message": "Some description",
                "codeDescription": {
                    "href": "https://fake.com/rules-docs",
                },
            },
            {
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 0},
                },
                "severity": 3,
                "code": "0102",
                "source": "robocop",
                "message": "Another description",
            },
        ]
        diagnostic = issues_to_lsp_diagnostic(issues)
        assert diagnostic == expected_diagnostic

    def test_ignore_sys_argv(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["robocorp", "--some", "args.robot"])
        in_memory = "*** Settings ***\n\n"
        issues = run_check_on_string(in_memory)
        expected_issues = {
            "Missing documentation in suite",
            "Section '*** Settings ***' is empty",
            "Too many blank lines at the end of file",
            "No tests in 'file.robot' file, consider renaming to 'file.resource'",
        }
        assert all(issue.desc in expected_issues for issue in issues)

    def test_robocop_api_no_trailing_blank_line_message(self):
        """Bug from #307"""
        in_memory = "*** Test Cases ***\nTest\n    Fail\n    \nTest\n    Fail\n"
        issues = run_check_on_string(in_memory)
        diag_issues = issues_to_lsp_diagnostic(issues)
        assert all(d["message"] != "Missing trailing blank line at the end of file" for d in diag_issues)

    def test_unicode_strings(self):
        in_memory = (
            "*** Variables ***\n${MY_VARIABLE}    Liian pitkä rivi, jossa on ääkkösiä. "
            "Pituuden tarkistuksen pitäisi laskea merkkejä, eikä tavuja.\n"
        )
        issues = run_check_on_string(in_memory)
        diag_issues = issues_to_lsp_diagnostic(issues)
        assert all(d["message"] != "Line is too long" for d in diag_issues)
