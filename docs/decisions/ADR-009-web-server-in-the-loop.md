# ADR-009: The web server runs inside the app loop (`poll()`), Microdot 2

- **Status:** Accepted (on `feature/microdot-manager`; final once the PR merges)
- **Date:** 2026-10-26

## Context
`MicrodotManager` (v0.1.5) wraps the Microdot web framework. Problems:

- Its `run()` blocks forever (`asyncio.run(...)`), so an `RPIApp` serving web pages
  cannot also run its `loop()` (read sensors, drive motors) — the common case: "a web
  page that shows the soil moisture and opens the valve".
- It imports `microdot_asyncio`, a Microdot **1.x** module. Microdot 2.x (current since
  2023) is asyncio-based on every platform and has no such module; the same
  `from microdot import Microdot` works on the Pico and on CPython.
- `setup()`, `run()` and `stop()` reuse lifecycle names (ADR-002), and `stop()` did
  nothing. `self.app` (the Microdot object) is confusing next to the `app=` argument.

`RPIApp` is synchronous: `run()` calls `loop()` every `loop_interval`. Options:

1. **Background thread** for the server. CPython only in practice: on the Pico the
   second core (`_thread`) plus the WiFi driver is unreliable, and handlers would run
   concurrently with `loop()`, so every device would need locking.
2. **Make `RPIApp` asyncio-based.** Large change to the core and to every example;
   beginners would have to learn `async def`.
3. **Run the server's event loop in slices from `loop()`** (`poll()`), plus a blocking
   `serve_forever()` for apps that only serve.

## Decision
- Option 3. `MicrodotManager` owns a private asyncio event loop with the Microdot
  server running as a task on it:
  - `listen()` binds the port (port-in-use errors surface here, as `OSError`);
  - `poll(timeout_s=0)` runs the event loop for up to `timeout_s`, handling pending
    requests, then returns — call it from `loop()`; it listens on first use;
  - `serve_forever()` blocks until `close()`/Ctrl-C, for serve-only apps;
  - `serve_async()` is the coroutine, for apps that run their own asyncio loop.
- Route handlers run in the app's thread, between `loop()` steps, so they can use
  devices without locks. They must be quick (no `time.sleep`).
- Target **Microdot 2.x** only: CPython via the new `web` extra
  (`pip install rpi-app-framework[web]`, `microdot>=2.0`); on the Pico the user copies
  Microdot's files to `/lib`.
- Names: `route()` decorator and `add_route()`; the Microdot object is `server`. The
  lifecycle-named `setup()`/`run()`/`stop()` are removed.
- `close()` shuts the server down, cancels the task and closes the event loop.

## Consequences
- **Breaking:** constructor `MicrodotManager(name=None, port=8080, host="0.0.0.0",
  log_func=None, app=None)`; `setup()`/`run()`/`stop()`/`run_server_async()` replaced;
  `.app` renamed `.server`; Microdot 1.x no longer supported.
- Request latency is bounded by the app loop: with `loop_interval=0.1` and
  `poll(0.05)`, a request waits at most ~0.1 s. Documented in the device doc.
- A long `loop()` step delays web responses; a slow handler delays `loop()`.
- If `RPIApp` later gains a cooperative scheduler (backlog), `poll()` becomes one of
  its tasks.
