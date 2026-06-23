$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
py -m uvicorn app:app --host 127.0.0.1 --port 8017
