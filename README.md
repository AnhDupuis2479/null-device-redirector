# Null Device Redirector

A context manager that redirects stdout and stderr to the operating system's null device (`os.devnull`) at the file-descriptor level, restoring them on exit.

## Usage

```python
from null_device_redirector import null_redirect, NullRedirect

# Functional form
with null_redirect():
    print("this vanishes")
    import os; os.write(2, b"so does this\n")

# Class form (identical behaviour)
with NullRedirect():
    print("this also vanishes")
```

## Why this exists

Some libraries — numpy's C extensions, ctypes calls, anything using `printf` in native code — write directly to file descriptors 1 and 2, bypassing `sys.stdout` and `sys.stderr`. Swapping the Python-level objects (the approach taken by `contextlib.redirect_stdout`) does not silence those writes. This library operates one level lower, using `os.dup2` to point the real file descriptors at `/dev/null` for the duration of the block, so C-level output is caught too.

The trade-off is that this is more invasive: it touches process-global state, so it is not thread-safe with respect to other code that might also be redirecting, and it cannot selectively silence only Python-level output. If you only need to quiet `print()`, use `contextlib.redirect_stdout`.

## Edge cases

If `sys.stdout` or `sys.stderr` has no real file descriptor (for example, when running under a GUI test runner that replaces them with `StringIO`), that stream is silently skipped rather than raising. The other stream, if it has a real fd, is still redirected.

The class is reusable across multiple `with` blocks but not designed for nesting. A nested `with NullRedirect():` inside another `with NullRedirect():` will work in the sense that output stays silenced, but the inner block's exit restores to the outer block's already-null state, discarding the outer block's saved descriptors. Use separate instances if you need layered redirection.

## Exports

- `NullRedirect` — the context manager class.
- `null_redirect()` — factory function returning a new `NullRedirect` instance.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

