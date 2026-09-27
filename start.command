#!/bin/zsh
set -e
cd -- "${0:A:h}"
runtime_root="$HOME/Library/Application Support/RpaOrkestrAI"
run_studio() {
  if [[ -f "$runtime_root/runtime/.ready" && -x "$runtime_root/runtime/bin/python" ]]; then
    print 'Yerel uygulama ortamı kullanılıyor.'
    # Copy only application code; Python and its packages never live in iCloud.
    mkdir -p "$runtime_root/source" || return $?
    /usr/bin/rsync -rt --delete --exclude '__pycache__' src/rpa_orkestrai "$runtime_root/source/" || return $?
    PYTHONPATH="$runtime_root/source" "$runtime_root/runtime/bin/python" -u -m rpa_orkestrai --native
  else
    .venv/bin/python -u launch.py --native
  fi
}
if [[ ! -f "$runtime_root/runtime/.ready" && ! -x .venv/bin/python ]]; then
  print 'Sanal ortam bulunamadı. README.md içindeki kurulum adımlarını tamamlayın.'
  read '?Kapatmak için Enter tuşuna basın…'
  exit 1
fi
print 'RpaOrkestrAI masaüstü penceresi açılıyor…'
if run_studio; then
  exit 0
else
  result=$?
  print '\nUygulama açılamadı. Yukarıdaki hata mesajını inceleyin.'
  read '?Kapatmak için Enter tuşuna basın…'
  exit $result
fi
