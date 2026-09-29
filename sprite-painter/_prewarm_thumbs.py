"""Pre-generate thumbnails into /tmp/monkey-thumb-cache/.

Reads jobs from stdin, one per line: path\t_\treference(0|1)\t_
The cache key is computed from path stat. Runs independently from the server.
"""
import hashlib, io, sys
from pathlib import Path

THUMB_DIR = Path('/tmp/monkey-thumb-cache')
THUMB_DIR.mkdir(exist_ok=True)

try:
    from PIL import Image
except ImportError:
    sys.exit(0)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split('\t')
    if len(parts) < 3:
        continue
    path = parts[0]
    reference = parts[2] == '1'
    try:
        p = Path(path)
        st = p.stat()
        cache_key = hashlib.md5(f'{path}:{st.st_mtime_ns}:{reference}'.encode()).hexdigest()
        out_path = THUMB_DIR / (cache_key + '.png')
        if out_path.exists():
            continue
        data = p.read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert('RGBA')
            image.thumbnail((240, 180), Image.Resampling.NEAREST if reference else Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format='PNG')
            out_path.write_bytes(buf.getvalue())
    except Exception:
        pass
