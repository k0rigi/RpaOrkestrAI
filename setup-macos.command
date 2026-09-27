#!/bin/zsh
# Install the runtime outside Desktop/Documents so iCloud cannot evict it.
set -e
cd -- "${0:A:h}"
trap 'print "Kurulum tamamlanamadı. Yukarıdaki hatayı inceleyin."; read "?Kapatmak için Enter…"' ZERR
runtime_root="$HOME/Library/Application Support/RpaOrkestrAI"
if [[ -x .bootstrap/bin/uv ]]; then
  uv_command="$PWD/.bootstrap/bin/uv"
elif command -v uv >/dev/null 2>&1; then
  uv_command="$(command -v uv)"
else
  print 'uv bulunamadı. Önce https://docs.astral.sh/uv/getting-started/installation/ adresindeki macOS kurulumunu tamamlayın.'
  exit 1
fi
export UV_PYTHON_INSTALL_DIR="$runtime_root/python"
export UV_CACHE_DIR="$HOME/Library/Caches/RpaOrkestrAI/uv"
print 'RpaOrkestrAI yerel çalışma ortamı kuruluyor…'
"$uv_command" python install 3.12
if [[ ! -x "$runtime_root/runtime/bin/python" ]]; then
  "$uv_command" venv --no-project --managed-python --python 3.12 "$runtime_root/runtime"
fi
"$uv_command" pip install --python "$runtime_root/runtime/bin/python" '.[native,automation]'
"$runtime_root/runtime/bin/python" -m playwright install chromium
touch "$runtime_root/runtime/.ready"
print 'Kurulum tamamlandı. start.command ile uygulamayı açabilirsiniz.'
read '?Kapatmak için Enter…'
