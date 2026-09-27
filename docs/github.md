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

`.github/workflows/tests.yml`, pull request ve push olaylarında macOS/Windows üzerinde Python 3.11 ve 3.12 için çekirdek testleri ve kod kontrollerini çalıştırır. İşletim sistemi ekran izinleri ve gerçek ERP/veritabanı/Sheets erişimleri bu otomatik testlerden ayrı doğrulanır.

`.env`, servis hesabı anahtarları, veritabanı bağlantı klasörleri, yerel `data/` ve çalışma raporları `.gitignore` kapsamındadır. `.gitignore` daha önce Git'e eklenmiş bir dosyayı geçmişten çıkarmaz. Akış JSON'larını paylaşırken içine yazılmış iş verileri ve sabit metinler de dışa aktarılacağından dosyanın içeriğini inceleyin.
