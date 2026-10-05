"""Hypothesis checks for the local and remote command-line interface."""

import io
import json
import runpy
import sys
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src import cli
from src.model import DataModel
from src.rpc import RpcClient, RpcServer


@settings(max_examples=3, derandomize=True)
@given(st.text(max_size=8))
def test_repl_handles_commands_and_errors(locale):
    """REPL accepts operations and reports input/model errors."""
    record = {
        "identifier": 1,
        "time": 1,
        "locale": locale,
        "user_agent": "agent",
    }
    invalid_commands = (
        '{"method":"missing"}',
        '{"method":"get_people","args":[]}',
        '{"method":"edit_person","args":{"identifier":1}}',
        "{}",
        "not json",
    )
    commands = (
        "",
        json.dumps({"method": "create_person", "args": {"record": record}}),
        '{"method":"get_people"}',
        *invalid_commands,
        "exit",
    )
    output = io.StringIO()
    with patch("builtins.input", side_effect=commands):
        with redirect_stdout(output):
            cli.repl(DataModel())
    lines = output.getvalue().splitlines()
    assert json.loads(lines[2]) == record
    assert json.loads(lines[3]) == [record]
    assert sum('"error"' in line for line in lines) == len(invalid_commands)
    with patch("builtins.input", side_effect=EOFError):
        cli.repl(DataModel())


@settings(max_examples=2, derandomize=True)
@given(st.integers(min_value=1024, max_value=65535))
def test_main_selects_all_modes(port):
    """CLI builds the appropriate target and shuts down on Ctrl+C."""
    with patch("sys.argv", ["variant5", "local"]):
        with patch.object(cli, "repl") as repl:
            cli.main()
            assert isinstance(repl.call_args.args[0], DataModel)
    with patch(
        "sys.argv",
        [
            "variant5",
            "client",
            "--host",
            "localhost",
            "--port",
            str(port),
        ],
    ):
        with patch.object(cli, "repl") as repl:
            cli.main()
            target = repl.call_args.args[0]
            assert isinstance(target, RpcClient)
            assert (target.host, target.port) == ("localhost", port)
    with TemporaryDirectory() as directory:
        journal = f"{directory}/journal.log"
        arguments = ["variant5", "server", "--port", "0", "--journal", journal]
        with patch("sys.argv", arguments):
            with patch.object(
                RpcServer, "serve_forever", side_effect=KeyboardInterrupt
            ):
                with redirect_stdout(io.StringIO()) as output:
                    cli.main()
        assert "RPC listening" in output.getvalue()
        assert "Stopped" in output.getvalue()


@settings(max_examples=1)
@given(st.just("local"))
def test_module_entry_point(mode):
    """The module can be launched as python -m src.cli."""
    with patch("sys.argv", ["src.cli", mode]):
        with patch("builtins.input", side_effect=EOFError):
            with redirect_stdout(io.StringIO()):
                with patch.dict(sys.modules):
                    del sys.modules["src.cli"]
                    runpy.run_module("src.cli", run_name="__main__")
