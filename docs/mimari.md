# LUMINOVA mimari kararlar

Durum: Planlanan dokuz modülün tamamı, ekip ve roller, bildirimler ve tercihleri, hatırlatmalar, etkinlik akışı, destek ve platform yönetimi, proje aşamaları, imzalı webhook'lar, veri dışa aktarma ve kapatma talepleri çalışır. Açık modüller sol menüde görünür ve erişim sunucuda denetlenir. E-posta n8n üzerinden gider: LUMINOVA iletiyi sıraya yazar, işçi imzalı olarak n8n'e iletir, SMTP gönderimini n8n yapar ve sonucu geri bildirir (`docs/n8n.md`, bölüm 3). Kanal tanımlı değilse e-posta sıraya alınmaz; yerel ortam doğrulama ve davet bağlantılarını ekranda gösterir ve hiçbir yerde gönderilmiş gibi söylemez. Ödeme ve hukuki metinler bağlı değildir. Yayına alma ve yedekleme `docs/yayin.md` içindedir. Kararlar değişirse gerekçesi bu belgeye yazılır.

n8n iş akışları bu depoda üretilmez; n8n arayüzünde kurulur. Uygulama bunun için API, webhook ve olay sözleşmesini sağlar.

## 1. Mevcut durum

Geliştirme makinesinde Node.js 24, npm 11, Python 3.14 ve Docker Desktop vardır. Veritabanı Docker içindeki PostgreSQL 16 ile çalışır ve konak makinede yalnızca `127.0.0.1:5433` adresine açılır. 5432 başka bir yerel Postgres tarafından kullanıldığı için LUMINOVA onu paylaşmaz. Migration zinciri `0001`'den `0032_support_kinds`'e kadardır; testler ayrı `luminova_test` veritabanında çalışır.

## 2. Klasör yapısı

```text
LUMINOVA/
  docker-compose.yml  yerel PostgreSQL
  .env.example
  deploy/             canlı Dockerfile'lar, nginx, compose, yedek ve geri yükleme betikleri
  scripts/            yerel yardımcılar (yedek)
  docs/               mimari.md, yayin.md, n8n.md
  backend/
    app/
      api/            HTTP katmanı (routes/, deps.py)
      core/           ayar, veritabanı oturumu, güvenlik
      db/             ORM tabanı
      models/         platform tabloları (kimlik, ekip, bildirim, destek, otomasyon, kapatma)
      schemas/
      services/       platform iş kuralları
      modules/        iş modülleri: models, schemas, service, routes
      cli.py          yönetici yetkisi ve webhook işçisi
    alembic/
    tests/
  frontend/
    src/
      components/     modül ekranları ve ortak bileşenler
      pages/          sayfalar (panel, yönetim, hesap)
      lib/            API istemcileri
      styles/         tokenlar
```

Tek depo, tek backend süreci, tek veritabanı. Modüller ayrı servis değildir. Her modül kendi model, servis ve route sınırına sahip olur. Bir modül başka modülün tablosunu doğrudan güncellemez; bunun için sahibin servisini çağırır.

## 3. Frontend ve backend mimarisi

Backend Python, FastAPI, SQLAlchemy 2, Alembic ve PostgreSQL kullanır. İş kuralları route fonksiyonunun içinde büyümez; servis katmanına yazılır. Pydantic şemaları HTTP sınırındadır.

Kimlik modeli:

- Parolalar Argon2id ile hashlenir.
- Oturum sunucuda saklanır. Çerezde yalnızca ham oturum belirteci bulunur, veritabanında SHA-256 özeti durur.
- Çerez `HttpOnly` ve `SameSite=Lax` olur. Canlıda `Secure` zorunludur.
- Durum değiştiren istekler `X-CSRF-Token` başlığı taşır.
- E-posta doğrulama ve parola sıfırlama belirteçleri hashlenir, kısa sürelidir ve tek kullanımlıktır.
- Platform yöneticisi, şirket sahibinden ayrı bir yetkidir. Yetki arayüzden verilmez; kayıtlı bir hesaba sunucuda `python -m app.cli grant-admin <e-posta>` ile verilir. Komut parola istemez ve parola yazmaz.

Frontend React, TypeScript, Vite ve React Router kullanır. Açık ve koyu tema vardır; renkler CSS değişkenlerindedir (`html.dark`) ve seçim profil menüsündeki Görünüm ayarından yapılır.

Veri okuma `fetch` ile yapılır (`lib/http.ts`); Zod, React Hook Form ve TanStack Query kullanılmadı, formlar kendi doğrulamasını yapar ve sunucu doğrulaması esastır. Rapor grafikleri ek kütüphane olmadan SVG ile çizilir.

Arayüz metinleri Türkçedir. Kod, API adları ve modül anahtarları İngilizcedir.

## 4. PostgreSQL veri modeli taslağı

Birincil anahtarlar UUID'dir. Zaman damgaları `timestamptz` ve UTC'dir. Para tutarları `numeric(19, 4)` alanındadır; kayan nokta kullanılmaz. Para birimi ISO kodu olarak saklanır.

Tablolar migration ile eklenir. Aşağıdaki liste kurulu şemadır; ayrıntılar API bölümündeki ilgili paragraftadır.

Kimlik ve kiracı:

- `users`: ad, soyad, benzersiz e-posta, parola hash, platform yöneticisi bayrağı, e-posta doğrulama zamanı, hesap durumu.
- `email_verification_tokens`, `password_reset_tokens`: kullanıcı, token hash, son kullanma, kullanılma zamanı.
- `sessions`: kullanıcı, token hash, son kullanma, iptal zamanı, kısaltılmış user agent.
- `companies`: ad, slug, sahip kullanıcı, durum, saat dilimi, kapanış zamanı.
- `company_memberships`: şirket, kullanıcı, rol (`owner`, `admin`, `member`), durum. Aynı çift tekrar edemez. Bir hesap tek bir çalışma alanına üyedir.
- `company_invitations`: hashlenmiş davet belirteci, rol, son kullanma, kabul ve iptal zamanı.

Modüller:

- Modül kataloğu kodda durur: `sales`, `inventory`, `production`, `customers`, `finance`, `tasks`, `projects`, `reporting`, `automation`.
- `company_modules`: şirket, modül anahtarı, etkinleşme, devre dışı kalma, şema sürümü. Devre dışı bırakmak satırı silmez.

İşletme verisi:

