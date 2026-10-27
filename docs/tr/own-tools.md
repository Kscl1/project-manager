---
title: Kendi araçlarını işe yarar kıl
description: Zaten kullandığın MCP sunucularını, eklentileri, becerileri ve uygulamaları koru; lider ajana her birini ne zaman kullanacağını söyleyen bir kural ver.
---

Zaten kullandığın MCP sunucularını (`MCP server`, ajanın dış araçlara bağlanmasını sağlayan servisler), eklentileri (`plugin`), becerileri (`skill`, ajana belirli bir işi nasıl yapacağını öğreten komut paketleri) ve uygulamaları olduğu gibi koru. project-manager'ın bunları kendi içinde sunması veya sahiplenmesi gerekmez. Bir aracı kurmak onu yalnızca erişilebilir yapar; lider ajana (`lead`, işi yöneten ana kodlama ajanı) **onu ne zaman kullanacağını** söyleyen kısa bir kural ve gerçek bir duman testi (`smoke check`, aracın gerçekten çalıştığını doğrulayan küçük bir deneme) ise onu işe yarar kılar.

İşe `/pm-setup` (veya kendi ajanındaki karşılığı) ile başla. Bu komutun mevcut araçlar adımı yalnızca aşağıdaki örnekler için değil, her araç için çalışır. Araçları tek tek ele al; bir şey kurmadan, ayar değiştirmeden veya özel veri alabilecek bir servisi çağırmadan önce mutlaka izin iste.

## Başka bir katalog değil, küçük bir yöntem

Her araç için lider ajana kurulum `Epic`'i (alt görevleri barındıran üst görev) altında bir alt görev açtır ya da var olanı kullandır ve şunları kaydet:

1. **İşi ve tetikleyicisi.** Projedeki hangi soruyu yanıtlıyor? Lider ajan bu araca ne zaman başvurmalı, ne zaman başvurmamalı? "Her zaman bu aracı kullan" gibi genel ifadeler yerine somut bir durum seç.
2. **Zaten ne var?** Kimlik bilgisi depolarını (parola ve anahtar kasalarını) açmadan projenin ve ajanın mevcut kurulumunu incele. Araç yalnızca bu projede mi (`project-local`) yoksa kullanıcı genelinde mi (`user-global`) kurulu? Hangi ajan onu görebiliyor? Kurulum ekranının (`TUI`) `similar` listesi tam bir döküm değil, yalnızca bir başlangıç noktasıdır. Daha geniş kullanıcı ayarlarını taramadan önce izin iste.
3. **Bağlantı ve kapsam.** Aracı geliştiren yerin (üreticinin) resmî istemci (`client`) talimatlarını kullan. MCP ayarı seçilen istemcinin kendi yapılandırmasına, eklenti o istemcinin eklenti sistemine, beceri ise desteklenen beceri klasörüne konur; dış bir uygulama ise belgelenmiş bir devir adımıyla (`handoff`) dışarıda kalabilir. Bir aracı sırf `.pm` içine uydurmak için yeni bir MCP sarmalayıcısı (`wrapper`, aracı başka bir biçime sokan ara katman) icat etme.
4. **İzinler ve maliyet.** Bilgisayardan dışarı hangi verinin çıktığını, nelerin okunup yazılabildiğini, hangi hesap veya istek sınırının (`rate limit`) geçerli olduğunu ve yan etkileri (dış sistemde değişiklik yapan işlemleri) kimin onayladığını yaz. Soruyu yanıtlamaya yetecek en az yetkiyi (`least privilege`) kullan. Parola ve API anahtarlarını (`credentials`) üreticinin desteklediği güvenli depoda veya yerel ortam değişkenlerinde tut; bunları görevlere, belgelere, paylaşılan ayar dosyalarına ya da geri bildirim raporlarına asla yazma.
5. **Tek bir çakışma kararı.** Onlarınkini mi, bizimkini mi, yoksa ikisini birden mi tutacaksın? Hiçbir şeyi otomatik silme. İki kopya hem sohbet bağlamında (`context`) yer kaplar, hem bir servisi iki kez çağırabilir, hem de farklı izin ve ayarlara sahip olabilir; yani fazladan bir kopya kendiliğinden zararsız değildir. Belirli bir durum için tercih edilen yolu açıkça adlandır. İkinci bir görev veya sorun takip uygulaması, sessizce ikinci bir ana kayıt kaynağına (`authoritative tracker`) dönüşmemelidir.
6. **Duman testi ve yedek yol (`fallback`).** Doğrudan gerçek ajanın ve projenin içinden mevcut araçları listele ve incele; ardından yanıtı bilinen, düşük riskli ve onaylanmış tek bir sorgu çalıştır. Kullanılan tam aracı/komutu, kaynağı/sürümü, sonucu ve tarihi (gizli anahtarları ve özel içerikleri dışarıda bırakarak) kaydet. Yalnızca sürüm numarasına bakmak veya bir JSON dosyasında metin aramak uçtan uca bir kontrol değildir. "Yapılandırıldı ama test edilmedi" dürüst bir sonuçtur. Servis erişilemez olduğunda veya hata verdiğinde ne yapılacağını belirt; çalışmış gibi sessizce devam etme.
7. **Ulaşılabilir kıl.** Onay aldıktan sonra projenin kendi `AGENTS.md` dosyasındaki (veya mevcut karşılığındaki) "Hangi araç ne zaman" ("Which tool when") tablosuna bir satır ekle. Satırda bu tablonun üç hücresi korunur: **Situation** (Durum), **Do** (Ne yapılacağı: araç, sınırı ve yedek yolu) ve **Why** (Neden: beklenen sonuç). Uzun kurulum adımlarını buraya kopyalamak yerine bağlantı ver. Duman testi kanıtını ikinci bir canlı durum sayfasına değil, doğrudan ilgili göreve kaydet.

