import os
import subprocess
import typing as t
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import click
from mcp.server.fastmcp import Context, FastMCP


class BlenderProcess:
    _process: subprocess.Popen | None = None

    def __init__(self, blender_path: str):
        self.blender_path = blender_path

    @property
    def process(self) -> subprocess.Popen:
        if self._process is None:
            self._process = subprocess.Popen(  # noqa: S603
                [
                    self.blender_path,
                    "-P",
                    os.path.join(os.path.dirname(__file__), "blender.py"),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                bufsize=1,
                text=True,
            )
        return self._process

    def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(5)
                except subprocess.TimeoutExpired:
                    return

    def _run_python(self, separator: str, code: str) -> str:
        assert self.process.stdin and self.process.stdout  # noqa: S101
        self.process.stdin.write(code)
        if not code.endswith("\n"):
            self.process.stdin.write("\n")
        self.process.stdin.write(separator)
        self.process.stdin.write("\n")
        self.process.stdin.flush()

        lines = []
        while (line := self.process.stdout.readline()) and not line.startswith(">>>"):
            lines.append(line)
        return "\n".join(lines)

    def eval_python(self, code: str) -> str:
        return self._run_python(">>>eval", code)

    def exec_python(self, code: str) -> str:
        return self._run_python(">>>exec", code)


@dataclass
class BlenderContext:
    blender: BlenderProcess


def blender_lifespan(blender_path: str) -> t.Callable[[FastMCP], t.AsyncContextManager[BlenderContext]]:
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncGenerator[BlenderContext, None]:
        blender = BlenderProcess(blender_path)
        try:
            yield BlenderContext(blender=blender)
        finally:
            blender.close()

    return lifespan


def eval_python(expression: str, ctx: Context) -> str:
    """
    eval a Python expression in Blender.
    The bpy module is available.
    The result of the eval is returned.
    If an exception occurs, the backtrace will be returned.
    """
    blender = ctx.request_context.lifespan_context.blender
    return blender.eval_python(expression)


def exec_python(code: str, ctx: Context) -> str:
    """
    exec Python code, possibly multiple lines, in Blender.
    The bpy module is available.
    If an exception occurs, the backtrace will be returned.
    """
    blender = ctx.request_context.lifespan_context.blender
    return blender.exec_python(code)


@click.command()
# XXX set platform defaults
@click.option("--blender-path", required=True, help="Path to blender executable")
def main(blender_path: str) -> None:
    mcp = FastMCP("blender-mcp", lifespan=blender_lifespan(blender_path), log_level="ERROR")
    mcp.tool()(eval_python)
    mcp.tool()(exec_python)
    mcp.run()  # XXX pass transport