- `customers`: şirket, ad, e-posta, telefon, not, silinme zamanı.
- `products`: şirket, SKU, ad, açıklama, birim, minimum stok. SKU şirket içinde benzersizdir.
- `stock_movements`: şirket, ürün, hareket türü, miktar, referans türü ve kimliği, idempotency anahtarı, zaman, işlemi yapan. Stok bakiyesi hareketlerden hesaplanır ve ürün üzerinde aynı işlemde güncellenen önbellek olarak durur.
- `orders`, `order_items`, `order_status_events`. Sipariş durumunda stok işlendiyse `stock_posted_at` dolar. Aynı sipariş ikinci kez stok düşürmez.
- `production_orders`, `production_materials`. Tamamlama, hammadde çıkışı ve mamul girişi tek transaction içindedir. Stok yetmezse işlem tamamlanmış görünmez.
- `financial_records`: gelir veya gider, kategori, tutar, para birimi, tarihler, durum, sipariş bağlantısı. Değişiklikler `financial_record_revisions` içine yazılır. Sipariş, kullanıcı açıkça gelir kaydı oluşturursa finansal kayda bağlanır.
- `quotes`, `quote_items`: teklif ve satırları; kabul edilen teklif `order_id` ile siparişe bağlanır.
- `projects`, `project_milestones`, `tasks`. İlerleme, tamamlanan görev sayısının toplam göreve bölümüdür; aşamalar ayrı sayılır.
- `notifications`: şirket, kullanıcı, kategori, başlık, bağlantı, `dedupe_key`, okunma zamanı. Aynı olay yeni bildirim çoğaltmaz.
- `notification_preferences`: kullanıcı ve kategori başına uygulama içi tercih; `email` sütunu e-posta servisi bağlanınca kullanılacak.
- `support_tickets`, `support_messages`: müşteri ve LUMINOVA ekibi mesajları. E-posta gönderilmez.
- `audit_logs`: aktör, şirket, işlem, varlık, özet JSON, kaynak (`api`, `admin`, `webhook`), zaman. Parola, oturum belirteci ve API anahtarı yazılmaz. Güncelleme ve silme endpoint'i yoktur.
- `webhook_endpoints`, `automation_events`, `webhook_deliveries`: bağlantılar, olay kutusu ve gönderim denemeleri. Gizli anahtar tabloda tutulmaz, türetilir.
- `closure_requests`: çalışma alanı kapatma talebi ve 30 günlük bekleme. Dışa aktarma istek anında üretildiği için tablo tutmaz.
- Abonelik tabloları yoktur; ödeme bağlanmadığı için tüm çalışma alanları ücretsiz erken erişimdedir ve kart bilgisi istenmez.

Silme davranışı tabloya göredir. Müşteri ve üründe kontrollü silinme zamanı vardır. Finansal kayıt, stok hareketi ve audit log fiziksel silinmez. Modül kapatmak veri silmez.

## 5. Multi-tenant güvenlik

Kiracı ayrımı satır düzeyindedir. Her şirket aynı şemayı kullanır. Şirkete ait her sorgunun `company_id` değeri, oturumdaki üyelikten gelir. İstemcinin gönderdiği şirket kimliği, üyelik ile aynı değilse istek reddedilir.

Modül kapalıysa ilgili endpoint sunucuda 403 döner. Menüden gizleme yetki sayılmaz. Platform yönetim route'ları ayrı bağımlılıkla `is_platform_admin` kontrolü yapar.

Eksik `company_id` filtresi veri sızıntısıdır. Liste ve tekil okuma aynı tenant bağımlılığını kullanır. Testler, başka şirketin kaydının okunamadığını ve değiştirilemediğini doğrular.

Parola sıfırlama yanıtı, e-postanın kayıtlı olup olmadığını söylemez. Başarısız e-posta gönderimi başarılı diye raporlanmaz.

## 6. API taslağı

Çalışan endpoint'ler:

