# Terminal gerektirmeyen masaüstü uygulaması

Son kullanıcı için Windows dağıtımı `RpaOrkestrAI-Setup-<sürüm>-Windows-x64.exe`, macOS dağıtımı `RpaOrkestrAI.app` biçimindedir. Python ve uygulamanın Python paketleri derlemeye dahil edilir; kullanıcı kaynak kod, sanal ortam veya terminal ile uğraşmaz.

## Kullanıcı deneyimi

Windows kurulum dosyası uygulamayı kullanıcının `AppData/Local/Programs/RpaOrkestrAI` klasörüne yerleştirir; masaüstü ve Başlat menüsü kısayollarını oluşturur. Normal kullanımda yönetici yetkisi istemez. Kısayol doğrudan konsolsuz `.exe` dosyasını çalıştırır. WebView2 Runtime yoksa kurulum, bileşenin kurulması için açıklama gösterir; Python kurdurmaz.

macOS'ta `.app` dosyasını Uygulamalar klasörüne taşıyıp açın. Paket derlendiği işlemci mimarisi içindir; Apple Silicon ve Intel sürümleri ayrı hedeflerde derlenmelidir. Ekran Kaydı ve Erişilebilirlik izinleri paketlenmiş uygulamaya verilmelidir.

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
2. Windows ve macOS işleri, testleri çalıştırıp kendi platformlarının uygulamasını oluşturur.
3. Derlenmiş uygulama geçici çalışma alanında `--self-test` ile açılır. Yerel API, arayüz dosyaları ve temel bağımlılıkların pakette bulunması kontrol edilir.
4. Windows işi Inno Setup ile kurulum `.exe` dosyasını üretir; macOS işi `.app` dosyasını ZIP'e koyar.
5. Başarılı çalışmanın **Artifacts** bölümünden `RpaOrkestrAI-Windows-x64` veya `RpaOrkestrAI-macOS` indirilir.

**Code → Download ZIP kaynak koddur; kurulum dosyası değildir.** İş akışı elle tetiklenir; GitHub Release yayımlamaz. Paket derlemesi ve gerçek hedef makinedeki açılış doğrulaması tamamlanmadan dağıtımın doğrulandığı varsayılmamalıdır. Windows kurulum betiği ve GUI davranışı gerçek Windows oturumunda ayrıca denenmelidir; paket kontrolü masaüstüne tıklamaz.

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

Mac çıktısı `dist/RpaOrkestrAI.app` olur. Proje iCloud ile eşitlenen Masaüstü/Belgeler altındaysa Finder metaverisi imzalamayı bozabilir; `--dist-dir /tmp/rpa-desktop-dist` ile paketi eşitlenmeyen bir klasöre üretin. SQL Server adaptörünün derlenmesi için `unixODBC` gerekir; CI bunu kurar. Yalnız pencere/Sheets işlerini denemek için `python scripts/build_desktop.py --without-odbc` kullanılabilir; bu test paketi SQL Server bağlantısı içermez.

Statik HTML/CSS/JS, pywebview kaynakları, sertifika deposu ve dinamik yüklenen modüller paketlenir. `.env`, servis hesabı anahtarı, yerel akışlar ve `data/` hiçbir zaman build girdisi değildir. Tesseract, veritabanı sürücüleri, Chromium ve WebView2 gibi harici sistem bileşenleri bu Python paketinden ayrıdır. İlk havuzdaki pencere ve Sheets işlemleri Chromium/Tesseract gerektirmez.

Windows paketleri bu aşamada kod imzalı değildir; macOS paketine yerel ad-hoc imza uygulanır, Apple notarization yapılmaz. Kurumsal genel dağıtım için imza sertifikası, hedef bilgisayar testi ve kurumun dağıtım süreci ayrıca hazırlanmalıdır. Güvenlik denetimlerini devre dışı bırakmak kurulum adımı değildir.

## Kaynak kodla çalışan Windows kullanıcısı

`setup-windows.bat`, bağımlılıkları kurduktan sonra masaüstüne **RpaOrkestrAI Studio** kısayolu koyar. Bu kısayol `.venv/Scripts/pythonw.exe` ile `launch_gui.pyw` dosyasını açar: terminal görünmez, kaynak klasördeki mevcut `data/` ve `.env` kullanılır. Proje klasörü taşınırsa ortamı ve kısayolu yeni yerde yeniden oluşturun.

Bu geliştirme kısayolu `.exe` kurulum paketinden farklı olarak bilgisayarda kurulmuş Python ortamına ihtiyaç duyar. `start.bat`, `start-browser.bat` ve `launch.py` hata ayıklama için kullanılmaya devam eder.

## Teknik dayanaklar

- [PyInstaller konsolsuz `.exe` ve `.app` seçenekleri](https://pyinstaller.org/en/stable/usage.html#windows-and-macos-specific-options)
- [Konsolsuz uygulamalarda stdout/stderr davranışı](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#sys-stdin-sys-stdout-and-sys-stderr-in-noconsole-windowed-applications-windows-only)
- [pywebview paketleme](https://pywebview.flowrl.com/guide/freezing.html)
- [Microsoft WebView2 dağıtımı](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
- [Inno Setup kullanıcı yetkisiyle kurulum](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
