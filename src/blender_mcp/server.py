import os
import subprocess
import typing as t
from collections.abc import Generator
from contextlib import contextmanager

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


class BlenderProcess:
    _process: subprocess.Popen | None = None

    def __init__(self, blender_path: str):
        self.blender_path = blender_path

    @property
    def process(self) -> subprocess.Popen:
        if self._process is None:
            self._process = subprocess.Popen(
                [
                    self.blender_path,
                    "-P",
                    os.path.join(os.path.dirname(__file__), "blender.py"),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )
        return self._process

    def close(self):
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
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(code)
        self.process.stdin.write(separator)

        lines = []
        while (line := self.process.stdout.readline()) and not line.startswith(">>>"):
            lines.append(line)
        return "\n".join(lines)

    def eval_python(self, code: str) -> str:
        return self._run_python(">>>eval", code)

    def exec_python(self, code: str) -> str:
        return self._run_python(">>>exec", code)


@contextmanager
def run_blender(blender_path: str) -> Generator[BlenderProcess, t.Any, None]:
    process = BlenderProcess(blender_path)
    try:
        yield process
    finally:
        process.close()


async def arun(blender_path: str):
    app = Server("blender-mcp")

    with run_blender(blender_path) as blender:

        @app.call_tool()
        async def run_python(name: str, arguments: dict) -> list[types.TextContent]:
            match name:
                case "eval_python":
                    return [
                        types.TextContent(
                            type="text",
                            text=blender.eval_python(arguments["expression"]),
                        )
                    ]
                case "exec_python":
                    return [
                        types.TextContent(
                            type="text", text=blender.exec_python(arguments["code"])
                        )
                    ]
                case n:
                    raise RuntimeError(f"Invalid tool name {n}")

        @app.list_tools()
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="eval_python",
                    description="eval a Python expression in Blender. The bpy module is available. The result of the eval is returned. If an exception occurs, the backtrace will be returned.",
                    inputSchema={
                        "type": "object",
                        "required": ["expression"],
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Python expression to eval",
                            }
                        },
                    },
                ),
                types.Tool(
                    name="exec_python",
                    description="exec Python code, possibly multiple lines, in Blender. The bpy module is available. If an exception occurs, the backtrace will be returned.",
                    inputSchema={
                        "type": "object",
                        "required": ["code"],
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to exec",
                            }
                        },
                    },
                ),
            ]

        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())


@click.command()
# XXX set platform defaults
@click.option("--blender-path", required=True, help="Path to blender executable")
def main(blender_path: str):
    anyio.run(arun, blender_path)
