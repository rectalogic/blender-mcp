import functools
import sys
import threading
import traceback
from queue import Queue

import bpy

SEPARATOR = ">>>"
EVAL_SEPARATOR = f"{SEPARATOR}eval"
EXEC_SEPARATOR = f"{SEPARATOR}exec"

BPY_GLOBALS = {"bpy": bpy}

bpy.context.window.workspace = bpy.data.workspaces.get("Scripting")
bpy.ops.text.new()
text = bpy.data.texts[-1]
text.name = "blender-mcp.py"


def setup():
    for area in bpy.context.screen.areas:
        if area.type == "TEXT_EDITOR":
            area.spaces.active.text = text
            break

    threading.Thread(target=stdio_loop, daemon=True).start()


def execute(code: str, command: str, result: Queue) -> str | None:
    text.from_string(code)
    try:
        if command == EVAL_SEPARATOR:
            return eval(code, BPY_GLOBALS)
        elif command == EXEC_SEPARATOR:
            return exec(code, BPY_GLOBALS)
        else:
            raise RuntimeError(f"Invalid command {command}")
    except Exception as e:
        return "".join(traceback.format_exception(e))


def stdio_loop():
    queue = Queue(1)
    while True:
        lines = []
        while (line := sys.stdin.readline()) and not line.startswith(SEPARATOR):
            lines.append(line)
        code = "\n".join(lines)

        # Execute in main Blender thread
        bpy.app.timers.register(functools.partial(execute, code, line.strip(), queue))
        result = queue.get()
        if result is not None:
            sys.stdout.write(result)
        sys.stdout.write(SEPARATOR)


bpy.app.timers.register(setup, first_interval=0.1)
