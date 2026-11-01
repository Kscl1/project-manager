---
title: İsteğe bağlı katmanlar
description: Her katmanın neyi eklediği, neye ihtiyaç duyduğu ve ne zaman eklendiği.
---

Çekirdek katman bir görevi planlamaya, yapmaya ve kontrol etmeye yeter. Bu üç katman daha fazlasını ekler. Hepsi isteğe bağlıdır; birini sonradan, geri kalanı yeniden kurmadan ekleyebilirsin.

| Katman | Neyi ekler? | Neye ihtiyaç duyar? |
|---|---|---|
| **Harita (Map)** | Ajanının okuyup güncel tutabildiği mimari şemaları | Node.js |
| **Sürü (Swarm)** | İzleyebildiğin terminal bölmelerinde çalışan yardımcı ajanlar | Pi ve Herdr |
| **EVREN** | Yerel bir köprü üzerinden kendi EVREN modellerin | Bir EVREN hesabı |

Katmanı kurulum ekranında işaretle ya da kurucu komutuna `--map` / `--swarm` ekle. EVREN'in kurucu bayrağı yoktur: adımı, kurulum ekranındaki kontrol listesinden gelir.

## Harita katmanı (Map, isteğe bağlı)

[LikeC4](https://likec4.dev/tooling/cli/), yazılım mimarinin modelini tarayıcıda gezebileceğin şemalara dönüştürür: proje klasöründe `npx likec4@1.60.0 start` komutuyla açılır. [MCP server](https://likec4.dev/tooling/mcp/) (Model Context Protocol: ajanının veri isteyebildiği küçük bir sunucu) ajanın bu modeli okumasını sağlar. `pm-likec4-dsl` becerisi ise (LikeC4'ün kendi `likec4-dsl` becerisinin v1.60.0 sürümünden kopyalanmış hâli) ajana bu şema dilinin yazım kurallarını öğretir. Kurulum ekranında Map'i işaretle ya da kurucu komutuna `--map` ekle. Projende zaten bir `.mcp.json` dosyası varsa (örneğin daha önce yalnızca çekirdek katmanı kurduysan), sunucu doğrudan dosyana yazılmaz; `/pm-setup` sırasında eklenmek üzere listelenir.

## Sürü katmanı (Swarm, isteğe bağlı)

Sürü (`swarm`), yardımcı ajanları çalışırken izleyebileceğin işçi ajanlar (`worker`) olarak çalıştırır. Her işçi kendi [Herdr](https://herdr.dev) bölmesinde (birden fazla terminali bir arada gösteren ekranda) açılır ve `.pm/swarm/pm_run.py` tarafından başlatılıp denetlenir. Başlamak için bu katmana ihtiyacın yoktur. Kurulum ekranında Swarm'ı işaretle (başlangıçta işaretsiz gelir) ya da kurucu komutuna `--swarm` ekle. Bu katman için gerekenler:

- [Pi](https://github.com/earendil-works/pi) ve onun `pi-mcp-adapter` (Context7 gibi proje MCP sunucularını Pi işçilerine bağlayan eklenti) ile `pi-web-access` (web araması ve sayfa okuma eklentisi) uzantıları. Pi ilk açılışta projeye güvenip güvenmediğini sorduğunda onay verirsen `.agents/skills/` içindeki `pm-` becerilerini bulur; bunları `/skill:pm-setup` şeklinde çağırabilirsin.
  Pi ve eklentileri kurulurken npm, bu paketlerin kendi bağımlılıklarından kaynaklanan "high severity vulnerabilities" ve kurulum betiği uyarıları gösterebilir; kurulum devam eder.
  `pi-mcp-adapter`, Pi'nin yerleşik MCP desteğinin yerini alır. İlk çalışmada Pi kullanıcı ayarlarında yerleşik desteği kapatır (`pi config` ile geri açılır) ve Claude Code'un da okuduğu proje `.mcp.json` dosyasını okur.
  Projenin MCP sunucuları yalnızca sen izin verdikten sonra başlar. Pi projeyi ilk açtığında her sunucu için bir kez izin sorar ("Allow project MCP server?"). Burada Allow seçeneğini seç, çünkü doğrudan Enter'a basmak Don't allow (izin verme) anlamına gelir. Pi bu yanıtı o proje ve onun çalışma ağaçları (`git worktree`, aynı deponun farklı bir iş için açılmış ayrı çalışma klasörleri) için hatırlar. İlk pm_run işçisini başlatmadan önce kendi projende `pi` komutunu bir kez açıp bu soruyu yanıtla ki hiçbir işçi ajan bu soruda takılıp beklemesin.
- Herdr: kendi kurucusuyla kurulur; bu kurucu en yeni sürümü `PATH` içine ekler ve dosyanın bozulmadığını `SHA-256` özetiyle doğrular.

Hiçbir otomatik kontrolün göremediği iki adımı Done ekranı sana hatırlatır: bir terminalde `herdr` komutunu bir kez başlatıp açık bırak ve Pi içinde bir modele giriş yap (`pi` çalıştır, ardından `/login` yaz; ChatGPT aboneliğin varsa OpenAI'ı, sonra Sign in with ChatGPT seçeneğini seç). `PM_RUN_HERDR` ortam değişkenini yalnızca `herdr` komutu `PATH` içinde değilse ayarla.

Herdr ilk açılışında bir karşılama ekranı, ardından bilgisayarda bulduğu ajanlar için entegrasyon kurmayı öneren bir "agent integrations" ekranı gösterir. pm_run bunlara ihtiyaç duymaz; `Esc` ile geçebilirsin. ChatGPT ile giriş yaptıktan sonra Pi, ChatGPT planının kullanamadığı bir modeli seçebilir (`gpt-5.5`, hata 400): `/model` yaz, `openai/gpt-6.1-sol` modelini seç ve yeni oturumlarda kalıcı olması için `Ctrl+S` tuşlarına bas. pm_run işçileri bundan etkilenmez, çünkü her görev kendi kullanacağı modeli açıkça belirtir.

Claude Code içinde çalışan bir işçi ajan, Claude Code'un kendi paket becerileri olmadan başlar (örneğin kendi gizli yardımcısını başlatan `/code-review`). Senin normal Claude Code kurulumun ise değişmez. İşçinin sana sormadan hangi komutları çalıştırabileceği Claude Code ayarlarına bağlıdır: `git status` gibi salt okunur komutlar hiçbir zaman izin istemez. Bir işçi ajan onay istediğinde pm_run durum olarak `WAITING` yazar ve yanıt vereceğin Herdr sekmesini gösterir.

## EVREN katmanı (isteğe bağlı)

[evren-bridge](https://github.com/Kscl1/evren-bridge), Pi gibi OpenAI Chat Completions (OpenAI'ın standart sohbet API formatı) konuşan ajanların [EVREN](https://evren.ssyz.org.tr) modellerine bağlanmasını sağlayan yerel bir köprüdür; resmî bir EVREN projesi değildir. EVREN, bazı kişilerin zaten ücret ödediği bir model servisidir. Kurulum ekranında EVREN seçeneğini (başlangıçta işaretsiz gelir) yalnızca kendi EVREN hesabın varsa işaretle. Kurulum, köprünün kendi README dosyasındaki adımları izler: depoyu `~/evren-bridge` klasörüne klonlar ve tek bağımlılığı olan `rich` paketini kurar (Omarchy'de Arch'ın Python'u doğrudan `pip install` çalıştırmayı reddettiği için pacman üzerinden yükler). Köprüyü aynı `python` ile başlat. Kontrol adımı bu klondaki sürüm etiketini okur; daha eski bir klon varsa `git pull` ile güncellenir.

Kurulum senden hiçbir zaman EVREN API anahtarını (kişisel servis erişim parolanı) istemez ve okumaz. Anahtarını [evren-bridge README](https://github.com/Kscl1/evren-bridge#quick-start) dosyasının Quick start bölümünde anlatıldığı gibi kendin yerleştir (anahtarı [EVREN API keys](https://evren.ssyz.org.tr/api-keys) sayfasından alabilirsin). Ardından `~/evren-bridge` klasöründe `python evren_bridge.py` komutunu çalıştırıp açık bırak ve ajanına taban adresi (`base URL`) `http://127.0.0.1:8787/v1` olan OpenAI uyumlu bir sağlayıcı ekle; köprünün README dosyası Pi için `models.json` örneğini gösterir. Başka hiçbir parça buna bağımlı değildir. EVREN katmanı olmadan da diğer ekranlar ve kurucu aynı şekilde çalışır; `~/evren-bridge` klasörünü silmek yalnızca EVREN işaretliyken ilgili satırı eksik gösterir.
