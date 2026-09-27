#!/bin/zsh
set -e
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Sanal ortam bulunamadı. README.md içindeki kurulum adımlarını tamamlayın.'
  read '?Kapatmak için Enter tuşuna basın…'
  exit 1
fi
print 'RpaOrkestrAI masaüstü penceresi açılıyor…'
if .venv/bin/python -u launch.py --native; then
  exit 0
else
  result=$?
  print '\nUygulama açılamadı. Yukarıdaki hata mesajını inceleyin.'
  read '?Kapatmak için Enter tuşuna basın…'
  exit $result
fi
