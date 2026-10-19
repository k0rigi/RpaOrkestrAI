# Web otomasyonu (0.9.20+, betikleme 0.9.21+)

RpaOrkestrAI, web sitelerini bilgisayardaki **Microsoft Edge** veya **Google Chrome** ile bir insan gibi kullanır: sayfa açar, alan doldurur, düğmeye basar, tablo okur, dosya indirir/yükler ve gerektiğinde sayfada kendi JavaScript kodunuzu çalıştırır. Ayrıca tarayıcı indirilmez; Windows'ta Edge her zaman vardır, Mac'te Chrome veya Edge kullanılır.

## İlk akış: portaldan sipariş listesini almak

1. **Web sayfası aç** — Adres: `https://portal.firma.com/giris`. Tarayıcı: Otomatik.
2. **Web alanını doldur** — **Tarayıcıda seç** ile kullanıcı adı alanına tıklayın (hedef `Alan etiketi: Kullanıcı adı` olur). Değer: `${row.kullanici}`.
3. **Web alanını doldur** — Şifre alanı; değer `${sifre.portal}` (Ayarlar → Kayıtlı şifreler). Şifre günlükte `[gizlendi]` görünür.
4. **Web öğesine tıkla** — `Düğme veya bağlantı adı: Giriş yap`.
5. **Web'de bekle** — Adres `/siparisler` içersin (en fazla 30 sn).
6. **Web tablosunu oku** — Hedef: tablodaki bir sütun başlığı, ör. `Görünen metin: Sipariş No` (Tam eşleşme). Sonuç `${web_rows}`.
7. **Her satır için** `${web_rows}` → içinde `${row.Tutar}`, `${row.Müşteri}` …
8. **Web'den dosya indir** — `Excel'e aktar` düğmesi, klasör `~/Desktop/Raporlar`. Sonuç `${web_file}`; ardından **Excel / CSV oku**.

Tarayıcı çalışma bitince kapanır. Girişler RpaOrkestrAI'nin **ayrı** tarayıcı profilinde saklanır (kendi Edge/Chrome profiliniz kullanılmaz); site izin verdiği sürece bir sonraki çalışmada yeniden giriş gerekmez.

## Tarayıcıda seç: hedefi tıklayarak belirleme

Hedef alanı olan her web adımında **Tarayıcıda seç** düğmesi vardır.

1. Düğmeye basın. Adres, akışta bu adımdan önceki **Web sayfası aç** adımından alınır; değiştirebilirsiniz.
2. Tarayıcı açılır. Sağ alttaki panel **Seçim açık** derken üzerine geldiğiniz öğe mavi çerçeveyle gösterilir.
3. Önce gezinmeniz veya giriş yapmanız gerekiyorsa **Seçimi kapat**'a basın, sayfada normal çalışın, sonra **Seçimi aç**.
4. Hedef öğeye tıklayın. Bu tıklama sayfaya ulaşmaz (form gönderilmez); tarayıcı kapanır ve adımın hedefi dolar.

Hedef, bir kişinin söyleyeceği adla seçilir: önce alan etiketi, yer tutucu yazı, düğme/bağlantı adı veya görünen metin; bunlar sayfada tek değilse kimlik (`#id`), `name` veya en sonda sayfadaki yol (CSS). Her aday, çalışmanın arayacağı biçimde denetlenir ve **yalnız tıkladığınız öğeyi** buluyorsa kaydedilir. Çerçeve (iframe) içindeki öğeler de seçilir; çerçeve alanı kendiliğinden dolar.

## Adımlar

