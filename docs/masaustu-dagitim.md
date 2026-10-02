# Terminal gerektirmeyen masaüstü uygulaması

Son kullanıcı için Windows dağıtımı `RpaOrkestrAI-Setup-<sürüm>-Windows-x64.exe`, macOS dağıtımı `.app` içeren `.dmg` biçimindedir. Python 3.12 ve uygulamanın Python paketleri derlemeye dahil edilir; kullanıcı kaynak kod, sanal ortam veya terminal ile uğraşmaz. Bilgisayarda ayrıca Python 3.14 olması paketin çalışmasını değiştirmez. Kaynak koddan geliştirme ise standart 64 bit Python 3.11–3.14 ile desteklenir.

## Doğrudan indirme

[RpaOrkestrAI indirme sayfası](https://orkestrai.net/rpa/) doğrudan Windows ve macOS paketlerine ayrılmıştır. GitHub alternatifinde [Releases](https://github.com/k0rigi/RpaOrkestrAI/releases) sayfasındaki **Assets** bölümünü kullanın; özel depoya erişen GitHub hesabıyla giriş gerekir. 0.2.0 dosyaları `RpaOrkestrAI-Setup-0.2.0-Windows-x64.exe` ve Apple Silicon Mac için `RpaOrkestrAI-0.2.0-macOS-arm64.dmg` adındadır.

Önceki macOS indirmesi ZIP içinde ZIP içeriyordu. İndirme bütünlüğü doğrulanmasına rağmen Arşiv İzlencesi'nde açma hatası görüldüğü için dağıtım DMG'ye geçirildi. DMG'yi çift tıklayın ve uygulamayı içindeki **Applications** kısayoluna sürükleyin. `start.command` paketlenmiş uygulamanın başlatıcısı değildir; terminale bağlı kaynak kod sürümünü çalıştırır.

## Otomatik güncellemenin başlangıcı

0.1.x paketlerinde güncelleme istemcisi yoktur; **0.2.0 ilk kez elle kurulmalıdır**. Bundan sonra uygulama açılışta imzalı sürüm bildirimini arka planda kontrol eder, daha yeni paketi doğrulayıp indirir ve sonraki açılışta kurar. Bağlantı veya doğrulama sorunu mevcut sürümün açılmasını engellemez. Program dosyaları değiştirilirken aşağıdaki kullanıcı çalışma alanı korunur.

Kullanıcının kendi akışını düzenlemesi o bilgisayarda kaydedilir. Kodla yeni bir adım türü eklendiğinde sürüm artırılır, iki platformun paketleri test edilir ve yeni yayın hazırlanır; ancak bundan sonra diğer kurulumlar değişikliği alır. Statik yayın dizini, anahtar yedeği ve bildirimin en son yayımlanması [güncelleme mimarisi rehberinde](guncelleme-mimarisi.md) açıklanır.

## Kullanıcı deneyimi

Windows kurulum dosyası uygulamayı kullanıcının `AppData/Local/Programs/RpaOrkestrAI` klasörüne yerleştirir; masaüstü ve Başlat menüsü kısayollarını oluşturur. Normal kullanımda yönetici yetkisi istemez. Kısayol doğrudan konsolsuz `.exe` dosyasını çalıştırır. WebView2 Runtime yoksa kurulum, bileşenin kurulması için açıklama gösterir; Python kurdurmaz.

macOS'ta `.app` dosyasını Uygulamalar klasörüne taşıyıp açın. Paket derlendiği işlemci mimarisi içindir; Apple Silicon ve Intel sürümleri ayrı hedeflerde derlenmelidir. Ekran Kaydı ve Erişilebilirlik izinleri paketlenmiş uygulamaya verilmelidir.

Masaüstü uygulaması varsayılan port başka bir çalışma alanı veya uygulama tarafından kullanılıyorsa otomatik olarak boş bir yerel port seçer. Seçilen port işletim sistemi soketiyle ayrılır; ikinci açılış, aynı çalışma alanının canlı kimliğini doğrulayarak bu oturumu bulur. Diğer uygulama kapatılmaz ve başka çalışma alanına bağlanılmaz. Komut satırında açıkça seçilmiş portlar için mevcut hata davranışı korunur.

Uygulama yerel servisini kendi sürecinde başlatır; pencere kapanınca kendisinin başlattığı servisi kapatır. Önceden açık aynı çalışma alanının servisine bağlanmışsa o servisi kapatmaz. Açılış hataları işletim sisteminin ileti kutusunda gösterilir, ayrıntılar dosyaya yazılır.

| İçerik | Windows | macOS |
| --- | --- | --- |
| Kullanıcı çalışma alanı | `%LOCALAPPDATA%/RpaOrkestrAI/workspace` | `~/Library/Application Support/RpaOrkestrAI/workspace` |
| Akışlar ve ayarlar | Çalışma alanındaki `data/` | Çalışma alanındaki `data/` |
| Açılış günlüğü | `logs/studio.log` | `logs/studio.log` |
| Görsel şablonlar | `assets/templates/` | `assets/templates/` |

Günlükler 2 MB sınırında döner; üç yedek tutulur. Kurulumun güncellenmesi veya kaldırılması bu ayrı çalışma alanını silmez. Kaynak kod sürümünden geçerken akışları Studio üzerinden JSON dışa/içe aktarın, bağlantıları yeniden yapılandırın. Önceki `data/` klasörü otomatik taşınmaz. `RPA_DATA_DIR` tanımlıysa açıkça seçilmiş bu dizin kullanılır.

## GitHub üzerinden paket üretme

Bu dosyalar depoya gönderildikten sonra:

1. GitHub deposunda **Actions → Build desktop apps → Run workflow** seçin.
2. Windows ve macOS işleri, Python 3.12 ile bağımlılık tutarlılığını ve testleri kontrol edip kendi platformlarının uygulamasını oluşturur. Ayrı Python kontrol iş akışı her push'ta 3.12'yi, elle başlatıldığında 3.11–3.14 aralığını tam native/automation bağımlılıkları ve yerel pencere motoru yüklemesiyle sınar.
3. Derlenmiş uygulama geçici çalışma alanında `--self-test` ile açılır. Yerel API, arayüz dosyaları ve temel bağımlılıkların pakette bulunması kontrol edilir.
4. Windows işi Inno Setup ile kurulum `.exe` dosyasını üretir; macOS işi `.app` dosyasını Applications kısayoluyla birlikte doğrulanmış bir DMG'ye koyar.
5. Başarılı çalışmanın **Artifacts** bölümünden `RpaOrkestrAI-Windows-x64` veya `RpaOrkestrAI-macOS` indirilir. Paketler bir gün sonra silinir.

**Code → Download ZIP kaynak koddur; kurulum dosyası değildir.** Derleme iş akışı elle tetiklenir; tek başına GitHub Release veya güncelleme sunucusu yayını yapmaz. Yayın için doğrulanmış dosyalardan `scripts/prepare_update_release.py` ile imzalı bildirim ve indirme sayfası hazırlanır. Paket derlemesi ve gerçek hedef makinedeki açılış doğrulaması tamamlanmadan dağıtımın doğrulandığı varsayılmamalıdır; paket kontrolü ERP ekranına tıklamaz.

## Geliştirici bilgisayarında derleme

Hedef işletim sisteminde Python 3.12 sanal ortamıyla:

```text
python -m pip install ".[native,automation,build]"
python scripts/build_desktop.py
```

Windows çıktısı `dist/RpaOrkestrAI/RpaOrkestrAI.exe` olur; `dist/RpaOrkestrAI` klasörünün tamamı gerekir. Inno Setup 6 kuruluysa kurulum paketini üretin:

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" packaging\windows-installer.iss
```

Mac çıktısı `dist/RpaOrkestrAI.app` olur. Kurulum imajını oluşturmak için:

```bash
python scripts/build_macos_dmg.py dist/RpaOrkestrAI.app dist/RpaOrkestrAI-macOS-arm64.dmg
```

Dosya adındaki mimari, uygulamanın derlendiği mimariyle eşleşmelidir. Proje iCloud ile eşitlenen Masaüstü/Belgeler altındaysa Finder metaverisi imzalamayı bozabilir; `--dist-dir /tmp/rpa-desktop-dist` ile paketi eşitlenmeyen bir klasöre üretin. SQL Server adaptörünün derlenmesi için `unixODBC` gerekir; CI bunu kurar. Yalnız pencere/Sheets işlerini denemek için `python scripts/build_desktop.py --without-odbc` kullanılabilir; bu test paketi SQL Server bağlantısı içermez.

Statik HTML/CSS/JS, pywebview kaynakları, sertifika deposu ve dinamik yüklenen modüller paketlenir. `.env`, servis hesabı anahtarı, yerel akışlar ve `data/` hiçbir zaman build girdisi değildir. Tesseract, veritabanı sürücüleri, Chromium ve WebView2 gibi harici sistem bileşenleri bu Python paketinden ayrıdır. İlk havuzdaki pencere ve Sheets işlemleri Chromium/Tesseract gerektirmez.

Bu test dağıtımı için Windows yayıncı sertifikası ve Apple noter onayı kullanılmaz; macOS paketine yerel ad-hoc imza uygulanır. Sistem veya kurum politikaları ilk kurulumda ek onay isteyebilir. Güncelleme bildirimi ve dosya özetlerini koruyan Ed25519 imzası, işletim sistemi yayıncı sertifikalarından ayrı bir mekanizmadır.

## Kaynak kodla çalışan Windows kullanıcısı

`setup-windows.bat`, varsa desteklenen `.venv` ortamını korur; yoksa sırasıyla standart 64 bit Python 3.14, 3.13, 3.12 ve 3.11'i arar. Bağımlılıkları kurduktan sonra masaüstüne **RpaOrkestrAI Studio** kısayolu koyar. Bu kısayol `.venv/Scripts/pythonw.exe` ile `launch_gui.pyw` dosyasını açar: terminal görünmez, kaynak klasördeki mevcut `data/` ve `.env` kullanılır. Proje klasörü taşınırsa ortamı ve kısayolu yeni yerde yeniden oluşturun.

Bu geliştirme kısayolu bilgisayarda kurulmuş Python ortamına ihtiyaç duyar ve kaynak kodu otomatik güncellemez. `start.bat`, `start-browser.bat`, macOS `start.command` ve `launch.py` hata ayıklama için kullanılmaya devam eder. Terminalden bağımsız normal kullanım için kurulu EXE/APP açılmalıdır.

## Teknik dayanaklar

- [PyInstaller konsolsuz `.exe` ve `.app` seçenekleri](https://pyinstaller.org/en/stable/usage.html#windows-and-macos-specific-options)
- [Konsolsuz uygulamalarda stdout/stderr davranışı](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#sys-stdin-sys-stdout-and-sys-stderr-in-noconsole-windowed-applications-windows-only)
- [pywebview paketleme](https://pywebview.flowrl.com/guide/freezing.html)
- [Microsoft WebView2 dağıtımı](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
- [Inno Setup kullanıcı yetkisiyle kurulum](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
