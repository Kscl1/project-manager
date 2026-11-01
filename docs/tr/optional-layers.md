---
title: İsteğe bağlı katmanlar
description: Her katmanın ne eklediği, neye ihtiyaç duyduğu ve ne zaman ekleneceği.
---

Çekirdek katman (core layer) bir görevi planlamaya, yapmaya ve kontrol etmeye yeter. Bu üç katman daha fazlasını ekler. Her biri isteğe bağlıdır; geri kalanı yeniden kurmadan istediğin zaman birini ekleyebilirsin. Yeni kelimeler [sözlükte](glossary.md) açıklanır.

| Katman | Neyi ekler? | Neye ihtiyaç duyar? |
|---|---|---|
| [Map](#map-katmanı-isteğe-bağlı) | Ajanının okuyup güncel tutabildiği mimari şemalar | Node.js |
| [Swarm](#swarm-katmanı-isteğe-bağlı) | İzleyebildiğin terminal bölmelerinde çalışan yardımcı ajanlar | Pi ve Herdr |
| [EVREN](#evren-katmanı-isteğe-bağlı) | Yerel bir köprü üzerinden kendi EVREN modellerin | Bir EVREN hesabı |

Katmanı kurulum ekranında işaretle ya da kurucu komutuna `--map` / `--swarm` ekle. EVREN için kurucu bayrağı (flag) yoktur: adımı, kurulum ekranındaki kontrol listesinden gelir.

## Map katmanı (isteğe bağlı)

[LikeC4](https://likec4.dev/tooling/cli/), yazılım mimarinin modelini tarayıcıda gezebileceğin şemalara dönüştürür: proje klasöründe `npx likec4@1.60.0 start` komutuyla açılır. İlk harita önizlemesi, sabitlenmiş LikeC4 paketini indirebilir; ajanın bundan önce senden onay ister. [MCP sunucusu](https://likec4.dev/tooling/mcp/) (MCP server, Model Context Protocol üzerinden ajanının veri sorabildiği küçük sunucu) sayesinde ajanın bu modeli okur; `pm-likec4-dsl` becerisi (skill, LikeC4'ün kendi `likec4-dsl` becerisinin v1.60.0 sürümünden kopyalanmış hâli) ise ajana şema dilinin yazım kurallarını öğretir. Kurulum ekranında Map'i işaretle ya da kurucu komutuna `--map` ekle. Projede zaten bir `.mcp.json` dosyası varsa (örneğin daha önce yalnızca çekirdek katman kurulduysa), sunucu doğrudan dosyana yazılmaz; `/pm-setup` sırasında eklenmek üzere listelenir.

## Swarm katmanı (isteğe bağlı)

Swarm (sürü katmanı), yardımcı ajanları çalışırken izleyebileceğin işçi ajanlar (worker) olarak çalıştırır: her işçi kendi [Herdr](https://herdr.dev) bölmesinde açılır ve `.pm/swarm/pm_run.py` tarafından başlatılıp kontrol edilir. Başlamak için buna ihtiyacın yoktur. Kurulum ekranında Swarm'ı işaretle (başlangıçta işaretsiz gelir) ya da kurucu komutuna `--swarm` ekle. Gerekenler:

- [Pi](https://github.com/earendil-works/pi) ve onun `pi-mcp-adapter` (Context7 gibi proje MCP sunucularını Pi işçilerine bağlayan uzantı) ile `pi-web-access` (web araması ve sayfa okuma uzantısı) eklentileri. Pi sorduğunda projeye güvenirsen `.agents/skills/` içindeki `pm-` becerilerini bulur; bunları `/skill:pm-setup` şeklinde çağırabilirsin.
  Pi ve uzantıları kurulurken npm, bu paketlerin kendi bağımlılıklarından kaynaklanan "high severity vulnerabilities" ve kurulum betiği uyarıları gösterebilir; kurulum devam eder.
  `pi-mcp-adapter`, Pi'nin yerleşik MCP desteğinin yerini alır: ilk açılışta Pi kullanıcı ayarlarında yerleşik desteği kapatır (`pi config` ile geri açılır) ve Claude Code'un da okuduğu proje `.mcp.json` dosyasını okur.
  Projenin MCP sunucuları yalnızca sen izin verdikten sonra başlar. Pi projeyi ilk açtığında her sunucu için bir kez izin sorar ("Allow project MCP server?"); burada Allow seç, çünkü doğrudan Enter'a basmak Don't allow (izin verme) demektir. Pi bu yanıtı o proje ve onun çalışma ağaçları (git worktree, aynı deponun ayrı çalışma klasörleri) için hatırlar. İlk pm_run işçisini başlatmadan önce kendi projende `pi` komutunu bir kez açıp bu soruyu yanıtla ki hiçbir işçi bu soruda takılmasın.
- Herdr: kendi kurucusuyla kurulur; bu kurucu en yeni sürümü PATH içine ekler ve dosyanın SHA-256 özetini kontrol eder.

Otomatik kontrollerin göremediği iki adımı Done ekranı sana hatırlatır: bir terminalde `herdr` komutunu bir kez başlatıp açık bırak ve Pi içinde bir modele giriş yap (`pi`, ardından `/login`; ChatGPT planın varsa OpenAI'ı, sonra Sign in with ChatGPT seçeneğini seç). `PM_RUN_HERDR` değişkenini yalnızca `herdr` komutu PATH içinde değilse ayarla.

Herdr ilk açılışında bir karşılama ekranı, ardından bilgisayarda bulduğu ajanlar için entegrasyon kurmayı öneren bir "agent integrations" ekranı gösterir; pm_run bunlara ihtiyaç duymaz ve `Esc` ile geçebilirsin. ChatGPT ile giriş yaptıktan sonra Pi, ChatGPT planının kullanamadığı bir modeli seçebilir (`gpt-5.5`, hata 400): `/model` yaz, `openai/gpt-6.1-sol` modelini seç ve yeni oturumlarda kalıcı olması için `Ctrl+S` tuşlarına bas. pm_run işçileri bundan etkilenmez, çünkü her iş kendi modelini açıkça belirtir.

Claude Code içinde çalışan bir işçi, Claude Code'un kendi paket becerileri olmadan başlar (örneğin kendi gizli yardımcısını başlatan `/code-review`); senin normal Claude Code kurulumun ise değişmez. İşçinin sormadan hangi komutları çalıştırabileceği Claude Code ayarlarını izler: `git status` gibi salt okunur komutlar hiçbir zaman izin istemez. Bir işçi soru sorduğunda pm_run `WAITING` yazar ve yanıt vereceğin Herdr sekmesini gösterir.

## EVREN katmanı (isteğe bağlı)

[evren-bridge](https://github.com/Kscl1/evren-bridge), Pi gibi OpenAI Chat Completions konuşan ajanları [EVREN](https://evren.ssyz.org.tr) modellerine bağlayan yerel bir köprüdür; resmî bir EVREN projesi değildir. EVREN, bazı kullanıcıların zaten abonesi olduğu bir model servisidir. Kurulum ekranında EVREN seçeneğini (başlangıçta işaretsiz gelir) yalnızca kendi EVREN hesabın varsa işaretle. Kurulum, köprünün kendi README dosyasını izler: depoyu `~/evren-bridge` klasörüne klonlar ve tek bağımlılığı olan `rich` paketini kurar (Omarchy'de Arch'ın Python'u `pip install` komutunu reddettiği için pacman üzerinden yükler); köprüyü aynı `python` ile başlat. Kontrol adımı bu klondaki sürüm etiketini okur; eski bir klon varsa `git pull` ile güncellenir.

Kurulum senden hiçbir zaman EVREN API anahtarını istemez ve okumaz. Anahtarını [evren-bridge README](https://github.com/Kscl1/evren-bridge#quick-start) dosyasının Quick start bölümünde anlatıldığı gibi kendin yerleştir ([EVREN API keys](https://evren.ssyz.org.tr/api-keys) sayfasından alabilirsin), `~/evren-bridge` klasöründe `python evren_bridge.py` komutunu çalıştırıp açık bırak, ardından ajanına taban adresi (`base URL`) `http://127.0.0.1:8787/v1` olan OpenAI uyumlu bir sağlayıcı ekle; köprünün README dosyası Pi'nin `models.json` örneğini gösterir. Başka hiçbir parça buna bağımlı değildir: EVREN katmanı olmadan diğer ekranlar ve kurucu aynı şekilde çalışır; `~/evren-bridge` klasörünü silmek yalnızca EVREN işaretliyken ilgili satırı eksik gösterir.
