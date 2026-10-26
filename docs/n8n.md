# n8n ile LUMINOVA otomasyonları

Bu rehber, LUMINOVA'nın imzalı webhook'larını ve e-posta gönderimini (bölüm 3) n8n'e nasıl bağlayacağınızı anlatır. Depoda hazır iş akışı (workflow JSON) yoktur; düğümleri n8n arayüzünde siz kurarsınız. Aşağıdaki kod parçaları yalnızca n8n'in **Code** düğümüne yapıştırılacak imza kontrolleridir.

Ön koşullar:

- Çalışma alanında **Otomasyonlar** modülü açık olmalı.
- Bağlantıları çalışma alanı sahibi veya yöneticisi oluşturur (`/panel/otomasyon`).
- Giden gönderimleri `webhook-worker` süreci yapar. Yerelde ayrı bir terminalde çalıştırın:

```powershell
cd backend
.venv\Scripts\python.exe -m app.cli webhook-worker
```

Tek seferlik deneme için `python -m app.cli deliver-webhooks` yeterlidir. Production'da bu süreç API'den ayrı, sürekli çalışan bir servis olarak kurulur.

## 1. LUMINOVA'dan n8n'e (giden webhook)

1. n8n'de yeni bir iş akışı açın ve **Webhook** düğümü ekleyin.
   - HTTP Method: `POST`
   - Path: ör. `luminova-siparis`
   - Respond: `Immediately` (LUMINOVA 2xx yanıtı bekler; 10 saniyede yanıt gelmezse yeniden dener)
   - Options bölümünden **Raw Body** seçeneğini açın. İmza ham gövde üzerinden hesaplanır; JSON'u yeniden yazdırırsanız imza tutmaz.
2. Webhook düğümünün **Production URL** adresini kopyalayın.
3. LUMINOVA'da **Otomasyonlar → Yeni bağlantı → Giden** seçin, adresi yapıştırın ve olayları işaretleyin (ör. `order.created`, `stock.low`).
4. Kaydettiğinizde gösterilen `whsec_...` anahtarını kopyalayın. Anahtar bir daha gösterilmez; kaybederseniz **Anahtarı yenile** ile yenisini alın.
5. n8n'de anahtarı bir **Credential** veya ortam değişkeni olarak saklayın (ör. `LUMINOVA_WEBHOOK_SECRET`). İş akışının içine düz metin olarak yazmayın.
6. Webhook düğümünden sonra bir **Code** düğümü ekleyip imzayı doğrulayın:

```javascript
// n8n Code düğümü, "Run Once for All Items"
// n8n'in crypto modülüne izin vermesi için NODE_FUNCTION_ALLOW_BUILTIN=crypto gerekir.
const crypto = require('crypto');

const item = $input.first();
const headers = item.json.headers;
const secret = $env.LUMINOVA_WEBHOOK_SECRET;
const timestamp = headers['x-luminova-timestamp'];
const given = headers['x-luminova-signature'] || '';
const raw = Buffer.from(item.binary.data.data, 'base64');

if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) {
  throw new Error('Zaman damgası 5 dakikadan eski');
}
const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(`${timestamp}.`).update(raw).digest('hex');
if (given.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expected))) {
  throw new Error('İmza doğrulanamadı');
}
return [{ json: JSON.parse(raw.toString('utf8')) }];
```

7. Sonraki düğümler doğrulanmış olayı kullanır: `{{$json.type}}`, `{{$json.data.number}}` gibi.
8. LUMINOVA'da **Deneme gönder** ile `ping` olayı yollayıp akışı test edin. Sonuç **Son gönderimler** tablosunda görünür.

Aynı olay iki kez gelebilir (ağ hatasında yeniden deneme). `X-Luminova-Delivery` başlığı her gönderim için sabittir; n8n'de bu değeri kaydedip ikinci kez işlemeyebilirsiniz.

### Olay gövdesi

```json
{
  "id": "olay-uuid",
  "type": "order.created",
  "occurred_at": "2026-10-23T14:05:00+00:00",
  "company": { "id": "şirket-uuid", "slug": "sh1ne" },
  "data": { "number": "SP-0003", "status": "draft", "total": "1200.00", "currency": "TRY", "customer_name": "Deniz Yapı" }
}
```

Başlıklar: `X-Luminova-Event`, `X-Luminova-Delivery`, `X-Luminova-Timestamp`, `X-Luminova-Signature`.

