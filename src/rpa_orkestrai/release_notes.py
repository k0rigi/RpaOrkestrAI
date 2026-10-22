"""Sürüm notları: Studio'da "Yenilikler" penceresinde gösterilir.

Her yeni sürümde en üste o sürümün kısa, kullanıcıya dönük maddeleri eklenir (testler en üstteki sürümün
uygulamanın sürümüyle aynı olmasını denetler). Ayrıntılı açıklama README ve docs/ içindedir.
"""

from __future__ import annotations

SHOWN = 8  # how many versions the Studio lists

NOTES: list[dict] = [
    {"version": "0.9.42", "date": "2026-10-22", "items": [
        "Yenilikler penceresi: güncellemeden sonra son sürümde nelerin değiştiği gösterilir. Üst çubuktaki sürüm "
        "numarasına veya Ayarlar → Uygulama güncellemeleri → Sürüm notları'na tıklayarak notlara her zaman ulaşırsınız.",
        "Güncelleme artık görünür: Windows'ta kurulum ilerleme penceresi, macOS'ta \"güncelleniyor\" penceresi açılır. "
        "Kurulum bitince Studio kendiliğinden açılır.",
        "Akışın adı, düzenleyicide akışın adına tıklayarak veya Akışlar sayfasındaki Adını değiştir düğmesiyle "
        "değiştirilir. Listeden yapılan değişiklik hemen kaydedilir.",
        "3D ofiste ajana soru sorarken Enter soruyu hemen gönderir; Shift + Enter yeni satıra geçer.",
    ]},
    {"version": "0.9.41", "date": "2026-10-22", "items": [
        "Telegram'dan görev ve soru: /gorev ile yöneticiye veya adı yazılan ajana görev verir, /sor ya da komutsuz "
        "mesajla soru sorarsınız; /ajanlar ofis ve ajanları listeler. Görev bitince sonucu Telegram'a yazılır.",
        "Telegram'dan verilen görevler, sorular, yanıtlar ve onay kararları kayıtlarda \"Telegram'dan\" olarak görünür.",
    ]},
    {"version": "0.9.40", "date": "2026-10-21", "items": [
        "Düğmesi düğme olarak işaretlenmemiş sitelerde (ör. Visual WebGui) Düğme veya bağlantı adı ile tıklama.",
        "Yeni adımlar: Dosya bilgisi ve uzantı kontrolü, Kullanıcıya dosya seçtir. Web'den dosya indir'e izin verilen "
        "uzantılar.",
        "Ofis'te Gösterimi oynat: ajanların görev, araştırma, soru ve sonuç teslimi gerçek iş başlatmadan canlandırılır.",
    ]},
    {"version": "0.9.39", "date": "2026-10-19", "items": [
        "Web öğesine tıkla: tek tık, çift tık, sağ tık, orta tık veya yalnız üzerine gelme.",
    ]},
    {"version": "0.9.38", "date": "2026-10-19", "items": [
        "Telegram'dan soru yanıtlama ve Onayla / Reddet düğmeleriyle onay.",
        "Ofis modeli yerleşim sözleşmesi, örnek ofis ve 3D ofisten görev, soru ve onay.",
        "Yönettiğiniz ofislerin yöneticileri birbirine görev ve soru gönderir.",
    ]},
    {"version": "0.9.37", "date": "2026-10-18", "items": [
        "Bir yetkili birden fazla ofisi yönetir; Ofis listesinden ofisler arasında geçilir.",
    ]},
    {"version": "0.9.36", "date": "2026-10-18", "items": [
        "Ofisinizi kendiniz kurun, Ofisim sekmesi ve kendi 3D ofis modeliniz.",
    ]},
]


def recent() -> list[dict]:
    return [dict(item, items=list(item["items"])) for item in NOTES[:SHOWN]]
