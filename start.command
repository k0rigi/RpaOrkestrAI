#!/bin/zsh
set -e
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Sanal ortam bulunamadı. README.md içindeki kurulum adımlarını tamamlayın.'
  read '?Kapatmak için Enter tuşuna basın…'
  exit 1
fi
exec .venv/bin/python -m rpa_orkestrai --native
