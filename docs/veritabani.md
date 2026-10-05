# Salt okunur veritabanı erişimi

Akışlar veritabanından **Veritabanı sorgusu** adımıyla okur: SQL Server, PostgreSQL, MySQL / MariaDB, Oracle veya SQLite'ta tek bir `SELECT` sorgusu çalıştırılır. Adımın kullanımı, bağlantı formu ve `${değişken}` parametreleri [adım rehberindedir](adimlar.md#veritabanı). Bu sayfa, bağlantıda kullanılacak **salt okunur veritabanı hesabının** nasıl hazırlanacağını anlatır.

Uygulama sorguyu çalıştırmadan önce tek bir `SELECT`/`WITH` ifadesi olduğunu ve değiştiren veya kilitleyen sözcük (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `INTO`, `EXEC`, `FOR UPDATE` …) içermediğini denetler, işlemi her zaman geri alır ve PostgreSQL, MySQL, Oracle oturumunu salt okunur başlatır. Bu denetim ek bir korumadır, yetki sınırı değildir: sunucudaki fonksiyonlar veya saklı yordamlar yan etki doğurabilir. Asıl sınır, aşağıdaki gibi yalnız `SELECT` yetkisi verilmiş bir veritabanı kullanıcısıdır. SQL Server'da salt okunur oturum bulunmadığından bu kullanıcı zorunludur.

Eski akışlardaki **Tablo oku** adımı (kütüphanede yer almaz) yalnız bağlantıda izin verilen tablolardan, eşitlik filtreleriyle okur; bu izin listesi bağlantı formunda ancak o adım kullanılıyorsa görünür.

Uygulamadaki denetim ile sunucudaki kullanıcı yetkisi birbirini tamamlar. Bağlantıda `sa`, `postgres`, veritabanı sahibi veya yazma yetkili ERP hesabını kullanmayın. Aşağıdaki örnekler DBA'nın gerçek şema ve erişim modeline uyarlaması içindir; uygulama bu komutları çalıştırmaz.

## PostgreSQL örneği

Bu örnek veritabanının `erp`, şemanın `erp`, tablo adlarının tırnakla oluşturulmuş büyük harfli adlar olduğunu varsayar. Küçük harfli oluşturulmuş tablolar için adları gerçek katalogla eşleştirin.

DBA önce rolü oluşturur:

```sql
CREATE ROLE rpa_reader LOGIN
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

GRANT CONNECT ON DATABASE erp TO rpa_reader;
```

Parolayı SQL dosyasına veya Git'e koymadan psql'de etkileşimli belirleyin:

```text
\password rpa_reader
\connect erp
```

Hedef veritabanında yalnız gereken nesnelere erişim verin:

```sql
GRANT USAGE ON SCHEMA erp TO rpa_reader;
GRANT SELECT ON TABLE erp."IASSALITEM", erp."IASINVITEM" TO rpa_reader;

ALTER ROLE rpa_reader IN DATABASE erp
    SET default_transaction_read_only = on;
ALTER ROLE rpa_reader IN DATABASE erp
    SET statement_timeout = '30s';
```

