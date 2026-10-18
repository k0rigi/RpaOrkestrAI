# Ofis modeli: RPA ofis yerleşim sözleşmesi (sürüm 1)

Studio'nun 3D ofisinde kendi binanızı veya ofisinizi kullanabilirsiniz. Ancak her GLB dosyası ajan yerleşimi
için yeterli değildir. Bir masanın, sandalyenin veya koridorun nerede olduğu bir modelin şekillerinden güvenle
çıkarılamaz. Bu nedenle Studio, modelin içinde açıkça tanımlanmış **yerleşim noktalarını** okur. Bu sayfa o
kuralları (sözleşme sürümü **1**) anlatır. Sözleşmeye uymayan model içe aktarılmaz; Studio eksikleri
madde madde yazar.

Hazır bir örnek de vardır: **Ofis → Ofis modeli → Örnek ofisi kullan**. Örnek, `scripts/make_sample_office.py`
ile üretilir ve bu sayfadaki bütün kurallara uyar.

## 1. Model standardı

- **Dosya:** tek parça `.glb` (glTF 2.0 ikili), en fazla 100 MB. Dokular dosyanın içine gömülüdür.
  Dış `.bin` veya doku dosyası, Draco sıkıştırması ve zorunlu meshopt veya KTX2 sıkıştırması kabul edilmez.
- **Ölçü ve eksenler:** uzunluk birimi **metre**, yukarı ekseni **+Y**. Ofisin zemini `RPA_ORIGIN`'e göre
  **Y = 0**'dır. Modelin boyutu 1–500 m dışında kalırsa (ör. santimetre ile dışa aktarılmışsa) reddedilir.
