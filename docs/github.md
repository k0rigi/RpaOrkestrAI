# GitHub'a bağlama ve çalışma düzeni

Yerel depo hazırlanıp `Initial commit` oluşturulduktan sonra GitHub hesabınızda boş bir repository oluşturun. Yerel ilk commit ile farklı geçmişler oluşturmamak için GitHub tarafında README, `.gitignore` veya lisans dosyasını otomatik başlatmayın.

Proje klasöründe durumu kontrol edin:

```bash
git status
git branch --show-current
git remote -v
```

Yerel dal `main` ve henüz `origin` yoksa:

```bash
git remote add origin https://github.com/KULLANICI/RpaOrkestrAI.git
git push -u origin main
```

SSH kullanıyorsanız remote adresi şu biçimdedir:

```bash
git remote add origin git@github.com:KULLANICI/RpaOrkestrAI.git
git push -u origin main
```

Yalnız bir adres seçin. `origin` zaten varsa yeni remote eklemek yerine önce mevcut adresin doğru depoyu gösterdiğini kontrol edin. Adres gerçekten değişecekse:

```bash
git remote set-url origin https://github.com/KULLANICI/RpaOrkestrAI.git
```

İlk commit sırasında kullanıcı bilgisi eksikse yalnız bu depo için tanımlayabilirsiniz:

```bash
git config user.name "Adınız Soyadınız"
git config user.email "GitHub hesabınızdaki doğrulanmış veya noreply e-posta"
```

Bu komutlar GitHub oturumunu açmaz; HTTPS veya SSH kimlik doğrulamasını kendi hesabınızla tamamlayın.

## Geliştirme

```bash
git switch -c feature/yeni-erp-akisi
python -m pytest
python -m ruff check .
git status
git diff
git add <degistirdiginiz-dosyalar>
git commit -m "Add ERP workflow support"
git push -u origin feature/yeni-erp-akisi
```

`.github/workflows/tests.yml`, pull request ve push olaylarında macOS/Windows üzerinde paketlenen Python 3.12 için; **Run workflow** ile elle başlatıldığında Python 3.11, 3.12, 3.13 ve 3.14 için tam `native`/`automation` bağımlılıklarını kurar. GitHub Actions dakikaları sınırlıdır (macOS dakikası 10, Windows dakikası 2 kat sayılır); tam matris yayın öncesinde bir kez çalıştırılır. `pip check`, yerel pencere motorunun gerçekten yüklenmesi, testler ve kod kontrolleri çalışır. İşletim sistemi ekran izinleri ve gerçek ERP/veritabanı/Sheets erişimleri bu otomatik testlerden ayrı doğrulanır.

`.env`, servis hesabı anahtarları, veritabanı bağlantı klasörleri, yerel `data/` ve çalışma raporları `.gitignore` kapsamındadır. `.gitignore` daha önce Git'e eklenmiş bir dosyayı geçmişten çıkarmaz. Akış JSON'larını paylaşırken içine yazılmış iş verileri ve sabit metinler de dışa aktarılacağından dosyanın içeriğini inceleyin.

## Masaüstü kurulum paketleri

`.github/workflows/desktop-build.yml`, **Actions → Build desktop apps → Run workflow** üzerinden elle çalıştırılır. Paketler kendi Python 3.12 yorumlayıcısını içerir. Windows `.exe` kurulum paketi ve macOS `.dmg` disk imajı **Artifacts** olarak üretilir ve bir gün sonra silinir; derleme işi tek başına Release veya güncelleme sunucusu yayını yapmaz. [Dağıtım, veri klasörleri ve paket kontrolleri](masaustu-dagitim.md).

Kullanıcı indirmeleri için [orkestrai.net/rpa](https://orkestrai.net/rpa/) adresi ve GitHub alternatifi olarak [Releases](https://github.com/k0rigi/RpaOrkestrAI/releases) bölümü kullanılır. 0.2.0 test yayınının etiketi `v0.2.0-test.1` olarak ayrılmıştır. **Code → Download ZIP** bu paketleri içermez; kaynak kodu indirir.

## Yeni adım ve uygulama sürümü yayımlama

Kodla geliştirilen yeni adım türleri test edilip sürüm numarası artırıldıktan sonra iki işletim sistemi için derlenir. `scripts/prepare_update_release.py`, doğrulanmış EXE/DMG dosyalarından statik indirme sayfası ve Ed25519 imzalı `stable.manifest` hazırlar. Özel imza anahtarı `credentials/` içinde veya güvenli başka bir konumda kalır; Git'e ve sunucuya gönderilmez. Sunucuya sürümlü paketler önce, bildirim en son aktarılır. [Komut ve yayın protokolü](guncelleme-mimarisi.md).

Güncelleme istemcisi 0.2.0 ile başlar; 0.1.x kurulumları bu sürüme bir kez elle yükseltilir. Daha sonraki sürümler açılışta arka planda indirilir ve sonraki açılışta kurulur. Kullanıcının kendi akışını değiştirmesi yerel bir kayıttır; başka bilgisayarlara uygulama sürümü yayımlamaz.
