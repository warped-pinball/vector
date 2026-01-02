# Vector HTTP API docs

The files in this directory are generated automatically from `src/common/backend.py` using the script `tools/gen_api_docs.py`. The generator works purely on static analysis and does **not** import the MicroPython runtime.

## Running locally

```bash
python tools/gen_api_docs.py
```

This rewrites `docs/index.html` (and `docs/api/index.html`) with the latest routes discovered in `backend.py`.

## Optional structured docstrings

Handlers can include an `@api ... @end` block inside a docstring to enrich the output. The format is YAML-like and designed to stay lightweight so docstrings can be stripped in firmware builds.

Example:

```python
"""
@api
summary: Update a player record
auth: true
request:
  query:
    - name: id
      type: int
      required: true
      description: Player index
  body:
    - name: initials
      type: string
      required: true
      description: 3-letter initials
response:
  status_codes:
    - code: 200
      description: OK
  body:
    description: Example payload
    example: {"success": true}
@end
"""
```

If the block is missing or malformed, the generator falls back to inferring request keys from references like `request.data["..."]`, `request.args.get("...")`, and `request.headers.get("...")`.
