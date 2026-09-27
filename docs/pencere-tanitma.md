# ERP penceresini tanıtma

İade faturası süreci, genel adım havuzunu geliştirmek için ilk örnektir. Pencere tanıma, tıklama, metin yazma ve Sheets okuma adımları başka masaüstü uygulamalarında da kullanılabilir.

## İlk adım: Pencereyi tanı

1. ERP uygulamasını açın ve ilgili pencereyi görünür hale getirin. Küçültülmüş veya başka masaüstündeki pencereler listelenmez.
2. Studio'da akışınıza **Pencereyi tanı** ekleyin.
3. Sağ panelde **Açık pencerelerden seç** düğmesine basın. ERP penceresini seçin. Uygulama adı ve başlığı otomatik doldurulur.
4. **Şimdi kontrol et** ile eşleşmeyi doğrulayın. Bu düğme yalnız pencere bilgilerini okur; tıklama veya yazma yapmaz.
5. Başlık belge numarası gibi değişken bilgi içeriyorsa sabit kısmını yazıp **İçerir** seçin. Uygulama adı tam eşleşir. Birden fazla sonuç varsa işlem durur; daha belirgin başlık kullanın.
6. Akışı kaydedin. Pencere her çalıştırmada yeniden bulunur; geçici pencere kimliği akış dosyasına kaydedilmez.

Varsayılan çıktı `erp_window` olur. `${erp_window.found}` pencerenin bulunup bulunmadığını, `${erp_window}` ise sonraki pencere adımlarına verilecek pencere bilgisini taşır. Bulunan sonuç ayrıca `title`, `application`, `x`, `y`, `width`, `height` alanlarını içerir. Bulunamayan sonuç yalnız `found: false` içerir.

Varsayılan olarak pencere 5 saniye beklenir; bulunamazsa akış durur. Alternatif olarak **Bulunamadı sonucu ile devam et** seçip sonraki **Koşul** adımında `${erp_window.found}` değerini **Dolu / doğru** ile değerlendirin. İşlemleri koşulun Evet dalına yerleştirin. Pencere bulunamazsa bu dal çalışmaz.

Bu adım **uygulama adı ve pencere başlığını** tanır. Pencere içindeki formun doğru sayfada olduğunu, bir alanın hazır olduğunu veya bir iş kaydının doğruluğunu görsel olarak doğrulamaz. ERP aynı başlıkla farklı formlar gösteriyorsa bunları ayırmak için ileride ayrı ekran/görsel tanıma adımı eklenmelidir.

## Sheets'teki değeri ERP alanına yazma

Başlangıç düzeni:

1. **Pencereyi tanı** → `erp_window`. Pencere bulunamazsa devam et seçeneğini seçin.
2. **Koşul** → sol değer `${erp_window.found}`, karşılaştırma **Dolu / doğru**.
3. Evet dalında **Sheets hücresini oku** → tablo kimliği, sayfa adı ve örneğin `A2`; çıktı `cell_value`.
4. Aynı dalda **Pencerede tıkla** → pencere `${erp_window}`, hedef alanın pencere içi X/Y koordinatları.
5. Aynı dalda **Pencereye metin yaz** → pencere `${erp_window}`, metin `${cell_value}`.

Google bağlantısı için **Bağlantılar ve ayarlar** bölümünde servis hesabı JSON dosyasının yolunu tanımlayın ve ilgili tabloyu bu hesabın e-posta adresiyle paylaşın. Tablo kimliği Google Sheets adresindeki `/d/` ile `/edit` arasındaki bölümdür. `Sheets hücresini oku` tek bir hücreyi metin olarak döndürür; hücre boşsa akışı durdurur. Bu işlem faturayı ERP'de kaydetmez veya onaylamaz.

Tıklama konumu, **başlık çubuğu dahil pencerenin sol üst köşesine göre** verilir. Pencere taşınırsa yeni konumu kullanılır. Boyut, tema veya ekran ölçeği değişince alan koordinatlarını yeniden kontrol edin. Mevcut masaüstü tıklama altyapısı ana ekranla sınırlıdır; ERP'yi ana ekrana alın. Metin yazma odaktaki alana yazar ve mevcut içeriği otomatik temizlemez; önce tıklama adımıyla alanı seçin.

Her tıklama/yazma adımı hedef pencereyi öne getirmeye çalışır ve odağı doğrular. Pencere kapanır, başlığı değişir veya odak doğrulanamazsa işlem durur. Başlık değişen bir ekrana geçtikten sonra yeniden **Pencereyi tanı** ekleyin. Çalışırken odağı başka uygulamaya geçirmeyin; kontrol ile gerçek giriş arasındaki kullanıcı/işletim sistemi değişimleri bütünüyle engellenemez.

**Deneme modu** pencereyi aramaz, Sheets'e bağlanmaz ve fare/klavye kullanmaz. Dış adımların çıktısını bilinmeyen olarak işaretler. Gerçek eşleşmeyi tasarım sırasında **Şimdi kontrol et** ile, gerçek akışı ise Deneme modu kapalıyken doğrulayın.

## macOS ve Windows

- **macOS:** `.[automation]` paketleri gereklidir. Başlıkları okumak için Ekran Kaydı, öne getirme ve giriş için Erişilebilirlik / Otomasyon izinleri gerekir. İzni uygulamayı başlatan Python/Terminal için verip uygulamayı yeniden açın. Eksik izin varsa Studio açıklayıcı hata gösterir.
- **Windows:** Pencere listeleme Windows API'sini kullanır. Tıklama/yazma için `.[automation]` paketleri gerekir. İşletim sistemi odak değişikliğine izin vermezse adım durur; ERP'yi elle öne alıp yeniden deneyin. Yükseltilmiş yetkiyle çalışan uygulamalar ve farklı oturumlar girişe izin vermeyebilir.
- Aynı ERP'nin uygulama adı ve başlığı iki işletim sisteminde farklı olabilir. Akışı başka bilgisayara taşıdıktan sonra o bilgisayardaki ERP penceresini yeniden seçin; tıklama koordinatlarını da doğrulayın.

Bu beş adımın her biri yıldızlanabilir. Favoriler kütüphanenin üstünde **Sık kullanılanlar** bölümünde görünür.