Olay türleri: `customer.created`, `order.created`, `order.status_changed`, `quote.status_changed`, `stock.low` (`data.level`: `low` minimumun altı, `critical` kritik seviye), `task.completed`, `finance.record_created`, `production.completed`. Deneme gönderimi `ping` türündedir.

Yeniden deneme aralıkları: 1 dk, 5 dk, 30 dk, 2 sa, 12 sa. Altıncı başarısız denemeden sonra gönderim "Başarısız" olur ve ekrandan elle yeniden denenebilir.

## 2. n8n'den LUMINOVA'ya (gelen webhook)

1. LUMINOVA'da **Yeni bağlantı → Gelen** seçin. Ekranda istek adresi (`POST https://alan-adiniz/api/v1/hooks/<bağlantı-id>`) ve anahtar gösterilir.
2. n8n'de isteği göndermeden önce bir **Code** düğümüyle gövdeyi ve imzayı hazırlayın:

```javascript
const crypto = require('crypto');

const secret = $env.LUMINOVA_INBOUND_SECRET;
const body = JSON.stringify({
  action: 'task.create',
  data: { title: `Web siparişini kontrol et: ${$json.orderNo}`, priority: 'high' },
});
const timestamp = Math.floor(Date.now() / 1000).toString();
const signature = 'sha256=' + crypto.createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
return [{ json: { body, timestamp, signature, delivery: `n8n-${$execution.id}` } }];
```

3. Ardından **HTTP Request** düğümü ekleyin:
   - Method: `POST`, URL: LUMINOVA'daki istek adresi
   - Body: `Raw`, Content Type `application/json`, gövde olarak `{{$json.body}}` (ifadeyi değiştirmeden; imza bu metin üzerinden hesaplandı)
   - Headers: `X-Luminova-Timestamp = {{$json.timestamp}}`, `X-Luminova-Signature = {{$json.signature}}`, `X-Luminova-Delivery = {{$json.delivery}}`

Desteklenen işlemler:

| action | data | Sonuç |
| --- | --- | --- |
| `task.create` | `title` (zorunlu), `description`, `due_date` (YYYY-AA-GG), `priority` (`low`, `normal`, `high`, `urgent`) | Görev açılır; etkinliklerde "Otomasyon görev ekledi" görünür. Görev modülü kapalıysa 403 döner. |
| `notification.create` | `title` (zorunlu), `body` | Sahip ve yöneticilere "Otomasyon" kategorisinde uygulama içi bildirim düşer. |

Yanıt kodları: 200 başarılı (`duplicate: true` aynı `X-Luminova-Delivery` ile ikinci istek), 401 imza veya zaman damgası hatası, 403 modül kapalı, 404 bağlantı yok veya duraklatılmış, 413 gövde 64 KB'tan büyük, 422 gövde geçersiz.

## 3. E-posta gönderimi (n8n + SMTP)

**Ne işe yarar?** LUMINOVA kendi başına SMTP'ye bağlanmaz. Gönderilmesi gereken her e-posta (kayıt doğrulama, şifre sıfırlama, ekip daveti ve kullanıcının açtığı bildirim e-postaları) önce `email_messages` tablosunda sıraya girer. `webhook-worker` iletiyi imzalayıp n8n'deki tek bir iş akışına yollar; o iş akışı e-postayı SMTP ile gönderir ve sonucu LUMINOVA'ya bildirir. Böylece SMTP hesabı, gönderen adres veya sağlayıcı değişse de LUMINOVA'da kod değişmez.

Durumlar: `queued` (sırada) → `handed_off` (n8n aldı, sonuç bekleniyor) → `sent` (SMTP sunucusu kabul etti) veya `failed`. n8n'e ulaşılamazsa veya 2xx dışı yanıt gelirse 1 dk, 5 dk, 30 dk, 2 sa ve 12 sa sonra yeniden denenir. Durumları **/yonetim → E-posta** ekranında, davetlerin durumunu **Profil → Ekip** bölümünde görürsünüz. İleti içeriği tek kullanımlık bağlantılar taşıdığı için gönderildiği anda, başarısız veya yanıtsız kalanlarda 24 saat sonra silinir; konu ve alıcı kalır.

### 3.1 Yerel deneme ortamı

Kök dizinde:

```powershell
docker compose --profile mail up -d
```