- **Yerleşim noktaları:** görünmez, **benzersiz adlı boş düğümlerdir** (Blender'da Empty). Şekil (mesh),
  kamera veya iskelet içeremezler. Noktalar gösterilen sahnenin içinde, modelin herhangi bir yerinde
  (bir grubun altında da) olabilir. Studio bütün dönüşümleri uygulayıp noktaların ofis içindeki konumunu ve
  yönünü kendisi hesaplar.
- **Tahmin yoktur:** Studio dekoratif nesne adlarından, zeminden veya mobilyadan yerleşim ya da yürüme yolu
  çıkarmaz. Tanımlanmayan bölge için etiket veya oda üretmez.
- `RPA_` ile başlayan her düğüm adı aşağıdaki listeden olmalıdır. Yazım hatası (ör. `RPA_WROK_001`)
  sessizce yok sayılmaz, hata olarak bildirilir.

## 2. Yerleşim düğümleri

| Düğüm | Zorunlu | Anlamı |
| --- | --- | --- |
| `RPA_ORIGIN` | Evet | Ofisin referans noktası. Özelliği: `rpa_layout_version = 1`. Ölçeksiz olmalı, yerel +Y yukarıyı göstermeli (yalnız Y ekseninde dönebilir). |
| `RPA_SPAWN_01` | Evet | Yeni ajanların ilk göründüğü, engelsiz nokta (genellikle giriş). |
| `RPA_WORK_001`, `RPA_WORK_002`, … | En az 1 | Çalışma noktaları. Masanın merkezi değil, **ajanın duracağı (oturacağı) yerdir**. Her noktada bir kişi bulunur. |
| `RPA_WAIT_001`, `RPA_WAIT_002`, … | En az 1 | Boş çalışma noktası kalmadığında kullanılan bekleme noktaları. Her noktada bir kişi bulunur. |
| `RPA_NAV_001`, `RPA_NAV_002`, … | Evet | Yürünebilir yol ağının ara noktaları (bkz. bölüm 4). |
| `RPA_SEAT_001`, … | Hayır | Aynı numaralı çalışma noktasının oturma referansı (`RPA_SEAT_003` → `RPA_WORK_003`). |
| `RPA_SEAT_MANAGER` | Hayır | `RPA_MANAGER_01` noktasının oturma referansı. |
| `RPA_MANAGER_01` | Hayır | Yönetici ajanın yeri. Yoksa yönetici de bir çalışma noktası alır. |
| `RPA_MEET_001`, … | Hayır | Yöneticiye soru soran veya sonuç teslim eden ajanın yürüyeceği buluşma noktaları. |
| `RPA_RESEARCH_001`, … | Hayır | İnternette araştıran ajanın yürüyeceği noktalar. |
| `RPA_LABEL_<alan>` | Hayır | Alan etiketi (ör. `RPA_LABEL_Muhasebe`). Görünen metin `rpa_label` özelliğinden okunur; yoksa adın kendisi kullanılır (`_` → boşluk). |
| `RPA_CAMERA_TARGET` | Hayır | Kameranın başlangıçta baktığı nokta. |

Numaralar üç basamaklıdır (`001`–`999`); yalnız `RPA_SPAWN_01` ve `RPA_MANAGER_01` iki basamaklıdır.

## 3. Konum ve yön

- Her noktanın konumu **karakterin ayak tabanıdır**. Ayakta durulan noktalar (SPAWN, WORK, WAIT, MANAGER,
  MEET, RESEARCH) ve yol ağı noktaları zeminde olmalıdır: `RPA_ORIGIN`'e göre Y, 0 ± 5 cm.
- Noktanın **yerel +Z ekseni karakterin bakacağı yatay yöndür**. Eğik yön (yukarı veya aşağı bakan) hata verir.
  Studio'nun karakterleri kendi ön yüzü −Z olacak şekilde çizilmiştir; uygulama bu farkı kendisi düzeltir.
- **Blender'da:** glTF dışa aktarımında "+Y Up" açıkken Blender'daki boş düğümün **yerel −Y ekseni**
  glTF'de yerel +Z olur. Yani noktayı, karakterin yüzü Blender'ın ön görünüşündeki gibi (size doğru, −Y)
  bakacak şekilde döndürün.
- Ayakta durulan iki nokta arasında en az **0,6 m** olmalıdır; daha yakın noktalar karakterleri üst üste
  bindireceği için reddedilir.

## 4. Yol ağı (zorunlu)

Noktalar tek başına güvenli bir yürüme yolu tanımlamaz. Ajanlar yalnız modelin bildirdiği yol ağında yürür.

- Ağ, `RPA_NAV_###` noktaları ile ayakta durulan noktalardan oluşur.
- Bağlantılar düğümün `rpa_links` özelliğine yazılır: diğer düğümlerin adları, virgülle ayrılarak
  (ör. `RPA_NAV_002, RPA_WORK_001`). Bağlantı iki yönlüdür; bir tarafa yazmak yeterlidir.
- Her ayakta durulan nokta en az bir bağlantıya sahip olmalı ve bütün ağ `RPA_SPAWN_01`'den ulaşılabilir
  tek parça olmalıdır.
- Bir bağlantı en fazla 40 m olabilir; uzun koridorlara ara `RPA_NAV` noktası koyun. Bağlantıyı yalnız
  gerçekten yürünebilen (duvar, masa veya cam içinden geçmeyen) yerlere çizin. Studio bunu sizin
  çizdiğiniz yola güvenerek uygular; şekillerden kendisi çıkarmaz.
- Öneri: her `RPA_WORK` noktasını, arkasındaki koridor noktasına tek bağlantıyla bağlayın. Böylece başka
  biri o noktanın içinden geçmez.
- Bir alanın buluşma veya araştırma noktası yoksa ajan yerinde kalır ve durum balonu gösterilir.
  Yürünecek yol bulunamazsa da yürünmez.

## 5. Yerleştirme ve kapasite

- Her çalışma ve bekleme noktası **bir kişilik**tir. Ajanlar (ve ofisin insan çalışanları) noktalara
  kalıcı olarak eşlenir. Eşleme bu bilgisayarda ve ofise özel saklanır.
- Yeni gelen ilk boş çalışma noktasını alır. Çalışma noktaları doluysa boş bekleme noktasını alır.
  Bir çalışma noktası boşalınca bekleyen ilk kişi oraya geçer.
- Bekleme noktaları da doluysa kişi yalnız listede görünür ve ofiste "Ofis kapasitesi dolu" yazar.
  Karakterler üst üste bindirilmez, modelin dışına konmaz.
- Silinen ajanın noktası boşalır. Model değiştirildiğinde eski eşlemeler doğrulanır: hâlâ var olan
  noktalar korunur, geçersiz olanlar yeniden atanır.
- `RPA_MANAGER_01` varsa yönetici ajan oraya oturur; başka kimse o noktayı almaz.

## 6. Oturma

Bir çalışma noktasının oturma referansı varsa (`RPA_SEAT_###`), o noktadaki karakter gerçek bir oturma
pozuyla (kalça ve diz bükülerek) oturur. Oturma yalnız konumu değiştirerek taklit edilmez.

- Oturma referansının konumu oturak yüzeyidir (kalçanın değdiği yer): yüksekliği 0,30–0,80 m.
- Çalışma noktasına en fazla 1 m uzaklıkta olmalıdır.
- Yerel +Z yönü, oturan kişinin baktığı yöndür.
- Karakter yürümeye başlayınca ayağa kalkar, dönünce yeniden oturur.

## 7. Studio'nun verdiği hatalar

İçe aktarma, uymayan her kuralı adıyla yazar. Örnekler:

- `RPA_ORIGIN düğümü yok` / `Yerleşim sözleşmesinin sürümü yok`
- `Zorunlu RPA_SPAWN_01 … yok`, `En az bir RPA_WORK_### noktası zorunlu`
- `Tanınmayan yerleşim düğümü: RPA_WROK_003`, `… adı birden fazla düğümde kullanılmış`
- `… görünmez boş bir düğüm olmalı`, `… zeminde değil`, `… yönü yatay değil`
- `… karakterler çakışır`, `… yol ağına bağlı değil`, `Yol ağı kopuk …`
- `… oturak yüzeyi 0,30–0,80 m olmalı`, `Modelin büyüklüğü … uzunluk birimi metre olmalı`

0.9.36–0.9.37 ile içe aktarılmış ve sözleşmeye uymayan model kullanılmaz. Ofis modeli panelinde
nedenleri yazar ve hazır ofis gösterilir. Yeni model içe aktarabilir, örnek ofisi kullanabilir veya
eski modeli silebilirsiniz.

## 8. Blender ile hazırlama

1. Birimler: Scene Properties → Units → Metric, Unit Scale 1.0. Ofisin zemini Z = 0'da olsun.
2. Ofisin referans noktasına `RPA_ORIGIN` adlı bir Empty ekleyin. Object Properties → Custom Properties
   bölümünden tamsayı özellik ekleyin: ad `rpa_layout_version`, değer `1`.
3. Giriş için `RPA_SPAWN_01`, her çalışma yeri için `RPA_WORK_001…` Empty'leri ekleyin. Empty'leri ayak
   tabanı hizasına (Z = 0) koyun. Karakterin bakacağı yön, Empty'nin yerel −Y ekseni olacak şekilde
   döndürün.
4. Bekleme yerleri için `RPA_WAIT_###`, koridorlar için `RPA_NAV_###` ekleyin. Her noktaya metin özellik
   `rpa_links` yazın (ör. `RPA_NAV_004, RPA_NAV_006`).
5. Sandalye varsa oturak yüzeyine `RPA_SEAT_###` ekleyin (aynı numaralı çalışma noktasıyla eşleşir).
6. İsterseniz `RPA_MANAGER_01`, `RPA_MEET_###`, `RPA_RESEARCH_###`, `RPA_LABEL_<alan>` (`rpa_label` metin
   özelliğiyle) ve `RPA_CAMERA_TARGET` ekleyin.
7. File → Export → glTF 2.0:
   - Format: glTF Binary (.glb).
   - Include → Custom Properties işaretli.
   - Transform → +Y Up açık.
   - Mesh → Apply Modifiers açık.
   - Compression (Draco) kapalı.
8. Studio'da **Ofis → Ofis modeli → Model seç (.glb)**. Hata çıkarsa listedeki maddeleri düzeltip yeniden
   dışa aktarın.

## 9. Yeni model hazırlatırken kullanılacak yönerge (prompt)

Aşağıdaki metni bir 3D tasarımcıya veya model üreten bir yapay zekâ aracına olduğu gibi verebilirsiniz:

```text
RpaOrkestrAI Studio için bir 3D ofis modeli hazırla. Teslim: tek bir .glb dosyası (glTF 2.0 ikili),
en fazla 100 MB, bütün dokular dosyanın içine gömülü. Draco, meshopt ve KTX2 sıkıştırması kullanma.

Ölçü ve eksenler:
- Uzunluk birimi metre, yukarı ekseni +Y. Ofisin zemini Y = 0.
- Gerçek ölçüler kullan (kapı yüksekliği ≈ 2,1 m, masa ≈ 0,75 m, oturak ≈ 0,45–0,50 m).
- Ölçeklenmiş veya santimetre ile dışa aktarılmış model kabul edilmez.

Yerleşim noktaları: görünmez, benzersiz adlı boş düğümler (Empty). Şekil içermeyecekler.
- RPA_ORIGIN: ofisin referans noktası, zeminde; özel özellik rpa_layout_version = 1 (tamsayı);
  ölçeksiz, yukarı ekseni +Y.
- RPA_SPAWN_01: girişte, engelsiz bir nokta.
- RPA_WORK_001, RPA_WORK_002, …: her çalışma yeri için kişinin ayak tabanının olacağı yer (masa merkezi değil),
  zeminde; düğümün yerel +Z ekseni kişinin bakacağı yön (masaya doğru). Noktalar arası en az 0,6 m.
- RPA_WAIT_001, …: en az bir bekleme yeri (bekleme alanında), zeminde.
- RPA_SEAT_001, …: sandalyeli her çalışma yeri için oturak yüzeyinin ortası (0,30–0,80 m yükseklikte),
  aynı numaralı RPA_WORK noktasına en fazla 1 m; yerel +Z oturan kişinin bakacağı yön.
- İsteğe bağlı: RPA_MANAGER_01 (yöneticinin yeri) ve RPA_SEAT_MANAGER, RPA_MEET_001… (yöneticinin
  kapısı önünde buluşma yerleri), RPA_RESEARCH_001… (kitaplık veya araştırma köşesi),
  RPA_LABEL_<alan> (alan etiketleri; görünen metni rpa_label metin özelliğine yaz), RPA_CAMERA_TARGET.

Yol ağı (zorunlu):
- Koridorlara RPA_NAV_001, RPA_NAV_002, … noktaları koy (zeminde).
- Her yerleşim ve yol noktasına rpa_links metin özelliğiyle bağlandığı noktaların adlarını virgülle ayırarak yaz.
- Bağlantılar yalnız gerçekten yürünebilen düz çizgiler olsun: duvar, cam, masa veya mobilyanın içinden geçmesin.
- Bir bağlantı en fazla 40 m olsun.
- Her çalışma, bekleme, yönetici, buluşma ve araştırma noktası ağa bağlı olsun.
- Bütün ağ RPA_SPAWN_01'den ulaşılabilir tek parça olsun.
- Her RPA_WORK noktasını arkasındaki koridor noktasına tek bağlantıyla bağla.

Başka hiçbir düğümün adı RPA_ ile başlamasın. Dışa aktarırken özel özellikleri (custom properties) dahil et.
Teslimden önce şu listeyi kontrol et:
- düğüm adları yazıldığı gibi;
- bütün noktalar zeminde;
- yönler yatay;
- yol ağı kopuk değil.
```

## 10. Kontrol listesi

- [ ] Tek dosya `.glb`, ≤ 100 MB, dokular gömülü, sıkıştırma yok.
- [ ] Metre, +Y yukarı, zemin Y = 0; `RPA_ORIGIN` ölçeksiz, `rpa_layout_version = 1`.
- [ ] `RPA_SPAWN_01`, en az bir `RPA_WORK_###` ve en az bir `RPA_WAIT_###` var.
- [ ] Ayakta durulan bütün noktalar zeminde, yönleri yatay ve aralarında en az 0,6 m var.
- [ ] Yol ağı tek parça; her nokta `rpa_links` ile bağlı; bağlantılar engellerin içinden geçmiyor.
- [ ] Oturma referansları aynı numaralı çalışma noktasına ≤ 1 m, yükseklikleri 0,30–0,80 m.
- [ ] `RPA_` ile başlayan başka düğüm adı yok.