- `GET /api/v1/health`
- `GET /api/v1/auth/csrf`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/verify-email`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `POST /api/v1/workspace/setup`
- `GET /api/v1/modules`, `PUT /api/v1/modules`
- `GET /api/v1/modules/{module_key}`
- `GET /api/v1/notifications`, `POST /api/v1/notifications/read-all`, `POST /api/v1/notifications/{id}/read`
- `GET /api/v1/customers?q=&sort=&page=&page_size=`, `POST /api/v1/customers`
- `GET /api/v1/customers/{id}`, `PUT /api/v1/customers/{id}`, `DELETE /api/v1/customers/{id}`

Müşteri uç noktaları `require_module("customers")` bağımlılığından geçer: oturum, tamamlanmış kurulum ve açık modül ister; aksi halde 401 veya 403 döner. Başka şirketin müşterisi 404 döner. Silme `deleted_at` alanını doldurur, satır kalır. E-posta, şirket içinde silinmemiş müşteriler arasında büyük/küçük harf farkı gözetmeden benzersizdir. Arama ad, e-posta ve telefonda yapılır; ad araması ve ada göre sıralama Türkçe ICU kuralını (`tr-TR-x-icu`) kullanır. Denetim kaydına yalnızca değişen alan adları yazılır, e-posta ve telefon yazılmaz. Yeni iş modülleri `app/modules/<modül>/` altında model, şema, servis ve route dosyalarıyla aynı kalıbı izler.

- `GET /api/v1/inventory/summary`
- `GET /api/v1/inventory/products?q=&sort=&low=&page=&page_size=`, `POST /api/v1/inventory/products`
- `GET|PUT|DELETE /api/v1/inventory/products/{id}`
- `GET|POST /api/v1/inventory/products/{id}/movements`

Stok hareketleri yalnızca eklenir; güncelleme ve silme uç noktası yoktur. Türler `in`, `out` ve `adjustment` (sayım) olarak tutulur; `quantity` işaretli farktır, `balance_after` hareket sonrası bakiyedir. Hareket ürün satırını `FOR UPDATE` ile kilitler, bakiyeyi aynı işlemde ürünün `stock_quantity` alanına yazar ve eksi bakiyeyi 409 ile reddeder. Veritabanı kısıtları da negatif bakiyeyi engeller. `idempotency_key` şirket içinde benzersizdir; aynı anahtarla gelen tekrar istek yeni hareket üretmez, ilk hareketi döner. Adet, paket ve kutu birimlerinde miktar tam sayı olmalıdır. Bakiye minimumun üstünden altına geçtiğinde, hareket kimliğine bağlı tek bir `inventory` bildirimi oluşur ve `/panel/stok?kritik=1` adresine bağlanır. Ürün oluştururken verilen açılış stoku "Açılış stoku" notlu bir giriş hareketi olarak yazılır. `reference_type` ve `reference_id` alanları satış ve üretim hareketleri için ayrılmıştır.

- `GET /api/v1/sales/summary`
- `GET /api/v1/sales/orders?q=&status=&sort=&page=&page_size=`, `POST /api/v1/sales/orders`
- `GET|PUT /api/v1/sales/orders/{id}`
- `POST /api/v1/sales/orders/{id}/confirm`, `/fulfil`, `/cancel`

Sipariş numarası şirket içinde sıralıdır ve `SP-0001` biçiminde gösterilir; yeni numara şirket satırı kilitlenerek alınır. Durumlar: `draft` (taslak), `confirmed` (onaylandı), `fulfilled` (teslim edildi), `cancelled` (iptal edildi). Yalnızca taslak düzenlenir. Onay stoğa dokunmaz. Teslim, ürün satırlarını ürün başına toplar, ürünleri kimlik sırasıyla `FOR UPDATE` kilitler, önce tüm eksikleri denetler ve stok yetmezse hiçbir hareket yazmadan 409 döner. Yeterliyse her ürün için "SP-000N teslimatı" notlu, `reference_type = "order"` çıkış hareketi yazılır ve `stock_posted_at` dolar. Teslim edilmiş sipariş iptal edilirse aynı miktarlar `order_cancel` referanslı giriş hareketiyle stoğa döner. Hareket anahtarları sipariş ve ürün kimliğinden türetilir; aynı işlem iki kez stok düşürmez veya iade etmez. Her durum geçişi `order_status_events` tablosuna not ve aktörle yazılır.

Satır ya stoklu bir ürüne bağlıdır ya da serbest açıklamalı stok dışı satırdır (hizmet, montaj gibi). KDV oranı %0, %1, %10 veya %20; para birimi TRY, USD veya EUR olur. Satır ara toplamı ve KDV ayrı ayrı 0,01'e yuvarlanır (ROUND_HALF_UP); sipariş toplamı satırların toplamıdır. Arama müşteri adında ve sipariş numarasında (`SP-12`, `sp12`, `12`) yapılır. Arayüz fiyatı `1.250,00` gibi Türkçe biçimde de kabul eder.

- `GET /api/v1/tasks/summary`, `GET /api/v1/tasks/assignees`
- `GET /api/v1/tasks?q=&status=&priority=&assignee=me|none|<id>&due=overdue|today|week|none&sort=&page=&page_size=`, `POST /api/v1/tasks`
- `GET|PUT|DELETE /api/v1/tasks/{id}`, `POST /api/v1/tasks/{id}/status`

Görev durumları `todo` (yapılacak), `in_progress` (devam ediyor), `done` (tamamlandı); öncelikler `low`, `normal`, `high`, `urgent`. `completed_at` yalnızca `done` durumunda doludur ve veritabanı kısıtı bunu zorlar. "Bugün", sunucu saatine göre değil şirketin saat dilimine göre veritabanında hesaplanır (`timezone(companies.timezone, now())::date`); gecikme, teslim tarihi bugünden önce olan ve tamamlanmamış görevdir. Liste yanıtı bu tarihi `today` alanında döndürür, arayüz "Bugün", "Yarın", "2 gün gecikti" etiketlerini buna göre yazar. Sorumlu yalnızca şirketin etkin üyelerinden seçilir. Görev başka bir üyeye atanırsa o kişiye tek bir `tasks` bildirimi yazılır; kişi kendine atadığında bildirim oluşmaz. Silme `deleted_at` ile yapılır. Teslim tarihi yaklaşan ve geciken görevlerin hatırlatmaları Bildirimler paragrafında anlatılır. Pano üç sütundur; tamamlananlar sütunu son 20 görevi gösterir.

- `GET /api/v1/projects/summary`
- `GET /api/v1/projects?q=&status=&sort=&page=&page_size=`, `POST /api/v1/projects`
- `GET|PUT|DELETE /api/v1/projects/{id}`
- Görevler: `project_id` alanı ve `GET /api/v1/tasks?project=<id>|none` filtresi

Proje durumları `planned` (planlandı), `active` (devam ediyor), `on_hold` (beklemede), `completed` (tamamlandı). `completed_at` yalnızca tamamlandı durumunda doludur; teslim tarihi başlangıçtan önce olamaz, iki kural da veritabanı kısıtıyla korunur. Proje isteğe bağlı olarak şirketin bir müşterisine bağlanır. İlerleme ayrı tutulmaz: projeye bağlı ve silinmemiş görevlerden tamamlananların oranıdır (`task_done / task_total`, tam sayıya yuvarlanır). Proje gecikmesi, tamamlanmamış ve teslim tarihi şirket gününden önce olan projedir; `task_overdue` projedeki gecikmiş görev sayısıdır. Proje silinince satır `deleted_at` ile işaretlenir ve bağlı görevlerin `project_id` alanı boşaltılır; görevler silinmez, denetim kaydına kaç görevin ayrıldığı yazılır. Görev, yalnızca aynı şirketin silinmemiş projesine bağlanabilir.

- `GET /api/v1/finance/categories`, `GET /api/v1/finance/summary?from=&to=`
- `GET /api/v1/finance/records?q=&kind=&status=&overdue=&from=&to=&order_id=&sort=&page=&page_size=`, `POST /api/v1/finance/records`
- `GET|PUT /api/v1/finance/records/{id}`, `POST /api/v1/finance/records/{id}/cancel`

Finansal kayıt `income` (gelir) veya `expense` (gider) türündedir; kategori türe göre sabit listeden seçilir. Durum `pending`, `paid` veya `cancelled` olur. Bekleyen gelir alacağı, bekleyen gider borcu oluşturur; vadesi şirket gününden önce olan bekleyen kayıt gecikmiş sayılır. `paid_on` yalnızca ödenmiş kayıtta doludur ve veritabanı kısıtıyla korunur. Tutar `numeric(19,4)` alanında durur, 0,01 hassasiyetle girilir ve sıfırdan büyük olmalıdır. Kayıt fiziksel olarak silinmez; iptal, zorunlu bir nedenle yapılır ve geri alınamaz. İptal edilen kayıt düzenlenemez ve özetlere girmez. Oluşturma, her değişiklik ve iptal `financial_record_revisions` tablosuna sıra numarası, işlem, alan bazında eski ve yeni değer, neden ve işlemi yapanla yazılır.

Özet dönem içindir: gelir ve gider, kayıt tarihi seçilen dönemde olan iptal edilmemiş kayıtların toplamıdır; varsayılan dönem şirketin içinde bulunduğu aydır. Açık alacak ve borç dönemden bağımsız olarak tüm bekleyen kayıtların toplamıdır. Toplamlar para birimine göre ayrı döner; kur dönüşümü yapılmaz, TRY her zaman ilk satırdır.

Sipariş gelire yalnızca kullanıcı işlemiyle bağlanır: sipariş panelindeki "Gelir kaydı oluştur" düğmesi formu sipariş toplamı, para birimi ve müşteriyle doldurur, kullanıcı tutarı ve vadeyi değiştirebilir. Bağlantı yalnızca onaylanmış veya teslim edilmiş siparişe kurulur, kayıt türü gelir olmak zorundadır ve bir siparişe aynı anda tek bir iptal edilmemiş gelir kaydı bağlanabilir (kısmi benzersiz indeks `uq_financial_records_order_id`). Gelir kaydı iptal edilirse sipariş yeniden bağlanabilir. Siparişin sonradan iptal edilmesi gelir kaydını kendiliğinden değiştirmez; sipariş paneli bu durumda uyarı gösterir.

- `GET /api/v1/production/summary`
- `GET /api/v1/production/orders?q=&status=&sort=&page=&page_size=`, `POST /api/v1/production/orders`
- `GET|PUT /api/v1/production/orders/{id}`
- `POST /api/v1/production/orders/{id}/start`, `/complete`, `/cancel`

İş emri numarası şirket içinde sıralıdır ve `UE-0001` biçiminde gösterilir. Bir iş emri tek bir mamul ürün ve miktarından, en az bir en fazla elli malzeme satırından oluşur; malzeme miktarı toplam tüketimdir. Mamul kendi malzemesi olamaz, aynı malzeme iki satırda tekrar edemez, adet, paket ve kutu birimlerinde miktar tam sayıdır. Durumlar `planned` (planlandı), `in_progress` (üretimde), `completed` (tamamlandı), `cancelled` (iptal edildi). Yalnızca planlanan iş emri düzenlenir. Tamamlama planlanan veya üretimdeki iş emrinden yapılır: mamul ve malzemeler kimlik sırasıyla `FOR UPDATE` kilitlenir, önce tüm eksikler denetlenir ve bir malzeme yetmezse hiçbir hareket yazılmadan 409 döner. Yeterliyse her malzeme için "UE-000N üretim tüketimi" notlu çıkış, mamul için "UE-000N üretim çıkışı" notlu giriş hareketi aynı transaction içinde `reference_type = "production"` ile yazılır ve `stock_posted_at` dolar; veritabanı kısıtı tamamlanmış iş emrinde bu alanın dolu olmasını zorlar. Hareket anahtarları iş emri ve ürün kimliğinden türetilir. Tamamlanan iş emri iptal edilmez; düzeltme Stok ve Depo modülündeki sayım hareketiyle yapılır. İptal zorunlu bir nedenle yapılır ve stoğa dokunmaz. Listede ve detayda, açık iş emirleri için malzemenin o anki stoğu gereken miktarın altındaysa "malzeme eksik" gösterilir.

- `GET /api/v1/quotes/summary`, `GET|POST /api/v1/quotes`, `GET|PUT /api/v1/quotes/{id}`
- `POST /api/v1/quotes/{id}/send`, `/accept`, `/reject`, `/convert`

Teklifler Müşteri ve Teklifler modülüne aittir ve `TK-0001` biçiminde numaralanır. Satırlar sipariş satırlarıyla aynı kurala uyar (ürün ya da açıklama, KDV %0/1/10/20, satır başına 0,01 yuvarlama). Akış: taslak → gönderildi → kabul edildi veya reddedildi; yalnızca taslak düzenlenir. LUMINOVA teklifi müşteriye kendisi göndermez; "gönderildi" kullanıcının işaretidir. Geçerlilik tarihi geçmiş ve yanıt bekleyen teklif "süresi doldu" olarak gösterilir. Kabul edilen teklif, Satış ve Siparişler modülü açıksa siparişe çevrilir: aynı transaction içinde taslak sipariş satırlarıyla oluşturulur ve `quotes.order_id` dolar; bu alan benzersizdir, bir teklif bir kez çevrilir. Sipariş taslak olarak açıldığı için stoğa dokunulmaz.

- `GET /api/v1/reports/overview?months=3|6|12`

Rapor, yalnızca şirkette açık olan modüllerin bölümlerini döndürür; kapalı modülün bölümü `null` gelir. Aylar şirketin saat diliminde gruplanır ve kaydı olmayan ay sıfırla doldurulur. Satış geliri onaylanmış ve teslim edilmiş TRY siparişlerinin toplamıdır; başka para birimindeki siparişler sayılır ama tutara katılmaz ve rapor bunu ayrıca belirtir. Finans bölümü iptal edilmemiş TRY kayıtlarını kullanır. Ayrı bir rapor tablosu yoktur; her istek kaynak tablolardan hesaplanır. Ana sayfadaki işletme özeti, açık modüllerin kendi özet uç noktalarından gelir ve kayıt yoksa sahte rakam göstermez.

Kullanıcıya dönen stok mesajları (yetersiz stok, kritik seviye bildirimi) miktarı Türkçe ondalık biçimiyle (`2,5`) yazar; API alanlarındaki sayılar nokta ayraçlı dizgi olarak kalır.

Kurulum akışı: kayıt, e-posta doğrulama, giriş, modül seçimi (`/kurulum`), panel. `companies.setup_completed_at` boşsa giriş kullanıcıyı kuruluma yönlendirir ve modül uç noktaları 403 döner. Kurulum en az bir modül ister ve yalnızca bir kez tamamlanır. E-posta servisi bağlı olmadığı için kurulum sonunda onay e-postası gönderilmez; arayüz bunu gönderilmiş gibi göstermez.

Modül uç noktaları şirketi oturumdaki üyelikten alır; istek gövdesinde şirket kimliği yoktur. Seçim, gereken modüllerle birlikte uygulanır: Satış ve Siparişler için Müşteri ve Teklifler ile Stok ve Depo, Proje Yönetimi için Görev ve İş Yönetimi, Üretim için Stok ve Depo otomatik açılır. Seçimden çıkan modülün satırı `disabled` olur, verisi silinmez. Değişiklik şirket satırını kilitleyerek çalışır, `audit_logs` tablosuna ve bildirimlere yazılır. Kapalı modülün `GET /modules/{key}` isteği 403 döner; ileride modül verisi okuyan her uç nokta aynı kontrolü kullanır.

Ekip: `GET /api/v1/team`, `POST /api/v1/team/invitations`, `DELETE /api/v1/team/invitations/{id}`, `PUT|DELETE /api/v1/team/members/{user_id}`, `GET /api/v1/auth/invitations/preview?token=`, `POST /api/v1/auth/invitations/accept`. Roller `owner` (sahip), `admin` (yönetici) ve `member` (üye) olur. Modül tercihlerini ve ekibi sahip ile yönetici değiştirir; yönetici davet etmeyi, rol değiştirmeyi ve yönetici çıkarmayı yalnızca sahip yapar; sahip çıkarılamaz ve rolü değişmez. Bir hesap tek bir çalışma alanına üye olabilir, bu yüzden kayıtlı bir e-postaya davet gönderilmez. Davet belirteci hashlenir, 7 gün geçerlidir, tek kullanımlıktır ve aynı e-postaya aynı anda tek açık davet olur. E-posta servisi yokken davet bağlantısı yalnızca local ve test ortamında yanıtta döner; arayüz bunu "gönderilmedi" diye açıkça söyler. Davet kabul edilince hesap etkin ve e-postası doğrulanmış olarak açılır, çünkü bağlantıyı yalnızca davet edilen kişi alır; sonra oturum açılır ve daveti gönderene bildirim düşer. Üye çıkarıldığında üyeliği `disabled` olur, açık oturumları kapanır ve girdiği kayıtlar silinmez. Etkin üyeliği olmayan hesap giriş yapamaz.

Bildirimler: `GET /api/v1/notifications`, `POST /api/v1/notifications/read-all`, `POST /api/v1/notifications/{id}/read`, `GET|PUT /api/v1/notifications/preferences`. Kategoriler `tasks`, `finance`, `inventory`, `team`, `support`, `automation` ve `workspace` olur. Tercih kullanıcı ve şirket başına `notification_preferences` tablosunda tutulur; satır yoksa kategori açık sayılır. Kapalı kategoriye bildirim yazılmaz. Teslim ve vade hatırlatmaları ayrı bir zamanlayıcı olmadan, bildirim listesi her istendiğinde üretilir: size atanmış, bitmemiş ve bugün, yarın teslim edilecek ya da gecikmiş görevler; sahip ve yönetici için 3 gün içinde vadesi gelen veya geçmiş bekleyen finans kayıtları. Her hatırlatmanın kayıt ve vade tarihine bağlı tekil anahtarı vardır, bu yüzden aynı hatırlatma ikinci kez yazılmaz; vade değişirse yeni hatırlatma çıkar. Bir istekte en çok 10 hatırlatma hazırlanır. `email` sütunu e-posta servisi bağlandığında kullanılacak; şimdilik arayüzde gösterilmez ve e-posta gönderilmez.

Etkinlikler: `GET /api/v1/activity?module=&actor=&cursor=&limit=`. Ayrı tablo yoktur; `audit_logs` satırları okunur ve kişi, eylem, hedef ve ayrıntı olarak Türkçe metne çevrilir (ör. "Ömer sipariş durumunu değiştirdi SP-0001, Taslak → Onaylandı"). Hedef adı istek anında kaynak tablodan okunur; silinmiş kayıtların adı görünür ama bağlantısı verilmez. Kapalı modüllerin etkinlikleri listelenmez. Ekip etkinliklerinin tamamını sahip ve yönetici görür; üye yalnızca katılımları görür. Sayfalama `created_at` ve `id` üzerinden imleçle yapılır, bu yüzden yeni kayıt geldiğinde satırlar kaymaz. Ana sayfadaki "Son etkinlikler" alanı aynı uç noktanın ilk 5 satırıdır; ekran `/panel/aktiviteler` adresindedir.

Proje aşamaları: `GET|POST /api/v1/projects/{id}/milestones`, `PUT|DELETE /api/v1/projects/{id}/milestones/{milestone_id}`, `POST /api/v1/projects/{id}/milestones/{milestone_id}/move` (`up` veya `down`). Aşamalar `project_milestones` tablosunda sıra numarasıyla tutulur; bir projede en çok 30 aşama olur. Aşama tamamlanınca `completed_at` dolar; ilerleme yüzdesi yine görevlerden hesaplanır, aşamalar ayrı sayılır. Proje yanıtı `milestone_total`, `milestone_done` ve sıradaki tamamlanmamış aşamayı (`next_milestone`, `next_milestone_due`) döndürür; proje kartı bunu gösterir. Aşama eklemek, tamamlamak, yeniden açmak ve kaldırmak proje kaydına denetim satırı yazar ve etkinlik akışında görünür.

Destek: `GET|POST /api/v1/support/tickets`, `GET /api/v1/support/tickets/{id}`, `POST /api/v1/support/tickets/{id}/messages`, `POST /api/v1/support/tickets/{id}/close`. Talepler `support_tickets` ve `support_messages` tablolarındadır; numara şirket başına `DT-0001` biçimindedir. Üye yalnızca kendi açtığı talepleri, sahip ve yönetici şirketin tüm taleplerini görür. Durumlar: `open` (yanıt bekliyor), `answered` (yanıtlandı), `closed` (kapandı). Müşteri yazınca talep `open`, LUMINOVA ekibi yazınca `answered` olur; kapanan talebe yazılamaz. Bir kullanıcının aynı anda en çok 20 açık talebi olabilir. Ekip yanıtı müşteri tarafında "LUMINOVA Destek" adıyla görünür ve talebi açana `support` kategorisinde uygulama içi bildirim düşer; e-posta gönderilmez.

Otomasyonlar: `GET /api/v1/automation/events`, `GET|POST /api/v1/automation/endpoints`, `PUT|DELETE /api/v1/automation/endpoints/{id}`, `POST /api/v1/automation/endpoints/{id}/rotate`, `POST /api/v1/automation/endpoints/{id}/test`, `GET /api/v1/automation/deliveries`, `POST /api/v1/automation/deliveries/{id}/retry` ve oturumsuz `POST /api/v1/hooks/{id}`. Bağlantıları yalnızca sahip ve yönetici yönetir; modül kapalıysa olay üretilmez. Tablolar: `webhook_endpoints` (giden veya gelen bağlantı), `automation_events` (giden olay kutusu ve gelen istek kaydı) ve `webhook_deliveries` (bağlantı başına gönderim, deneme sayısı, son hata). Olay, iş kaydıyla aynı transaction içinde kutuya yazılır; gönderimi ayrı `python -m app.cli webhook-worker` süreci yapar, `FOR UPDATE SKIP LOCKED` ile iş alır ve 2 dakikalık kira koyar, böylece birden çok işçi aynı gönderimi almaz. İmza `HMAC-SHA256(anahtar, zaman_damgası + "." + ham_gövde)` biçimindedir. Anahtar tabloda tutulmaz; `WEBHOOK_SECRET_KEY`, bağlantı kimliği ve sürüm numarasından türetilir, yalnızca oluşturma ve yenileme yanıtında bir kez döner. Gelen isteklerde 5 dakikalık zaman toleransı, imza kontrolü ve `X-Luminova-Delivery` ile tekrar engeli vardır; desteklenen işlemler `task.create` ve `notification.create`'tir ve etkinlik akışında "Otomasyon" olarak görünür. Production'da giden adres `https` olmalı ve iç ağ adresine çözümlenmemelidir. n8n kurulum rehberi `docs/n8n.md` dosyasındadır; iş akışı JSON'u üretilmez.

Veri ve hesap: `POST /api/v1/exports/workspace` sahip ve yöneticiye şirketin tüm iş tablolarını ZIP içinde ayrı CSV dosyaları olarak verir (UTF-8 BOM, `;` ayracı, ondalıkta virgül; Türkçe Excel doğrudan açar). Pakette `BENIOKU.txt`, şirket kaydı olan her tablo ve `uyeler.csv` vardır; şifre, oturum, webhook anahtarı ve kişisel bildirimler yoktur. Dosya istek anında üretilir ve sunucuda saklanmaz. `GET /api/v1/me/export` her kullanıcıya kendi profilini, üyeliklerini, atanan görevlerini, destek taleplerini ve bildirimlerini JSON olarak verir. İki işlem de denetim kaydına yazılır. Çalışma alanı kapatma: sahip şifresiyle `POST /api/v1/workspace/closure` talebi açar, talep `closure_requests` tablosunda 30 gün bekler ve `DELETE` ile iptal edilir; bu sürede tüm üyelere üst şeritte kapanış tarihi gösterilir. Süre dolunca platform yöneticisi `/yonetim` ekranından (`POST /api/v1/admin/closures/{id}/complete`) kapatmayı tamamlar: şirket `closed` olur, üyelikler `disabled` olur, açık oturumlar kapanır, giriş engellenir. Kayıtlar bu adımda silinmez; saklama ve imha süreleri hukuki metinlerle birlikte belirlenecek. Sahip olmayan kullanıcı şifresiyle `POST /api/v1/me/close` ile kendi hesabını hemen kapatabilir; girdiği kayıtlar şirkette kalır. Sahip, çalışma alanı kapanmadan kendi hesabını kapatamaz.

Platform yönetimi: `GET /api/v1/admin/overview`, `GET /api/v1/admin/companies?q=&page=`, `GET /api/v1/admin/support/tickets?status=`, `GET /api/v1/admin/support/tickets/{id}`, `POST /api/v1/admin/support/tickets/{id}/reply`, `POST /api/v1/admin/support/tickets/{id}/close`. Bu uç noktalar `users.is_platform_admin` ister ve bilerek şirketler arası okur; şirketlerin iş kayıtlarını (müşteri, sipariş, finans) döndürmez, yalnızca hesap özetlerini ve destek taleplerini gösterir. Yönetici işlemleri ilgili şirketin `audit_logs` kaydına `source = admin` ile yazılır ve şirketin etkinlik akışında görünmez. Yetki arayüzden verilmez; sunucuda `python -m app.cli grant-admin <e-posta>` ve `revoke-admin` komutlarıyla değiştirilir. Ekran `/yonetim` adresindedir; yetkisi olmayan kullanıcı bilgilendirme görür.

"Beni hatırla" seçiliyse oturum 30 gün geçerlidir ve çerez kalıcıdır. Seçili değilse çerez tarayıcı oturumuyla sınırlıdır ve sunucu oturumu 12 saatte biter. Şifre sıfırlama bağlantısı bir saat geçerlidir, tek kullanımlıktır ve kullanıldığında açık oturumlar kapanır. Yanıt, e-postanın kayıtlı olup olmadığını söylemez; bağlantı yalnızca local ve test ortamında yanıtta döner.

Yazma istekleri `X-CSRF-Token` ister. Oturum `luminova_session` çerezindedir. OpenAPI, local ve test ortamında `/docs` altındadır. Production'da kapalıdır.

Henüz olmayanlar: profil ve şirket bilgisi düzenleme (`PATCH /api/v1/me`, `PATCH /api/v1/company`; ad, şirket adı ve saat dilimi şimdilik kayıtta belirlenir), e-posta gönderimi ve ödeme.

Liste endpoint'leri sayfalama, arama ve sıralama alır. Büyük tablo tek yanıtta dönmez.

## 7. Tasarım sistemi ve ekranlar

Renk ve yazı tokenları `frontend/src/styles/tokens.css` içindedir.

- Gece: `#10131C`
- Grafit: `#202432`
- Elektrik menekşe: `#7C5CFC`
- Lavanta: `#A78BFA`
- Bulut: `#F6F7FB`
- Arduvaz: `#687086`
- Başarı metni: `#166534`
- Uyarı metni: `#92400E`, vurgu `#D97706`
- Hata metni: `#B91C1C`, vurgu `#DC2626`

