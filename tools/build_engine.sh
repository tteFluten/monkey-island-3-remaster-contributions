#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE_ROOT="$TASK_ROOT/.playtest/engine"
REVISION=43c1d07613e3c34b9c8cfc7ab168575212864d48
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'This build script targets macOS.' >&2
  exit 1
fi
for command in brew clang make python3 curl; do
  command -v "$command" >/dev/null || { echo "Install $command before building." >&2; exit 1; }
done
for dependency in sdl2-compat libpng zlib pkgconf; do
  brew --prefix "$dependency" >/dev/null 2>&1 || { echo "Missing $dependency. Run: brew install sdl2 libpng zlib pkgconf" >&2; exit 1; }
done
mkdir -p "$ENGINE_ROOT/source" "$ENGINE_ROOT/build"
if [[ ! -f "$ENGINE_ROOT/source/configure" ]]; then
  echo "Downloading COMI-HD $REVISION"
  curl -L --fail --retry 2 "https://api.github.com/repos/harrytyp/comiupscale/tarball/$REVISION" -o "$ENGINE_ROOT/source.tar.gz"
  tar -xzf "$ENGINE_ROOT/source.tar.gz" --strip-components=3 -C "$ENGINE_ROOT/source" '*/scummvm/fork'
  printf '%s\n' "$REVISION" > "$ENGINE_ROOT/revision"
fi
if [[ ! -f "$ENGINE_ROOT/revision" || "$(cat "$ENGINE_ROOT/revision")" != "$REVISION" ]]; then
  echo 'Engine source revision mismatch; move .playtest/engine aside and rebuild.' >&2
  exit 1
fi
chmod +x "$ENGINE_ROOT/source/config.guess" "$ENGINE_ROOT/source/config.sub"
python3 "$TASK_ROOT/tools/engine/patch_engine.py" "$ENGINE_ROOT/source"
cd "$ENGINE_ROOT/build"
bash ../source/configure --disable-all-engines --enable-engine=scumm,scumm-7-8 \
  --enable-optimizations \
  --opengl-mode=gl --disable-nasm \
  --with-sdl-prefix="$(brew --prefix sdl2-compat)" \
  --with-png-prefix="$(brew --prefix libpng)" --with-zlib-prefix="$(brew --prefix zlib)"
grep -q '^ENABLE_SCUMM_7_8 = 1' config.mk || { echo 'SCUMM v8 is missing'; exit 1; }
grep -q '^MACOSX = 1' config.mk || { echo 'macOS backend is missing'; exit 1; }
grep -q '^USE_PNG = 1' config.mk || { echo 'PNG support is missing'; exit 1; }
grep -Eq '^CXXFLAGS.*-O[23s]' config.mk || { echo 'Optimized engine build is required'; exit 1; }
make -j"$(sysctl -n hw.ncpu)"
printf '%s\n' "$REVISION" > "$ENGINE_ROOT/revision"
echo "Mac engine ready: $ENGINE_ROOT/build/scummvm"
