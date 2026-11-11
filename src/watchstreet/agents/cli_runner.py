"""Delegates to an external agent CLI (for example ``claude -p``) via stdin/stdout."""

import shlex
import subprocess  # nosec B404 - command is operator-configured, never user input

from watchstreet.agents.base import AgentError, AgentRequest


class CliRunner:
    name = "cli"

    def __init__(self, command: str, timeout_s: float) -> None:
        self._argv = shlex.split(command)
        if not self._argv:
            msg = "WATCHSTREET_AGENT_CLI_COMMAND is empty"
            raise AgentError(msg)
        self._timeout_s = timeout_s

    def complete(self, request: AgentRequest) -> str:
        stdin = f"{request.system}\n\n{request.prompt}"
        try:
            done = subprocess.run(  # noqa: S603  # nosec B603
                self._argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f"Agent CLI failed: {exc}"
            raise AgentError(msg) from exc
        if done.returncode != 0:
            msg = f"Agent CLI exited with {done.returncode}: {done.stderr[:300]}"
            raise AgentError(msg)
        return done.stdout