- n8n: `http://127.0.0.1:5679` (ilk açılışta yerel bir n8n sahibi hesabı oluşturun). Bu, LUMINOVA'ya ait `luminova-n8n` kapsayıcısıdır.
- Mailpit: `http://127.0.0.1:8025`. Yerelde gönderilen tüm e-postalar burada görünür, gerçek adreslere gitmez.
- İmza anahtarı `.env` içindeki `MAIL_WEBHOOK_SECRET` değeridir; docker compose bunu n8n'e `LUMINOVA_MAIL_SECRET` ortam değişkeni olarak verir. Anahtarı n8n'e elle yazmayın.

### 3.2 İş akışını kurun

n8n'de **Create workflow** ile yeni bir iş akışı açın, adını `LUMINOVA e-posta` koyun. Üç düğüm yeterlidir.

**1) Webhook düğümü**

- HTTP Method: `POST`
- Path: `luminova-mail`
- Authentication: `None` (doğrulamayı imza yapar)
- Respond: `When Last Node Finishes`
- Response Data: `First Entry JSON`
- Options → **Raw Body**: açık

"When Last Node Finishes" sayesinde n8n, LUMINOVA'ya ancak e-posta düğümü bitince yanıt verir. LUMINOVA bu yanıttaki `accepted` ve `messageId` alanlarını görünce iletiyi "gönderildi" yapar.

**2) Code düğümü** (adı: `İmzayı doğrula`, mod: Run Once for All Items)

```javascript
const crypto = require('crypto');

const item = $input.first();
const headers = item.json.headers;
const secret = $env.LUMINOVA_MAIL_SECRET;
const timestamp = headers['x-luminova-timestamp'];
const given = headers['x-luminova-signature'] || '';
const raw = Buffer.from(item.binary.data.data, 'base64');

if (headers['x-luminova-event'] !== 'mail.send') {
  throw new Error('Beklenmeyen olay türü');
}
if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) {
  throw new Error('Zaman damgası 5 dakikadan eski');
}
const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(`${timestamp}.`).update(raw).digest('hex');
if (given.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expected))) {
  throw new Error('İmza doğrulanamadı');
}
return [{ json: JSON.parse(raw.toString('utf8')) }];
```

İmza tutmazsa düğüm hata verir, n8n 500 döner ve e-posta gönderilmez.

**3) Send Email düğümü**

- Credential: yeni bir **SMTP** kimlik bilgisi. Yerelde: Host `mailpit`, Port `1025`, SSL/TLS kapalı, User `luminova`, Password `yerel` (Mailpit her kullanıcıyı kabul eder).
- From Email: `LUMINOVA <bildirim@luminova.local>`
- To Email: `{{ $json.to }}`
- Subject: `{{ $json.subject }}`
- Email Format: `Both`
- Text: `{{ $json.text }}`
- HTML: `{{ $json.html }}`
- Options → Append n8n Attribution: kapalı
- Options → Reply To: `{{ $json.reply_to || '' }}` (müşteriye giden teklif e-postasını yanıtlayan müşteri, teklifi gönderen kişiye yazar; diğer e-postalarda alan boştur)

Düğümleri Webhook → İmzayı doğrula → Send Email sırasıyla bağlayın, kaydedin ve iş akışını etkinleştirin (**Active** / **Publish**). Webhook düğümündeki **Production URL** şuna benzer: `http://127.0.0.1:5679/webhook/luminova-mail`.

### 3.3 LUMINOVA'yı bağlayın

1. `.env` içinde `MAIL_WEBHOOK_URL=http://127.0.0.1:5679/webhook/luminova-mail` yazın.
2. API'yi yeniden başlatın (ayarlar açılışta okunur) ve ayrı bir terminalde işçiyi çalıştırın: `.venv\Scripts\python.exe -m app.cli webhook-worker`.
3. Deneme: giriş ekranında **Şifremi unuttum** ile kayıtlı bir adrese bağlantı isteyin. Birkaç saniye içinde ileti Mailpit'te görünür, **/yonetim → E-posta** ekranında durumu "Gönderildi" olur.
4. **Profil → Bildirimler** bölümünde artık her kategori için e-posta anahtarı açılabilir.

### 3.4 İsteğe bağlı: hata sonucunu ayrıca bildirmek