İşe yarar bir satır, oturum başında hızlıca okunabilecek kadar kısadır:

| Situation | Do | Why |
|---|---|---|
| Kurulu sürüm için güncel kütüphane/API kurulum bilgisi gerektiğinde | Bu ajanın MCP bağlantısı üzerinden Context7 kullan. Sorgularda özel kod veya gizli anahtar gönderme; servis çalışmıyorsa resmî belgelere bak ve bunu belirt | Kütüphane kimliği (ID), sürüme duyarlı belgeler ve kaynak bağlantıları |
| Mimari modelde zaten var olan ilişkileri izlemek gerektiğinde | Salt okunur olarak LikeC4 MCP kullan. Kodun modelle birebir uyduğunun kanıtı değildir; gerçek davranış için kaynak kodu ve testleri incele | Hedeflenen projeden öğe/yol/görünüm (`element/path/view`) referansları |
| Dış bir uygulamada onaylanmış bir işlem gerektiğinde | Kullanıcının mevcut uygulamasını/eklentisini kullan. Açık onay olmadan gönderim, yayımlama veya yazma işlemi yapma; erişilemezse işi kullanıcıya elle devret | Görev içinde bir bağlantı veya sınırları belli bir sonuç |

Bunlar varsayılan ek araçlar değil, kendi projene uyarlayabileceğin örneklerdir. Tablo yalnızca hangi durumda hangi araca gidileceğini gösterir; kurulum komutları aracın kendi resmî belgelerine, doğrulama kanıtları ise kurulum görevine aittir. İsteğe bağlı bir aracın o an çalışmaması, ondan bağımsız işleri durdurmamalıdır.

## Yapılandırma nereye konur?

- Proje içindeki `.mcp.json` dosyasını destekleyen bir istemci için `mcpServers` altına yalnızca eklemek istediğin kaydı birleştir. Diğer tüm anahtarları olduğu gibi koru. Mevcut `.mcp.json` dosyaları `pm_init` tarafından hiçbir zaman baştan yazılmaz; kurucu, eksik kayıtları senin incelemen için `.pm/local/merge-by-hand.md` dosyasında listeler.
- İstemcilerin desteği birbirinden farklıdır. Başka bir kodlama ajanının `.mcp.json` dosyasını okuduğunu, Claude eklentilerini yüklediğini ya da aynı becerileri bulduğunu varsayma. O ajanın kendi resmî talimatlarını izle; bir istemcinin genel (`global`) ayar dosyasını deponun içine kopyalama. Bir işçi ajanın (`worker`, tek bir alt işi yapan yardımcı ajan) bu araca ihtiyacı olacaksa, o işçinin çalıştığı istemcideki bağlantıyı ve güven onaylarını da ayrıca kontrol et. Lider ajanın araca erişebilmesi, işçi ajanın da erişebildiği anlamına gelmez.
- Kendi becerilerini paketle gelen `pm-*` isimlerinin dışında tut. Paketle gelen bu beceriler `pm_init.py --upgrade` çalıştırıldığında yenilenir; orada yaptığın özel değişiklikler için yedekleme ve yeniden uygulama planı gerekir. Bir eklenti kendi içinde kancalar (`hooks`), beceriler ve sunucular barındırabilir: ikinci bir kopyayı etkinleştirmeden önce neleri eklediğini incele.
- Bulut tabanlı bir uygulamanın mutlaka bir ajan aracı olması gerekmez. Kullanıcının ne sağlayacağını (örneğin herkese açık bir bağlantı veya gizli kısımları temizlenmiş bir dışa aktarım), Backlog görevine hangi sonucun döneceğini ve asıl kaydın nerede yaşayacağını tanımla. Özel kayıtları kopyalamak yerine bağlantı ver.
- Bir değişiklik yapmadan önce mevcut yapılandırmayı özel olarak yedekle, en küçük kod farkını (`diff`) göster, onay al ve yazım kurallarını (`syntax`) doğrula. Yalnızca istemci gerektiriyorsa yeniden başlat veya yeniden bağlan. Kontrol başarısız olursa yalnızca o kaydı, eklentiyi veya sürümü eski hâline döndürüp kontrolü tekrarla; ilgisiz sunucuları silme veya tüm projeyi sıfırlama.