Wordmark Plus Jakarta Sans, büyük harf, `LUMINOVA`. Uzun metin ve tablolar Inter. Fontlar paketten gelir; tarayıcı Google'a istek atmaz.

Çalışma alanı açık zemindir. Tanıtım sayfası koyu zemin kullanır ve scroll ile dönüşen dört sahneden oluşur: hero, modüllerin birleşmesi, verinin panele dönüşmesi, kapanış çağrısı. Animasyon transform ve opacity ile gider, `prefers-reduced-motion` ayarına uyar, mobilde sadeleşir.

Ekranlar:

- `/` tanıtım
- `/kayit`, `/giris`, `/sifremi-unuttum`
- `/panel` genel bakış
- `/panel/raporlar`, `/panel/aktiviteler`, `/panel/profil`, `/panel/destek`
- Modül yolları: `/panel/satis`, `/panel/stok`, `/panel/uretim`, `/panel/musteriler`, `/panel/finans`, `/panel/gorevler`, `/panel/projeler`, `/panel/otomasyon`
- `/davet` ekip daveti kabulü
- `/yonetim` platform yönetimi (genel bakış, destek talepleri, şirketler ve kapatma talepleri)

Sol menünün üstünde Ana Sayfa ve Etkinlikler, ortasında etkin modüller, altında Destek ile Profil ve ayarlar durur. Panel, kaydı olmayan alanda sahte sayı göstermez.

