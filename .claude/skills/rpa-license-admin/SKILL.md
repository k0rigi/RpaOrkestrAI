---
name: rpa-license-admin
description: RpaOrkestrAI (MOD_RPA) lisansını bir firmaya veya kullanıcıya vermek, süresini uzatmak, kaldırmak ya da "süreniz dolmuştur / lisans tanımlı değil / giriş yapılamıyor" sorunlarını incelemek için kullan. orkestrai.net firma-modül ve kullanıcı-modül kuralına göre çalışır.
---

# RpaOrkestrAI lisans yönetimi

Kural: Kullanıcı ancak **firmasında** (`SYS_FirmaModulleri`) ve **kendi hesabında** (`SYS_KullaniciModulleri`) `MOD_RPA` açıksa ve firma satırındaki `BitisTarihi` bugünden önce değilse (boş = süresiz) uygulamayı açabilir. `Admin` rolü tüm modüllere erişir. Uygulama (0.8.0+) her açılışta ve 10 dakikada bir orkestrai.net'ten onay alır; bir hesap aynı anda tek bilgisayarda çalışır. Ayrıntılar: `docs/lisans.md`.

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

Değişiklik açık uygulamaya en geç 10 dakika içinde (arka plan doğrulaması) veya kullanıcı **Lisansı şimdi doğrula** / **Yeniden kontrol et** dediğinde yansır; yetkisi kalkan kullanıcıda Studio kilitlenir ve çalışan akış durur. Kapalı uygulama bir sonraki açılışta onay alamaz. İnterneti kesilmiş açık bir uygulama en fazla 60 dakika daha çalışır.

Kullanımı hemen kesmek için kullanıcının MOD_RPA satırını sil, hesabı `Pasif` yap ya da şifresini değiştir (son ikisi oturumu da kapatır).

## Oturumlar (tek bilgisayar kuralı)

Her giriş `SYS_RpaOturumlari` tablosuna bir satır açar ve hesabın başka bilgisayardaki oturumunu kapatır. Tabloyu API yazar; elle satır ekleme. İnceleme ve elle kapatma:

```sql
-- Bir kullanıcının oturumları (en yeni üstte)
SELECT OturumID, Cihaz, Surum, IP, Olusturma, SonGorulme, Durum, KapanmaNedeni
FROM SYS_RpaOturumlari WHERE KullaniciID = <KullaniciID> ORDER BY SonGorulme DESC LIMIT 20;

-- Şu anda açık tüm oturumlar
SELECT o.KullaniciID, k.Eposta, o.Cihaz, o.Surum, o.IP, o.SonGorulme
FROM SYS_RpaOturumlari o JOIN SYS_Kullanicilar k ON k.KullaniciID = o.KullaniciID
WHERE o.Durum = 'Aktif' ORDER BY o.SonGorulme DESC;

-- Bir oturumu elle kapat (kullanıcı en geç 10 dakika içinde giriş ekranına döner; yetkisi duruyorsa yeniden girebilir)
UPDATE SYS_RpaOturumlari SET Durum = 'Kapandi', KapanmaNedeni = 'YONETICI' WHERE OturumID = '<OturumID>';
```

`KapanmaNedeni`: `BASKA_CIHAZ` (hesap başka bilgisayarda açıldı), `YENI_GIRIS` (aynı bilgisayarda yeniden giriş), `CIKIS` (kullanıcı oturumu kapattı), `KOPYA` (aynı oturum iki yerde kullanıldı). Aynı kullanıcıda sık `BASKA_CIHAZ` / `KOPYA` görülmesi hesabın paylaşıldığını gösterir; kullanıcıya her kişi için ayrı hesap gerektiğini bildir.

Eş zamanlı bilgisayar sayısı (`rpa_lisans.RPA_ES_ZAMANLI_OTURUM = 1`), doğrulama aralığı (`RPA_YENILEME_ARALIGI`), bağlantısız çalışma süresi (`RPA_CALISMA_TOLERANSI`) ve kabul edilen en düşük uygulama sürümü (`RPA_ASGARI_SURUM`) orkestrai deposunda `api/` içindedir. Değişiklik commit + push ile gider; değiştirmeden önce kullanıcıya sor.

## Sorun inceleme

| Belirti | Olası neden |
| --- | --- |
| Kullanıcı adı veya şifre hatalı | Hesap `Aktif` değil, yanlış şifre. 15 dakikada 10 hatalı denemeden sonra geçici kilit uygulanır. |
| Birden fazla hesapla eşleşiyor | Aynı kullanıcı adı ve şifre farklı firmalarda var; e-postanın tamamı yazılmalı. |
| Lisans tanımlı değil | Firmada veya kullanıcıda MOD_RPA satırı yok. |
| Kullanım süreniz dolmuştur | Firma `BitisTarihi` geçmiş. |
| Lisans doğrulanamadı | Bilgisayar `https://orkestrai.net` adresine ulaşamıyor (internet, proxy/güvenlik duvarı) ya da sunucu yanıt vermiyor. Açılışta onay şarttır; açık uygulama bağlantısız en fazla 60 dakika çalışır. |
| Bu hesap başka bir bilgisayarda açıldı | Aynı hesapla başka bilgisayarda giriş yapıldı (`BASKA_CIHAZ`). Hesap paylaşılıyorsa ayrı hesap gerekir. |
| Oturum birden fazla yerde kullanıldı | Aynı oturum kaydı iki yerde çalıştırıldı (`KOPYA`); yeniden giriş yeterlidir. |
| Bu sürüm artık desteklenmiyor | Uygulama `RPA_ASGARI_SURUM` değerinden eski. Güncelleme arka planda iner ve yeniden açılışta kurulur; olmazsa orkestrai.net/rpa adresinden kurulur. |
| Yeniden giriş istendi | Şifre değişti, hesap pasifleşti, oturum 30 günden uzun kullanılmadı veya çalışma alanı başka bilgisayardan kopyalandı. |

Canlı uçları dışarıdan kontrol etmek için (şifre gerektirmez):

```bash
curl -s https://orkestrai.net/api/rpa/lisans/anahtar
# Uygulamadaki licensing.LICENSE_PUBLIC_KEY ile aynı olmalı.
```

Anahtar farklıysa sunucudaki `/home/orkestrai.net/.orkestrai_rpa_lisans_ed25519` dosyası değişmiş demektir. Kurulu uygulamalar yeni anahtarla lisans doğrulayamaz. Bu durumda `LICENSE_PUBLIC_KEY` güncellenip yeni sürüm yayımlanır (`rpa-release`). Güncelleme mekanizması lisanstan bağımsız çalıştığı için kullanıcılar yeni sürümü alabilir.

Uygulama tarafında çalışma alanındaki `data/license.json` yalnız kurulum kimliğini, oturum belirtecini ve kullanıcı adını içerir; lisansın kendisi ve şifre yoktur. Dosya uygulamayı açmaz: onay her açılışta sunucudan alınır ve yalnız bellekte tutulur. Dosya silinir veya bozulursa yeniden giriş istenir.

Canlı sunucunun hangi protokolü konuştuğu `anahtar` ucundaki `protokol` alanından görülür (0.8.0 için `2`).
