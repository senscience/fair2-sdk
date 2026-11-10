"""A fix of jupyter_client applied by notebook-runner until a release of jupyter_client has it.

`Session.send` and `send_raw` send on an asyncio socket through a sync shadow of it. If a message
is already waiting, that send can clear the socket's edge-triggered file descriptor: a pending
`await poll()` on the same socket then sleeps until its timeout, although the message is there.
nbclient does such a send when it plays the frontend of an ipywidgets `Output` (a `comm_msg`),
while it waits for the kernel's reply: the cell then takes the whole timeout, and is reported as a
Timeout (jupyter/nbclient#312; py3Dmol displayed in an `Output`, in hw56-vj34).

The fix is jupyter/jupyter_client#1145: after the send, read the socket's events through the
asyncio socket, which makes pyzmq wake its pending polls. It only changes the runner's process,
not the notebooks, nor their kernels.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import zmq
import zmq.asyncio
from jupyter_client import session


def apply() -> None:
    """Patches `Session.send` and `send_raw`, once, unless jupyter_client has its own fix."""
    if hasattr(session, "_wake_async_socket"):  # jupyter_client with #1145
        return
    for name in ("send", "send_raw"):
        method = getattr(session.Session, name)
        if not getattr(method, "_wakes_async_socket", False):
            setattr(session.Session, name, _waking(method))


def _waking(send: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(send)
    def wrapper(self: session.Session, *args: Any, **kwargs: Any) -> Any:
        result = send(self, *args, **kwargs)
        stream = args[0] if args else kwargs.get("stream")
        if isinstance(stream, zmq.asyncio.Socket):
            stream.get(zmq.EVENTS)
        return result

    wrapper._wakes_async_socket = True  # type: ignore[attr-defined]
    return wrapper