## 8. Aşamalar ve bağımlılıklar

1. İnceleme. Tamamlandı.
2. Temel altyapı. Tamamlandı.
3. Tasarım sistemi ve tanıtım sayfası. Tamamlandı.
4. Üyelik, oturum, e-posta doğrulama, parola sıfırlama, şirket ve tenant testi. Tamamlandı.
5. Modül seçimi, kabuk, bildirim merkezi, profil, ekip ve roller, bildirim tercihleri. Tamamlandı; e-posta bildirimleri e-posta servisini bekliyor.
6. İş modülleri: müşteriler ve teklifler, stok, satış, görevler, projeler ve aşamalar, finans, üretim, raporlama, etkinlik akışı. Tamamlandı.
7. Destek ve yönetim paneli. Tamamlandı.
8. n8n sözleşmesi (imzalı webhook'lar) ve kurulum rehberi (`docs/n8n.md`). Tamamlandı; iş akışları n8n arayüzünde kurulur.
9. Test, yedekleme, ortam ayrımı ve yayına hazırlık (`docs/yayin.md`, `deploy/`). Tamamlandı; yayından önce açık kalanlar `docs/yayin.md` sonunda listelenir.

## 9. Paketler ve kurulum

Backend: FastAPI, Uvicorn, SQLAlchemy, Alembic, psycopg, Pydantic Settings, argon2-cffi, email-validator, httpx (webhook gönderimi); geliştirmede pytest.

Frontend: React, React Router, TypeScript, Vite, Tailwind CSS, Plus Jakarta Sans ve Inter font paketleri; denetim için oxlint. İkonlar ve grafikler elle yazılmış SVG'dir; animasyon kütüphanesi kullanılmaz.

Veritabanı: `postgres:16-alpine`. Canlı imajlar: `python:3.12-slim` (API ve işçi), `node:22-alpine` ile derlenip `nginx:1.27-alpine` ile sunulan arayüz.

Kurulum adımları kök `README.md`, canlı kurulum `docs/yayin.md` dosyasındadır.

## 10. Riskler ve dış yapılandırma

- Docker Desktop kapalıysa veritabanı ve API testleri çalışmaz.
- Python 3.14 yenidir. Kurulum, tekerlek bulunamazsa durur ve o zaman 3.12 ortamına geçilir.
- E-postalar n8n üzerinden SMTP ile gönderilir (`docs/n8n.md`). Yerelde SMTP olarak Mailpit kullanılır; canlı için gerçek bir SMTP hesabı henüz seçilmedi. `MAIL_WEBHOOK_URL` tanımlı değilse doğrulama kodu gönderilemez ve canlıda yeni hesap doğrulanamaz; servis yokken gönderilmiş gibi gösterilmez.
- Ödeme sağlayıcısı yoktur. Erişim `complimentary` durumudur.
- KVKK, gizlilik ve kullanım metinleri yayından önce hukuk incelemesi ister. Taslak metin hukuki yeterlilik iddiası taşımaz.
- Trendyol, N11 ve benzeri bağlantılar, gerçek API yetkisi doğrulanmadan yapılmaz.
- Yedekleme betikleri (`deploy/backup.sh`, `deploy/restore.sh`, `scripts/backup-local.ps1`) yerelde yedek alma ve ayrı veritabanına geri yükleme provasıyla denendi. Canlıda yedeklerin sunucu dışına kopyalanacağı depolama henüz seçilmedi.
- n8n ayrı bir süreçtir; iş akışları uygulamanın dışında, n8n arayüzünde yönetilir.

## İş kuralı kararları

Sipariş `fulfilled` olduğunda stok hareketi aynı transaction içinde yazılır. İptal, daha önce stok işlendiyse ters hareket üretir. Düşük stok, bakiye minimumun altına geçtiğinde tek bir bildirim anahtarıyla oluşur. Üretim tamamlanması eksik hammaddede durur.

Bütün otomatik işler backend'de, tetikleyen işlemle aynı transaction içinde çalışır; dış servis, e-posta veya n8n kullanılmaz. Her kural tekrar çalıştığında aynı kaydı ikinci kez üretmez.

**Stok ayırma.** Kullanılabilir stok = eldeki stok − ayrılan. Ayrılan miktar, onaylanmış ama stoğu düşülmemiş siparişlerin satırları ile planlanmış veya üretimdeki iş emirlerinin malzemeleridir. Üretimdeki miktar (açık iş emirlerinin çıktısı) ayrıca gösterilir. Teslim yalnızca eldeki stok yetmezse engellenir; ayrılan stok kullanılacaksa uyarı verilir.

**Satış kuralları** (şirket başına, `sales_rules`, yalnızca sahip ve yönetici değiştirir):
- Gelir kaydı: kapalı, onayda veya teslimde; isteğe bağlı vade günü. Sipariş başına tek aktif gelir kaydı (veritabanında tekil indeks).
- Onayda görev şablonu: şablon siparişe `order:<id>` hedef anahtarıyla bir kez uygulanır.
- Eksik stokta üretim: onayda eksik miktardan bu siparişe bağlı açık iş emirleri düşülür, kalan kadar iş emri açılır. Malzemeler reçeteden gelir; reçete yoksa yalnızca not düşülür.
- Sipariş iptalinde bekleyen gelir kaydı iptal edilir; ödenmiş kayda dokunulmaz, kullanıcıya iade notu gösterilir.
- Kuralların yaptığı her şey siparişin cevabında (`automation`) ve etkinlik akışında `order.rules_applied` olarak görünür.

**Reçeteler.** Bir birim ürün için malzeme miktarıdır. Döngü (ürünün kendi reçetesine dolaylı dönmesi) reddedilir. İş emrinde adet, paket ve kutu birimleri yukarı yuvarlanır.

**Yeniden sipariş önerisi.** Beklenen stok (eldeki − ayrılan + üretimdeki) minimumun altındaysa veya son 30 günlük çıkış hızıyla 14 günden az yetiyorsa öneri çıkar. Hedef, minimum ile 30 günlük tüketimin büyüğüdür. Reçetesi olan ürün için "üret", olmayan için "satın al" önerilir.

**Görev bağımlılıkları.** Önceki görevi bitmemiş görev başlatılamaz ve tamamlanamaz (409). Son önceki görev tamamlanınca bekleyen görev açılır ve `task.unblocked` kaydı yazılır. Döngü reddedilir.

**Proje takvimi.** Süresi olan görevler ileri hesaplanır: önceki görevlerin bitişinden sonraki gün, proje başlangıcından ve bugünden önce olmamak üzere başlar. Projede "yalnızca iş günleri" açıksa (`projects.working_days_only`, yeni projelerde varsayılan) cumartesi, pazar ve sabit tarihli resmî tatiller (1 Ocak, 23 Nisan, 1 Mayıs, 19 Mayıs, 15 Temmuz, 30 Ağustos, 29 Ekim) sayılmaz; dini bayramlar her yıl değiştiği için listede yoktur. Kapalıysa takvim günü kullanılır. Yeniden hesaplama önce önizlenir, onayla uygulanır. Bir aşamanın tüm görevleri bitince aşama kendiliğinden kapanır, görev yeniden açılırsa aşama da açılır. Riskler (teslimi aşan plan, plana göre geride kalma, geciken görev, darboğaz, sorumlusuz yakın görev, geciken aşama) nedenleriyle hesaplanır.

**Kısmi ödemeler.** Her finans kaydının ödemeleri `financial_payments` tablosundadır; `paid_amount`, durum (`pending`, `partial`, `paid`) ve ödeme tarihi her değişiklikte ödemelerden yeniden hesaplanır. Kalan tutardan fazla veya ileri tarihli ödeme reddedilir, tutar alınan ödemelerin altına düşürülemez. Açık alacak ve borç, vade hatırlatmaları, raporlar ve bakiyeler hep kalan tutarı kullanır.

**Tahmini kasa.** Sahip veya yönetici para birimi başına bir açılış bakiyesi girer (`cash_balances`, `PUT /api/v1/finance/opening-balance`; ileri tarih reddedilir). Bugünkü tahmini kasa, açılış bakiyesine o tarihten bugüne kadar alınan tahsilatların eklenip yapılan ödemelerin düşülmesiyle bulunur. Nakit akışı tablosu bu tutardan başlayıp gelecek haftaların vadesi gelen açık kayıtlarını ekleyerek hafta sonu tahmini kasayı gösterir. Gecikmiş kayıtlar tahmine katılmaz, ayrı gösterilir.

**Uyarılar ve otomatik görevler** (`app/services/insights.py`). Modüllerden sinyal toplanır; her sinyalin sabit bir anahtarı vardır. Açık otomatik görev anahtar başına tektir (`uq_tasks_open_source_key`). Kontrol, bildirim listesi çekildiğinde ve ana sayfa açıldığında en fazla 5 dakikada bir çalışır. Kimse oturum açmamışken de çalışması için `webhook-worker` her 5 dakikada bir zamanlanmış turu (`app/services/scheduler.py`) da yürütür: kurulumu bitmiş her etkin şirket için otomatik görevleri ve üyelerin teslim/vade hatırlatmalarını günceller. Bir şirketteki hata diğerlerini durdurmaz. Tur `python -m app.cli run-scheduled` ile elle de çalıştırılabilir. Sinyal kaybolan görev kendiliğinden tamamlanır; elle tamamlanan görev 3 gün yeniden açılmaz. Görev mümkünse kaydı oluşturana, değilse ayarlardaki kişiye veya şirket sahibine atanır. Otomatik görevler görev hatırlatması üretmez; kaynağın kendi hatırlatması yeterlidir. İsteğe bağlı "sahipsiz görevleri dağıt" ayarı, atanmamış açık görevleri en az açık işi olan üyeye verir.

**E-posta** (`app/services/mail.py`, tablo `email_messages`). Doğrulama, şifre sıfırlama, davet ve bildirim e-postaları iş kaydıyla aynı transaction içinde `queued` olarak yazılır; kanal (`MAIL_WEBHOOK_URL` + `MAIL_WEBHOOK_SECRET`) tanımlı değilse hiç yazılmaz. `webhook-worker` iletiyi `FOR UPDATE SKIP LOCKED` ile alır ve webhook'larla aynı HMAC biçimiyle imzalayıp n8n'e yollar. n8n yanıtında SMTP'nin `accepted`/`messageId` alanı varsa ileti `sent`, boş 2xx ise `handed_off` olur; ağ hatası ve 2xx dışı yanıt 5 kez artan aralıkla yeniden denenir, sonra `failed` olur. n8n sonucu sonradan imzalı `POST /api/v1/mail/callback` ile bildirebilir; sonuçlanmış ileti değişmez. Gövde tek kullanımlık bağlantı taşıdığı için gönderilince, diğer durumlarda 24 saat sonra silinir. Şifre sıfırlamada yanıt, hesabın var olup olmadığını belli etmez. Bildirim e-postası kullanıcının kategori bazlı `email` tercihiyle açılır; uygulama içi bildirim kapalı olsa bile e-posta gidebilir ve aynı `dedupe_key` için tek e-posta gider. Platform yönetimi kuyruğu `GET /api/v1/admin/mail` ile görür, başarısız ve içeriği silinmemiş iletiyi `POST /api/v1/admin/mail/{id}/retry` ile yeniden sıraya alır.

**Katılım kodu ve onay.** Her şirketin tekil bir katılım kodu vardır (`companies.join_code`, `XXXX-XXXX`, karışan harfler kullanılmaz); yöneticiler Ekip bölümünde görür, bağlantı olarak paylaşır (`/kayit?kod=`) ve `POST /api/v1/team/join-code` ile yeniler. Kayıt ekranında kişi yönetici mi üye mi olduğunu seçer: yönetici şirketini kurar (sektör ve ekip büyüklüğü isteğe bağlı), üye kodla kayıt olur (`POST /api/v1/auth/register/member`). E-posta doğrulaması 6 haneli kodla yapılır: kayıttan hemen sonra kod e-postayla gelir ve ekrandaki kutuya girilir (`POST /api/v1/auth/verify-code`); aynı e-postadaki bağlantı da çalışır. Kod 30 dakika geçerlidir, kod başına 5 hatalı deneme hakkı vardır; yeni kod (`/verify-code/resend`) dakikada bir, saatte en fazla 5 kez istenir ve öncekileri geçersiz kılar. Yanıtlar hesabın var olup olmadığını belli etmez. Girişte "doğrulamanız gerekiyor" uyarısı kod ekranına (`/dogrula?eposta=`) götürür. Üye hesabı e-posta doğrulanana kadar beklemede kalır; doğrulanınca yöneticilere bildirim gider. Yönetici isteği yetkileri seçerek onaylar veya reddeder (`/api/v1/team/join-requests/{id}/approve|reject`); karar kişiye e-postayla bildirilir. Onaydan önce girişte "yönetici onayını bekliyor", ret sonrasında "onaylanmadı" mesajı çıkar. Davetle katılma da çalışmaya devam eder.

**Platform yönetim hesabı.** `/yonetim` paneline şirketi olmayan bir yönetim hesabıyla girilir; hesap `python -m app.cli create-admin <giriş-adı>` ile oluşturulur ve şifre komut tarafından sorulur. Giriş adı e-posta olmak zorunda değildir. Canlı ortamda en az 12 karakterli, tahmin edilemeyen şifre şarttır; şifre kodda veya ortam dosyasında tutulmaz. Panel şirketleri, kullandıkları modülleri ve ekiplerini gösterir; modüllerin içindeki kayıtlar gösterilmez. Yönetim ekibi bir şirkete mesaj başlatabilir: mesaj, şirketin Destek sayfasında "LUMINOVA mesajı" türünde bir konuşma olarak açılır, sahip ve yöneticilere bildirim gider, onlar da yanıt yazar. Şirket silme (`DELETE /api/v1/admin/companies/{id}`, şirket adı birebir yazılarak) `company_id` taşıyan bütün tablolardaki kayıtları ve yalnızca o şirkete ait kullanıcı hesaplarını kalıcı olarak siler; işlem şirket dışı bir denetim kaydı bırakır. Yönetici profilindeki "Bize ulaşın" bölümü sorun, şikâyet ve öneri talebi açar.

**Üye yetkileri** (`app/services/permissions.py`, tablo `member_permissions`). Sahip ve yönetici açık modüllerin hepsinde tam yetkilidir. Üye (`member`) yalnızca kendisine verilen modülleri görür: `view` kayıtları okur, `edit` ekler ve değiştirir; satırı olmayan modüle erişemez. Yetki davette seçilir (`company_invitations.permissions`, kabulde uygulanır) ve sonradan `PUT /api/v1/team/members/{id}/permissions` ile değiştirilir; üyeye bildirim gider ve etkinlikte görünür. Bir modül başka bir modüle dayanıyorsa (Satış → Müşteriler ve Stok, Üretim → Stok, Projeler → Görevler) dayandığı modüller en az `view` ile eklenir. Otomasyonlar üyelere verilemez. Kontrol sunucudadır: `require_module` okuma isteklerinde `view`, diğer isteklerde `edit` arar. Modül listesi üyeye yalnızca erişebildiği modülleri açık döner (`access` alanıyla), böylece menü ve modüller arası bağlantılar kendiliğinden gizlenir. Ana sayfa uyarıları, raporlar, etkinlik akışı, hatırlatmalar, müşteri özeti ve haftalık özet `visible_keys` ile kişinin görebildiği modüllerle sınırlanır; göremediği modülden çıkan otomatik görevler, kendisine atanmadıkça görev listesinde görünmez. Satış kuralları, otomasyon olayları ve otomatik görev senkronu ise şirketin açık modüllerine göre çalışır (`enabled_keys`), kimin isteğiyle tetiklendiklerinden etkilenmez. Teklifi siparişe çevirmek Satış'ta düzenleme yetkisi de ister. Geçişte mevcut üyelere açık modüllerin hepsinde `edit` verildi.

**Müşteriye teklif.** Teklif gönderilirken rastgele bir bağlantı üretilir; tabloda yalnızca hash'i durur (`quotes.share_token_hash`) ve yeniden gönderme (`POST /api/v1/quotes/{id}/resend`) eski bağlantıyı geçersiz kılar. İstenirse müşterinin kayıtlı adresine teklif özeti ve bağlantı içeren e-posta sıraya alınır (`kind = quote`, `reply_to` = gönderen kullanıcı); adres yoksa veya e-posta kanalı kapalıysa bağlantı ekranda gösterilir ve elle iletilebilir. Bağlantı oturum istemeyen `/teklif/<belirteç>` sayfasını açar (`GET /api/v1/public/quotes/{token}`); müşteri isteğe bağlı notla kabul eder veya reddeder (`POST .../decision`). Karar yalnızca `sent` durumundaki ve süresi geçmemiş teklifte verilir, aynı kararın tekrarı sorun çıkarmaz, farklı karar 409 döner. Karar `decided_by = customer` ile yazılır, etkinlik akışında müşterinin adıyla görünür, `quote.status_changed` olayı çıkar ve sahip, yönetici ile teklifi hazırlayana "Teklifler" kategorisinde bildirim gider (bu kategoride e-posta yöneticilerde varsayılan açıktır). Ekip yine elle kabul veya ret işaretleyebilir.

**Stok seviyeleri.** Ürünün minimum stoku ve isteğe bağlı kritik stoku vardır (`products.critical_stock`; boşsa minimumun yarısı, minimumdan büyük olamaz). Stoğu değiştiren tek yol `post_stock_change` olduğu için satış, üretim ve elle hareketlerin hepsi aynı kurala girer: minimum eşiği geçilince "azaldı", kritik eşik geçilince "kritik" bildirimi hareketi yapana ve tüm sahip ile yöneticilere gider; aynı hareket iki eşiği birden geçerse yalnızca kritik uyarısı gider. Uyarı yalnızca eşik geçildiği anda verilir, stok tamamlanıp yeniden düşerse tekrarlanır. `stock.low` webhook olayı `level` (`low` veya `critical`) alanını taşır.

**Haftalık özet** (`app/services/digest.py`). Zamanlanmış tur, şirket saatine göre pazartesi 09:00'dan itibaren o haftanın özetini her üyeye bir kez sıraya alır (`email_messages.ref = digest:<pazartesi>`). İçerik açık modüllere ve role göre değişir: herkes kendi geciken ve bu hafta teslim olan görevlerini görür; sahip ve yönetici ayrıca geçen haftanın satışını ve tahsilatını, vadesi geçen alacakları, bu hafta ödenecek borçları, kritik ve minimumun altındaki ürünleri ve teslimi geçen projeleri görür. Bildirecek bir şeyi olmayan kişiye e-posta gitmez. İşçi pazartesi hiç çalışmazsa o haftanın özeti atlanır.

**E-posta tercihleri.** Kategori bazlı e-posta varsayılan olarak kapalıdır; istisnalar haftalık özet (herkeste açık) ve stok uyarılarıdır (sahip ve yöneticide açık). Haftalık özet yalnızca e-posta kanalındadır.

**Tema.** Renkler `styles/tokens.css` içindeki değişkenlerdir; `html.dark` bunları değiştirir. Yüzeyler `surface`, koyu düğme yazıları `onink`, kenar çubuğu ve koyu paneller `rail` kullanır. Seçim tarayıcıda saklanır, sayfa açılmadan önce uygulanır.

**Bağlantı alanları.** Proje ve iş emri güncellemelerinde teklif, sipariş ve proje bağlantıları istekte gönderilmezse korunur; açıkça `null` gönderilirse kaldırılır. Teklife veya siparişe bağlanan proje müşteriyi oradan alır; farklı müşteri 422 döner.
