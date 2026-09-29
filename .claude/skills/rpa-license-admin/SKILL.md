---
name: rpa-license-admin
description: RpaOrkestrAI (MOD_RPA) lisansını bir firmaya veya kullanıcıya vermek, süresini uzatmak, kaldırmak ya da "süreniz dolmuştur / lisans tanımlı değil / giriş yapılamıyor" sorunlarını incelemek için kullan. orkestrai.net firma-modül ve kullanıcı-modül kuralına göre çalışır.
---

# RpaOrkestrAI lisans yönetimi

Kural: Kullanıcı ancak **firmasında** (`SYS_FirmaModulleri`) ve **kendi hesabında** (`SYS_KullaniciModulleri`) `MOD_RPA` açıksa ve firma satırındaki `BitisTarihi` bugünden önce değilse (boş = süresiz) uygulamayı açabilir. `Admin` rolü tüm modüllere erişir. Ayrıntılar: `docs/lisans.md`.

## Önce sor

Lisans vermek, uzatmak veya kaldırmak üretim veritabanını değiştirir. Firma, kullanıcı ve bitiş tarihini kullanıcıdan açıkça teyit etmeden işlem yapma.

## Veritabanı işlemleri

Üretim veritabanı yalnız sunucunun kendi içinden erişilebilir; bağlantı bilgileri orkestrai deposundaki `api/db.py` içindedir ve bu depoya yazılmaz. orkestrai deposunun kuralına göre SSH yalnız gerçekten gerektiğinde ve kullanıcı onayıyla kullanılır. Kod değişikliği için SSH kullanılmaz. Aşağıdaki SQL'ler kullanıcıya verilebilir veya onayla çalıştırılabilir.

```sql
-- Modül kimliği
SELECT ModulID FROM SYS_Moduller WHERE ModulKodu = 'MOD_RPA';

-- Kullanıcıyı bul (kullanıcı adı = e-postanın @ öncesi)
SELECT KullaniciID, FirmaID, AdSoyad, Eposta, Rol, Durum FROM SYS_Kullanicilar
WHERE LOWER(SUBSTRING_INDEX(Eposta, '@', 1)) = LOWER('kullanici_adi') OR LOWER(Eposta) = LOWER('kullanici_adi');

-- Firmaya lisans ver veya süresini değiştir (BitisTarihi dahil son gündür)
INSERT INTO SYS_FirmaModulleri (FirmaID, ModulID, BitisTarihi) VALUES (<FirmaID>, <ModulID>, '2027-09-27');
UPDATE SYS_FirmaModulleri SET BitisTarihi = '2028-09-27' WHERE FirmaID = <FirmaID> AND ModulID = <ModulID>;

-- Kullanıcıya modül ata / kaldır
INSERT INTO SYS_KullaniciModulleri (KullaniciID, ModulID) VALUES (<KullaniciID>, <ModulID>);
DELETE FROM SYS_KullaniciModulleri WHERE KullaniciID = <KullaniciID> AND ModulID = <ModulID>;
```

Tabloda zorunlu başka kolonlar olabilir; eklemeden önce `SHOW COLUMNS FROM <tablo>` ile kontrol et.

Değişiklik uygulamaya en geç 1 saat içinde (arka plan yenilemesi) veya kullanıcı **Lisansı şimdi doğrula** / **Yeniden kontrol et** dediğinde yansır. İnternetsiz bilgisayarda son doğrulamadan itibaren en fazla 7 gün gecikebilir.

## Sorun inceleme

| Belirti | Olası neden |
| --- | --- |
| Kullanıcı adı veya şifre hatalı | Hesap `Aktif` değil, yanlış şifre. 15 dakikada 10 hatalı denemeden sonra geçici kilit uygulanır. |
| Birden fazla hesapla eşleşiyor | Aynı kullanıcı adı ve şifre farklı firmalarda var; e-postanın tamamı yazılmalı. |
| Lisans tanımlı değil | Firmada veya kullanıcıda MOD_RPA satırı yok. |
| Kullanım süreniz dolmuştur | Firma `BitisTarihi` geçmiş. |
| 7 gündür doğrulanamadı | Bilgisayar orkestrai.net'e ulaşamıyor (proxy/güvenlik duvarı), veya saat geri alınmış. |
| Yeniden giriş istendi | Şifre değişti, oturum 30 günden uzun kullanılmadı veya çalışma alanı başka bilgisayardan kopyalandı. |

Canlı uçları dışarıdan kontrol etmek için (şifre gerektirmez):

```bash
curl -s https://orkestrai.net/api/rpa/lisans/anahtar
# Uygulamadaki licensing.LICENSE_PUBLIC_KEY ile aynı olmalı.
```

Anahtar farklıysa sunucudaki `/home/orkestrai.net/.orkestrai_rpa_lisans_ed25519` dosyası değişmiş demektir. Kurulu uygulamalar yeni anahtarla lisans doğrulayamaz. Bu durumda `LICENSE_PUBLIC_KEY` güncellenip yeni sürüm yayımlanır (`rpa-release`). Güncelleme mekanizması lisanstan bağımsız çalıştığı için kullanıcılar yeni sürümü alabilir.

Uygulama tarafındaki lisans durumu kullanıcının çalışma alanında `data/license.json` dosyasındadır. Bu dosya imzalı lisansı ve yenileme oturumunu içerir, şifre içermez. Elle düzenlenirse imza tutmaz ve yeniden giriş istenir.
