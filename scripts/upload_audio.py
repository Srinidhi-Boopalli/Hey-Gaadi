"""Upload a WAV with Python's standard library, bypassing Snap curl issues."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--language", choices=["en", "hi"], default="hi")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"File not found: {args.file}")
    boundary = uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"command.wav\"\r\n"
            "Content-Type: audio/wav\r\n\r\n").encode() + args.file.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(args.url.rstrip("/") + "/voice?" + urlencode({"language": args.language}), data=body,
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urlopen(request, timeout=180) as response:
            print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
    except HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode()}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
