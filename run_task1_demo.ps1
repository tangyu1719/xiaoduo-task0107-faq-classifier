$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
py -m uvicorn task0107_review.app:app --host 127.0.0.1 --port 8017