`default_transaction_read_only` bir varsayılandır; tek başına yetkilendirme sınırı değildir. Yeni role başka rol üyelikleri vermeyin. Rolün nesne sahibi olmadığını; `PUBLIC`, rol üyelikleri ve özel fonksiyonlar üzerinden ek yetki almadığını DBA doğrulamalıdır. `PUBLIC` için mevcut yetkileri değiştirmek diğer uygulamaları etkileyebileceğinden burada otomatik veya genel bir `REVOKE` işlemi yapılmaz. [PostgreSQL GRANT](https://www.postgresql.org/docs/current/sql-grant.html), [salt okunur işlem varsayılanı](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-DEFAULT-TRANSACTION-READ-ONLY).

## SQL Server örneği

Aşağıdaki örnek SQL Server kimlik doğrulamasını kullanır. Kurumunuz Windows/Entra kimliği kullanıyorsa DBA uygun login/user eşlemesini yapmalıdır. Parola alanını gerçek bir sırla yalnız yönetim aracında doldurun; bunu dosyaya kaydetmeyin.

```sql
USE [master];
GO
CREATE LOGIN [rpa_reader]
    WITH PASSWORD = '<DBA_TARAFINDAN_BELIRLENECEK_GUCLU_PAROLA>',
    CHECK_POLICY = ON;
GO

USE [ERP];
GO
CREATE USER [rpa_reader] FOR LOGIN [rpa_reader];
GRANT CONNECT TO [rpa_reader];
GRANT SELECT ON OBJECT::[dbo].[IASSALITEM] TO [rpa_reader];
GRANT SELECT ON OBJECT::[dbo].[IASINVITEM] TO [rpa_reader];
DENY INSERT, UPDATE, DELETE, EXECUTE TO [rpa_reader];
GO
```

`db_owner`, `db_datawriter`, `sysadmin` gibi geniş roller vermeyin. Yalnız iki tablo gereken durumda `db_datareader` da tüm tabloları açacağından gerekli değildir. DBA mevcut rol üyeliklerini ve `public` izinlerini de denetlemelidir. [Microsoft nesne bazlı yetkilendirme](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-object-permissions-transact-sql?view=sql-server-ver16), [en az yetki ilkesi](https://learn.microsoft.com/en-us/sql/relational-databases/security/authentication-access/getting-started-with-database-engine-permissions?view=sql-server-ver17).

## Bağlantı yapılandırması

Bağlantı Studio'da adımın **Bağlantı** alanından form ile kurulur (veritabanı türü, sunucu, port, veritabanı adı, kullanıcı, şifre). Şifre yalnız o bilgisayardaki çalışma alanında saklanır, dışa aktarılan akışa eklenmez ve çalışma günlüğünde gizlenir. Aşağıdaki `.env` ayarı yalnız ilk açılışta varsayılan bağlantı oluşturmak içindir.

`.env.example` dosyasını `.env` olarak kopyalayın. Örnek SQLAlchemy bağlantı adresleri:

```dotenv
# PostgreSQL: kimlik bilgileri yer tutucudur.
RPA_DATABASE_URL=postgresql+psycopg://rpa_reader:PAROLA@sunucu:5432/erp
RPA_ALLOWED_TABLES=erp.IASSALITEM,erp.IASINVITEM

# SQL Server: yalnız seçtiğiniz bağlantıyı etkinleştirin.
# RPA_DATABASE_URL=mssql+pyodbc://rpa_reader:PAROLA@sunucu:1433/ERP?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
# RPA_ALLOWED_TABLES=dbo.IASSALITEM,dbo.IASINVITEM
```

URL içinde kullanılan parola özel karakterler içeriyorsa URL kodlaması gerekir. SQL Server sertifikası istemci tarafından güvenilir olmalı; kurumsal CA sertifikasını yükleyerek bağlantıyı düzeltin. `.env` içindeki `RPA_DATABASE_URL` yalnız ilk açılışta varsayılan bağlantıya dönüştürülür; sonraki değişiklikleri adımın **Bağlantı** alanından veya editördeki **Bağlantılar** penceresinden yapın.

İzin listesinde şemayla birlikte tablo adını kullanın: PostgreSQL için `erp.IASSALITEM`, SQL Server için `dbo.IASSALITEM`. Okunacak sütunları mümkün olduğunca daraltın, satır sınırı koyun ve büyük veri kümelerinde adaptörün parçalı okuma arayüzünü kullanın. Sınırlı sonuçlar tam rapor yerine örneklem olabilir; satır limitini iş gereksiniminize göre seçin.

## Python servisinin kullanımı

Studio'nun dışında aynı adaptörü kullanmak için, şema ve sütun adlarını kendi tablonuza uyarlayın:

```python
from contextlib import closing

from rpa_orkestrai.config import Settings
from rpa_orkestrai.database.reader import ReadOnlyDatabase

settings = Settings()
with ReadOnlyDatabase(
    settings.get("database_url"),
    {"erp.IASSALITEM": ["COMPANY", "MATERIAL", "QUANTITY"]},
    max_rows=10_000,
) as database:
    frame = database.read_table(
        "erp.IASSALITEM",
        columns=["MATERIAL", "QUANTITY"],
        filters={"COMPANY": "01"},
        limit=100,
    )
    print(frame.shape)

    with closing(database.iter_table("erp.IASSALITEM", chunk_size=1_000)) as chunks:
        for chunk in chunks:
            process_chunk = chunk.shape
            print(process_chunk)
```

`iter_table` da toplam satır sınırına uyar. `closing`, döngü erken sonlandırıldığında açık bağlantının bırakılmasını sağlar. Filtreler eşitlik, `None` için `IS NULL` ve liste değeri için `IN` destekler. Studio yapılandırması tablo listesi sunar; Python servisinde yukarıdaki gibi tablo başına sütun izinleri de verilebilir.

## İlk gerçek bağlantının doğrulanması

DBA erişimleri hazırladıktan sonra önce düşük satır sınırıyla izin verilen bir tablonun okunabildiğini doğrulayın. İzin verilmeyen tabloyu uygulamanın reddettiğini test edin. Yazma yetkisinin bulunmadığını DBA yetki görünümünden veya ayrı test veritabanında doğrulayın; üretim ERP'sine deneme amaçlı `UPDATE` göndermeyin.

SQL Server/PostgreSQL gerçek bağlantı testleri CI kapsamına girmez. CI'deki sahte bağlantı testleri sorgu oluşturma ve izin listesi mantığını denetler; sunucudaki fiili hesap yetkilerini kanıtlamaz.
