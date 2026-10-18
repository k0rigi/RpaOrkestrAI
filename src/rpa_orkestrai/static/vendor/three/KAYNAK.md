# Three.js yerel kopyası

Sürüm: **0.160.0 (r160)**. Mevcut web ofisiyle aynı sürüm kullanılır; farklı
WebGL davranışlarını sürüm değişikliğiyle aynı anda devreye almamak için sürüm
sabit tutulmuştur. ES modülü, OrbitControls ve MIT lisansı resmî
[Three.js deposunun r160 etiketinden](https://github.com/mrdoob/three.js/tree/r160)
13 Ekim 2026 tarihinde alınmıştır. Kullanıcının kendi ofis modelini (GLB) açmak
için GLTFLoader ve onun kullandığı BufferGeometryUtils aynı etiketten 18 Ekim 2026
tarihinde eklenmiş, özetleri npm'deki `three@0.160.0` paketiyle de
karşılaştırılmıştır. Kaynak dosyalar değiştirilmemiştir.

Her dosyanın kaynak adresi ve SHA-256 özeti `manifest.json` içindedir.
`package_check` dosyaların varlığını, sürümü ve özetlerini doğrular.
Uygulama çalışırken bu kaynaklara veya CDN'e istek gönderilmez.
Import map yalnız `/vendor/three/` altındaki paketlenmiş dosyaları gösterir.

Güncellemede beş dosya birlikte değiştirilir; manifest özetleri, paket öz-testi
ve WebGL / 2D yedek görünüm testleri yeniden çalıştırılır. Yeni üçüncü taraf
dosyaları eklenirse lisansları da pakete alınır.