SMTP hatasında n8n 500 döner ve LUMINOVA yeniden dener; çoğu durumda bu yeterlidir. Hatanın nedenini LUMINOVA'ya yazdırmak isterseniz:

1. Send Email düğümünün **Settings → On Error** ayarını `Continue (using error output)` yapın.
2. Hata çıkışına bir Code düğümü (`Sonucu imzala`) ekleyin:

```javascript
const crypto = require('crypto');

const secret = $env.LUMINOVA_MAIL_SECRET;
const original = $('İmzayı doğrula').first().json;
const reason = $json.error?.message ?? $json.error ?? 'SMTP hatası';
const body = JSON.stringify({ id: original.id, status: 'failed', error: String(reason).slice(0, 400) });
const timestamp = Math.floor(Date.now() / 1000).toString();
const signature = 'sha256=' + crypto.createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
return [{ json: { body, timestamp, signature } }];
```

3. Ardından **HTTP Request** düğümü: Method `POST`, URL `{{ $env.LUMINOVA_CALLBACK_URL }}`, Body `Raw` / `application/json` / `{{ $json.body }}`, Headers `X-Luminova-Timestamp = {{ $json.timestamp }}` ve `X-Luminova-Signature = {{ $json.signature }}`.

`POST /api/v1/mail/callback` gövdesi: `id` (LUMINOVA ileti kimliği), `status` (`sent` veya `failed`), isteğe bağlı `error` ve `message_id`. Yanıt kodları: 200 başarılı, 401 imza veya zaman damgası hatası, 404 ileti yok veya kanal kapalı, 422 gövde geçersiz. Sonuçlanmış (`sent`/`failed`) bir ileti sonradan değişmez.

### 3.5 n8n'e giden ileti

Başlıklar: `X-Luminova-Event: mail.send`, `X-Luminova-Delivery` (ileti kimliği), `X-Luminova-Timestamp`, `X-Luminova-Signature`.

```json
{
  "id": "ileti-uuid",
  "kind": "password_reset",
  "to": "ece@example.com",
  "reply_to": null,
  "subject": "Şifre sıfırlama bağlantınız",
  "text": "Düz metin gövde",
  "html": "<div>…</div>",
  "created_at": "2026-10-25T11:00:00+00:00"
}
```

`kind` değerleri: `verify_email`, `password_reset`, `invitation`, `notification`, `digest` (pazartesi 09:00 haftalık özeti), `quote` (müşteriye giden teklif; `reply_to` teklifi gönderen kullanıcının adresidir). Hepsi aynı iş akışından geçer; türe göre farklı bir şey yapmak isterseniz Send Email'den önce bir **Switch** düğümüyle `{{ $json.kind }}` değerine göre ayırabilirsiniz.

### 3.6 Yayında

- Send Email kimlik bilgisine gerçek SMTP sağlayıcınızı girin (kurumsal e-posta, Google Workspace uygulama şifresi, Brevo, Amazon SES vb.). Gönderen alan adı için SPF ve DKIM kayıtlarını sağlayıcının yönergesine göre ekleyin; yoksa iletiler istenmeyen klasörüne düşer.
- `MAIL_WEBHOOK_URL` ve `PUBLIC_APP_URL` `https` olmalı, `MAIL_WEBHOOK_SECRET` en az 32 karakter olmalı; API bu koşullar sağlanmazsa açılmaz.
- n8n'de `NODE_FUNCTION_ALLOW_BUILTIN=crypto`, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, `LUMINOVA_MAIL_SECRET` ve (3.4'ü kurduysanız) `LUMINOVA_CALLBACK_URL=https://alan-adiniz/api/v1/mail/callback` tanımlı olmalı.

## Güvenlik notları

- Anahtarlar veritabanında saklanmaz; `WEBHOOK_SECRET_KEY`, bağlantı kimliği ve sürüm numarasından türetilir. Bu yüzden production'da `WEBHOOK_SECRET_KEY` değerini değiştirmek tüm anahtarları geçersiz kılar.
- Production'da giden adresler `https` olmalı ve iç ağ adreslerine (127.0.0.1, 10.x, 192.168.x vb.) gönderim yapılmaz. Yerel ortamda `http://localhost:5678` gibi n8n adresleri kullanılabilir.
- Bir anahtarın sızdığını düşünüyorsanız **Anahtarı yenile** düğmesine basın; eski anahtar hemen geçersiz olur.