| Adım | Ne işe yarar |
| --- | --- |
| Web sayfası aç | Adresi açar; sonraki adımlar bu sekmede çalışır. |
| Web öğesine tıkla | Düğme, bağlantı veya metne tıklar. **Tıklama türü** (0.9.39+): **Tek tık** (varsayılan), **Çift tık** (satır veya dosya açan listeler), **Sağ tık** (sitenin kendi sağ tık menüsü), **Orta tık** veya **Yalnız üzerine gel** (tıklamaz; fareyle açılan menüleri gösterir, sonraki adım menüdeki öğeye tıklar). Tıklamayla başlatılan yeni sekmenin ilk yanıtı beklenir; sonraki adımlar o sekmeye geçer. Yeni sekme süresinde açılmazsa işlem durur, tıklama tekrarlanmaz. Tek tık dışında bir tür seçilen akış 0.9.39 öncesi sürümlerde açılmaz. |
| Web alanını doldur | Yazı alanının değerini değiştirir. |
| Web'den metin oku | Öğenin metnini veya alanın değerini okur. |
| Web listesinden seç | Açılır listede (select) seçenek seçer. |
| Web'de bekle | Öğe görünene/kaybolana veya adres bir metni içerene kadar bekler; sabit beklemeden hızlı ve güvenlidir. |
| Web'de tuşa bas | Enter, Tab, ok tuşları…; hedef verilirse o öğeye. |
| Web'de geri / ileri / yenile | Tarayıcı düğmeleri. |
| Web sekmesine geç / kapat | Son, ilk, başlığında veya adresinde metin geçen sekme; etkin sekmeyi kapatma. |
| Web tablosunu oku | HTML tablosunu satır listesine çevirir; başlıklar alan adı olur. |
| Web'den dosya indir | İndirmeyi başlatan öğeye tıklar, dosyayı klasöre kaydeder; aynı ad varsa sonuna (2) eklenir. |
| Web'e dosya yükle | Dosya seçme alanına dosyaları verir; Gözat penceresi açılmaz. |
| Web sayfasının görüntüsünü al | Sayfayı çalışma çıktılarına PNG olarak ekler. |
| Web'de JavaScript çalıştır | Sayfada kendi kodunuzu çalıştırır, döndürdüğü değeri değişkene kaydeder. |

Ortak hedef ayarları: **Hedefi bulma yöntemi** (görünen metin, alan etiketi, silik yazı, düğme/bağlantı adı, CSS), **Tam eşleşme** (kapalıyken içinde geçmesi yeterli), **En fazla bekle** ve **Çerçeve (iframe)**. Hedef birden fazla öğeyle eşleşirse adım hiçbir şey yapmadan durur; tıklama hiçbir zaman tekrarlanmaz.

## JavaScript ile betikleme

**Web'de JavaScript çalıştır** adımındaki kod, `async (girdi) => { … }` fonksiyonunun gövdesidir: `await` kullanılabilir, sonucu `return` ile verirsiniz. Akış değişkenleri koda doğrudan yazılmaz; **Girdi** alanından verilir ve kodda `girdi` adıyla kullanılır. Koddaki `${...}` JavaScript'e aittir, akış değişkeni olarak doldurulmaz.

Sayfadaki tüm bağlantıları listelemek:

```js
return [...document.querySelectorAll("a")].map(a => ({ metin: a.innerText.trim(), adres: a.href }));
```

Girdi `{"no": "${row.no}"}` ile bir satırı bulup tutarını almak:

```js
const satir = [...document.querySelectorAll("table tr")].find(tr => tr.cells[0]?.innerText.trim() === girdi.no);
return satir ? satir.cells[3].innerText.trim() : null;
```

Sayfanın sonuna kadar kaydırıp yeni kayıtların yüklenmesini beklemek:

```js
for (let i = 0; i < 10; i++) {
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 500));
}
return document.querySelectorAll(".kayit").length;
```

Sitenin kendi API'sinden JSON almak (oturum çerezleriyle):

```js
const yanit = await fetch("/api/siparisler?durum=bekliyor");
return await yanit.json();
```

Dönen değer metin, sayı, liste veya nesne olabilir (en fazla 5 MB); sonraki adımlarda `${web_result}`, `${web_result.alan}` veya **Her satır için** ile kullanılır. Kod hata verirse adım durur ve hata mesajı günlükte görünür; **Hata olursa** bloğuyla yakalanabilir.

Kod, sitede oturum açmış kullanıcının yetkisiyle çalışır. Güvenmediğiniz kaynaktan kod yapıştırmayın.

## İpuçları

- Sabit **Bekle** yerine **Web'de bekle** kullanın: "Yükleniyor" yazısının kaybolmasını veya sonucun görünmesini bekleyin.
- Hata anını görmek için **Hata olursa** dalına **Web sayfasının görüntüsünü al** ekleyin.
- Türkçe büyük **İ** içeren metinlerde hedefi sayfadaki gibi yazın veya Tarayıcıda seç kullanın.
- Akış çalışırken başka bir **Tarayıcıda seç** açılamaz (aynı tarayıcı profilini kullanırlar).
- Bu adımları kullanan akışlar, adımı ilk getiren sürümden (0.9.20 veya 0.9.21) eski kurulumlarda açılmaz.