## Test edilmiş örnek: Context7

**Ne katar:** Özellikle modelin eğitimden hatırladığı API bilgisi yanlış veya eski olabileceğinde, güncel kütüphane ve API belgelerini getirir. Kodunu test etmez ve kütüphanenin kendi sürüm notlarının yerini tutmaz.

**Resmî kurulum:** [Context7 README](https://github.com/upstash/context7#readme) ve [istemciye özel talimatlar](https://context7.com/docs/resources/all-clients). Paketin çekirdek şablonu aşağıdaki uzak uç noktayı (`endpoint`) zaten içerir. Bu biçimi destekleyen istemciler için gizli bilgi içermeyen bir proje ayarıdır; tüm dosyanın üzerine yazmak yerine mevcut dosyanla birleştir:

```json
{
  "mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

Bağlantın bir anahtar veya hesap gerektiriyorsa üreticinin güncel kimlik doğrulama talimatlarını kullan; anahtarı bu paylaşılan örneğin içine asla yapıştırma. Üretici şu anda bir komut satırı (`CLI`) / beceri (`skill`) yolu da sunuyor. Bir neden olmadan ikisini birden kurmak yerine tercih ettiğin tek bir yolu seç.

**İş akışı kuralı:** Bir kütüphane sorusunda önce tam kütüphaneyi çözümle, ardından gerekli kavramı ve sürümü sor. Dönen belgeleri kaynak bağlantılarıyla birlikte kullan. Projenin gerçekten kullandığı sürümle karşılaştır; sırf ilk sırada çıktı diye en yeni API'yi benimseme. Bir araç kataloğu veya bağlantı ön eki (`transport prefix`) çağrı adlarını değiştirebilir; bu yüzden belirli bir bağdaştırıcıya (`adapter`) özgü adı ezbere yazmak yerine istemcinin sunduğu araçları incele.

**Duman testi:** Herkese açık bir kütüphane için önce `resolve-library-id` çağrısını yap, ardından dönen kimliği (ID) ve odaklı bir belge sorusunu kullanarak `query-docs` çağrısını çalıştır. Yanıtın ilgili resmî kaynakları içerdiğini kontrol et. Özel gereksinimleri ve proje kodunu isteğin dışında tut.

**Kanıt (2026-10-18):** Bir geliştirici, mevcut bir MCP bağlantısı üzerinden her iki çağrıyı kullanarak Renovate regex-manager ve custom-datasource belgelerini ana kaynak (`upstream`) bağlantılarıyla birlikte çekti. Bu deneme sıfırdan kurulumu, her istemciyi veya kimlik doğrulamalı/özel kütüphane erişimini değil, o bağlantı üzerindeki iş akışını doğrular. İstek sınırına (`rate limit`) takılırsa veya servis çalışmıyorsa doğrudan kütüphanenin resmî belgelerine başvur ve yedek yolu (`fallback`) kullandığını belirt.

## Test edilmiş örnek: LikeC4

**Ne katar:** Mevcut bir mimari model üzerinde sorgular çalıştırır. MCP sunucusu modelle ilgili soruları yanıtlar; DSL (şema yazım dili) becerisi ise yazım kurallarını öğretir. İkisi de kodun gerçekte nasıl çalıştığını kanıtlamaz.

**Resmî kurulum:** [LikeC4 MCP ve becerileri](https://likec4.dev/tooling/mcp/). Paketin Harita (`Map`) katmanını seçtiysen ikinci bir kopya eklemek yerine önce onun oluşturduğu sunucu kaydını veya elle birleştirme listesini (`merge-by-hand.md`) kullan. Zaten var olan kişisel bir sunucu ya da editör sunucusu için, çalışma alanının (`workspace`) sunucunun rastgele başladığı klasörü değil, **bu projenin modelini** gösterdiğini doğrula: LikeC4 MCP sunucusu `LIKEC4_WORKSPACE` ortam değişkenini okur, bulamazsa içinde bulunduğu klasörü kullanır. Bir çakışma kararı vermeden `pm-likec4-dsl` üzerine ikinci bir DSL becerisi kurma.

**İş akışı kuralı:** Bir bileşenin neye bağlandığını sorarken hedeflenen LikeC4 projesini seç, ilgili model öğesini ve ilişkilerini incele ve model kaynağını belirt. Şema yazımını düzenlerken DSL becerisini kullan ve kullandığın sürümün seçtiği CLI sürümüyle doğrula; programın gerçekte ne yaptığını sorarken ise kodu ve testleri incele.

**Duman testi:** Mevcut projeleri listele (`list-projects` birden fazla proje döndürebilir), beklenen proje kimliğinin (ID) listede olduğunu doğrula, ardından özetini veya bilinen bir öğesini oku. Sunucu başka bir çalışma alanını gösteriyorsa mevcut mimariyi oradan çıkarmaya çalışma. Üreticinin talimatlarına göre çalışma alanını düzelt ve kontrolü tekrarla.

**Kanıt (2026-10-18):** Bir geliştirici mevcut bir MCP bağlantısı üzerinden `list-projects` çağrısını başarıyla çalıştırdı ve dönen proje/çalışma alanı bilgilerini kontrol etti. Bu yalnızca keşif amaçlı bir duman testidir; sıfırdan kurulum, model doğrulama veya şema çizim (`rendering`) testi değildir. İstemciye özel ayarların ve kullanıcının kendi çalışma alanının yine ayrıca kontrol edilmesi gerekir.

## Körü körüne kurmak değil, kurulum talimatlarını bulmak

2026-10-18 tarihinde yapılan kısa bir kaynak taramasında mevcut keşif ve kurulum kaynakları incelendi:

- [Resmî MCP Kayıt Defteri (Official MCP Registry)](https://registry.modelcontextprotocol.io/) ([kapsam ve durum](https://github.com/modelcontextprotocol/registry#readme)): sunucu üst verisi (`metadata`) ve keşif sağlar; projene özel bir güven onayı değildir.
- [Claude Code eklenti keşfi](https://code.claude.com/docs/en/discover-plugins): bir istemcinin eklenti kurulum ve yönetim rehberidir; eklentinin senin iş akışına uygun olduğunun garantisi değildir.
- [Agent Skills dizini](https://www.skills.sh/): beceri keşif rehberidir. Kullanmaya başlamadan önce ana kaynağı (`upstream`), lisansı ve sürüm sabitlemesini (`pin`, belirli bir sürüm veya commit'e kilitlemeyi) incele; bir becerinin listede yer alması güvenlik denetiminden geçtiği anlamına gelmez.

Burada ayrı ve geniş bir kurulum kataloğu tutmak yerine bu kaynakları kullan. Bu rehberin doldurduğu projeye özel boşluk; **bir aracın ne zaman kullanılacağı, mevcut yollardan hangisinin seçileceği ve aracın işe yaradığının nasıl kontrol edileceğidir**. Bu sınırlı bir taramaydı; başka hiçbir kaynağın bu boşluğu ele almadığının kanıtı değildir.

Burada yer almayan bir araç için de aynı yedi adımı uygula ve gerçek bir deneme yapılana kadar "test edilmedi" ("not tested") olarak kaydet. `/pm-feedback` üzerinden veya katkı yoluyla yeni bir örnek önerirken yalnızca resmî bağlantıları, küçük ve tekrarlanabilir bir kontrolü, çakışma/izin sınırlarını paylaş; hiçbir özel yapılandırma ekleme. Bir aracı kurmuş olmak; ona kendi başına yayın yapma, mesaj gönderme, görev takipçini değiştirme veya yardımcı ajanlar başlatma izni vermez.
