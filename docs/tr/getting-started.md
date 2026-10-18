---
title: Başlangıç
description: Çalışma sistemi paketini projene kur, ardından ajanınla birlikte projene uyarla.
sidebar:
  order: 3
---

project-manager; görevlerini (yapılacak iş kayıtlarını), karar kayıtlarını (teknik seçimlerin nedenlerini) ve çalışma kurallarını kodunun yanında tutar. Böylece kodlama ajanın (kod okuyup yazan yapay zekâ aracın) her oturumda (çalışma sohbetinde) işi aynı yöntemle planlar ve kontrol eder.

Kuruluma iki yoldan başlayabilirsin: terminalde adım adım yol gösteren **kurulum ekranı (TUI, yani metin tabanlı arayüz — önerilen yol)** ile ya da aşağıdaki katmanları sırayla **elle** kurarak. Hangi yolu seçersen seç, sonunda kendi projende `/pm-setup` komutunu çalıştırırsın ve ajanın paketi seninle birlikte projene uyarlar.

## Başlamadan önce

İnternet bağlantısı, **Python 3.11 veya daha yeni bir sürüm** ve **Git** gerekir. Kurulum ekranı (TUI), üzerinde çalıştığı Python'u kendi başına kuramaz.

**Windows 11:** PowerShell'de [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) kullanarak [Python Install Manager](https://docs.python.org/3/using/windows.html) ve [Git for Windows](https://git-scm.com/install/windows) araçlarını yükle. Ardından yeni bir terminal aç ve Python'un kendisini `py` komutuyla kur:

```powershell
winget install --id Python.PythonInstallManager --exact --source winget
winget install --id Git.Git --exact --source winget
py install 3.13
```

Eski kurucular (`Python.Python.3.11` vb.), Windows'un Akıllı Uygulama Denetimi (Smart App Control) tarafından "Bad Image" hatasıyla (`0xc0e90002`) durdurulabilir. Install Manager bu engele takılmaz.

**Omarchy ve diğer Arch tabanlı sistemler:** İkisi de çoğunlukla kurulu gelir; `python --version` ve `git --version` ile kontrol et. Kurulu değilse [pacman](https://man.archlinux.org/man/pacman.8.en) kullan:

```bash
sudo pacman -S --needed python git
```

Projen bir Git deposu olmalıdır. Yeni bir projeyse klasörünü oluştur ve içinde `git init` çalıştır. Kurulumdan önce mevcut çalışmalarını Git'e kaydet (`commit`) veya yedekle.

## Kurulum ekranını (TUI) çalıştır

Projenin bulunduğu üst klasörde, project-manager deposunu kendi projenin içine değil, **yanına** klonla. Ardından TUI için ayrı bir sanal ortam oluştur (Python kütüphanelerini sistemin geri kalanından ayrı tutan bir klasör):

```bash
git clone --branch v0.1.0-alpha.1 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

`--branch v0.1.0-alpha.1` seçeneği en son `main` dalını değil, yayımlanmış sürümü kurar. Git bu durumda "detached HEAD" uyarısı verir. Bu beklenen bir durumdur; klonun bir geliştirme dalı yerine sabit bir sürüm üzerinde durduğunu gösterir. Daha yeni sürümler [Releases](https://github.com/Kscl1/project-manager/releases) sayfasında listelenir.

Ardından gerekli kütüphaneleri yükle ve kurulum ekranını kendi proje klasörünle başlat.

Windows PowerShell:

```powershell
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/Scripts/python tools/setup/app.py "C:/projects/my-project"
```

Omarchy:

```bash
tools/setup/.venv/bin/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/bin/python tools/setup/app.py ~/projects/my-project
```

| Ekran | Ne olur? | Tuşlar |
|---|---|---|
| Check | Her programı ve proje dosyasını gösterir: kurulu, en düşük ve test edilmiş sürüm. Burada hiçbir şey değişmez. Tekrar çalıştırdığında eksik kalmamışsa `Enter` doğrudan Done ekranına geçer. | `Enter` devam eder, `r` tekrar kontrol eder, `c` yolu kopyalar, `l` tekrar çalıştırmada katmanları değiştirir |
| Choose | Core (çekirdek katman) her zaman açıktır; şemalar istiyorsan Map'i, izleyebileceğin işçi ajanlar (`worker`, tek bir alt işi yapan yardımcı ajan) istiyorsan Swarm'ı işaretle. Bu bilgisayarda gereken adımları listeler. | `Space` işaretler, `Enter` devam eder, `Esc` geri döner |
| Install | Her seferinde tek bir adım ilerler. Önce çalıştıracağı komutu gösterir; proje adımında kurucunun planını da gösterir. | `y` çalıştırır, `s` atlar, `c` kopyalar, `r` tekrar kontrol eder |
| Done | Nelerin hazır olduğunu, geriye ne kaldığını ve projeni nasıl açacağını gösterir. | `o` Claude Desktop'ı açar (Windows), `c` komutları kopyalar |

Bir adımda `y` tuşuna basana kadar hiçbir şey kurulmaz. Test edilmiş sürümün üzerindeki bir sürüm **henüz test edilmedi** demektir, bozuk demek değildir. Kurulum senin hiçbir dosyanı baştan yazmaz; yalnızca `.gitignore` ve `.gitattributes` dosyalarının sonuna satır ekler. Projende zaten kendi `AGENTS.md` dosyan (ajan çalışma kuralları), Git kancaların (`git hooks`, yani `commit` gibi işlemlerde otomatik çalışan betikler), `.claude/settings.json` veya `.mcp.json` (dış araç bağlantı ayarları) varsa bunlara dokunulmaz. Hepsi olduğu gibi korunur ve `/pm-setup` aşamasında seninle birlikte birleştirilmek üzere listelenir.

**Takıldın mı? `a` tuşuna bas.** Bu tuş, kodlama ajanına verebileceğin bir mesajı kopyalar; böylece ajan kurulumu TUI olmadan tamamlayabilir. Kopyalama çalışmazsa ekrandaki metni fareyle seç. `python tools/setup/bom.py --project <folder>` komutu da aynı kontrolü ve komutları ekrana yazdırır; hiçbir şey kurmaz.

Bir kurucu tamamlandığında çıktısını oku ve `Enter` ile geri dön. Kurulan program hâlâ bulunamıyorsa yeni bir terminal açıp kurulumu tekrar başlat. Linux'ta `sudo` parola isterken yazdığın karakterleri ekranda göstermez.

## Çekirdek katman (Core)

Her projenin ihtiyaç duyduğu temel katman. Elle kuruyorsan tabloyu yukarıdan aşağıya sırayla uygula.

| Araç | Ne işe yarar ve nasıl kurulur? |
|---|---|
| [Node.js](https://nodejs.org/en/download) | Aşağıdaki JavaScript araçlarını çalıştırır. Windows: `winget install --id OpenJS.NodeJS.LTS --exact --source winget`. Omarchy: `omarchy install dev-env node`. |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | Görevlerini projede Markdown dosyaları olarak ve bir kanban panosu (işleri Yapılacak, Yapılıyor, Bitti sütunlarında izleyen pano) düzeninde tutar. `npm i -g backlog.md@1.54.0`. npm `EACCES` yetki hatası verirse [npm's guide](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally) adımlarını izle; komutun başına `sudo` ekleme. |
| [Claude Code](https://code.claude.com/docs/en/setup) | Kodlama ajanın. Windows PowerShell: `irm https://claude.ai/install.ps1 \| iex`. Linux: `curl -fsSL https://claude.ai/install.sh \| bash`. İkisi de `claude` komutunu kullanıcı klasöründeki `.local\bin` (`~/.local/bin`) içine koyar. Windows'ta bu klasör `PATH`'e (sistemin komut aradığı klasör listesine) otomatik eklenmez. TUI bu klasörü kullanıcı `PATH` ayarına senin için ekler (elle kuruyorsan `%USERPROFILE%\.local\bin` yolunu ekle, ardından yeni bir terminal aç). `claude` komutunu ilk çalıştırdığında hesabına giriş yap. |
| `.pm` paketi | Kurallar, karar kayıtları, kontroller ve `pm-` becerileri (`skill`, ajana belirli bir işi nasıl yapacağını öğreten hazır komut paketleri: `pm-setup`, `pm-grilling`, `pm-grill-me`, `pm-scratch`, `pm-feedback`). |
| Oturum kancaları (`session hooks`) | Oturum başladığında ve ajanın sohbet belleği özetlendiğinde (`compacted`, uzun sohbet geçmişinin yer açmak için kısaltılması) işin nerede kaldığını ajana gösterir. |
| [Context7](https://github.com/upstash/context7) | Ajanına kütüphanelerin güncel belgelerini sağlar. Hesap açman gerekmez; ücretsiz anahtar yalnızca istek sınırını yükseltir. |

Son üç satırdaki bileşenler, project-manager klasöründen çalıştırılan tek bir komutla kurulur. TUI bu komutu senin yerine çalıştırır:

```bash
python template/.pm/tools/pm_init.py ../my-project --check
python template/.pm/tools/pm_init.py ../my-project
```

`--check` seçeneği yazacağı her şeyi listeler ama hiçbir dosya yazmaz. Projende zaten kendi ajan talimatların, Backlog.md veya Git kancaların varsa kurucu durur. Mevcut dosyalarını koruyarak kurmak için komutu `--keep-existing` ile tekrar çalıştır. Komutu ikinci kez çalıştırmak hiçbir şeyi değiştirmez.

## Harita katmanı (Map, isteğe bağlı)

[LikeC4](https://likec4.dev/tooling/cli/), yazılım mimarinin modelini tarayıcıda gezebileceğin şemalara dönüştürür: proje klasöründe `npx likec4@1.60.0 start` komutuyla açılır. [MCP server](https://likec4.dev/tooling/mcp/) (Model Context Protocol sunucusu; ajanın dış araçlardan veri okumasını sağlayan bağlantı servisi) ajanın bu modeli okumasını sağlar. `pm-likec4-dsl` becerisi ise (LikeC4'ün kendi `likec4-dsl` becerisinin v1.60.0 sürümünden kopyalanmış hâli) ajana bu şema dilinin yazım kurallarını öğretir. TUI'de Map'i işaretle ya da kurucu komutuna `--map` ekle. Projende zaten bir `.mcp.json` dosyası varsa (örneğin daha önce yalnızca çekirdek katmanı kurduysan), sunucu doğrudan dosyana yazılmaz; `/pm-setup` sırasında eklenmek üzere listelenir.

## Sürü katmanı (Swarm, isteğe bağlı)

Sürü (`swarm`), yardımcı ajanları çalışırken izleyebileceğin işçi ajanlar (`worker`) olarak çalıştırır. Her işçi kendi [Herdr](https://herdr.dev) bölmesinde (birden fazla terminali bir arada gösteren ekranda) açılır ve `.pm/swarm/pm_run.py` tarafından başlatılıp denetlenir. Başlamak için bu katmana ihtiyacın yoktur. TUI'de Swarm'ı işaretle (başlangıçta işaretsiz gelir) ya da kurucu komutuna `--swarm` ekle. Bu katman için gerekenler:

- [Pi](https://github.com/earendil-works/pi) ve onun `pi-mcp-adapter` (Context7 gibi proje MCP sunucularını Pi işçilerine bağlayan eklenti) ile `pi-web-access` (web araması ve sayfa okuma eklentisi) uzantıları. Pi ilk açılışta projeye güvenip güvenmediğini sorduğunda onay verirsen `.agents/skills/` içindeki `pm-` becerilerini bulur; bunları `/skill:pm-setup` şeklinde çağırabilirsin.
  Pi ve eklentileri kurulurken npm, bu paketlerin kendi bağımlılıklarından kaynaklanan "high severity vulnerabilities" ve kurulum betiği uyarıları gösterebilir; kurulum devam eder.
  `pi-mcp-adapter`, Pi'nin yerleşik MCP desteğinin yerini alır. İlk çalışmada Pi kullanıcı ayarlarında yerleşik desteği kapatır (`pi config` ile geri açılır) ve Claude Code'un da okuduğu proje `.mcp.json` dosyasını okur.
  Projenin MCP sunucuları yalnızca sen izin verdikten sonra başlar. Pi projeyi ilk açtığında her sunucu için bir kez izin sorar ("Allow project MCP server?"). Burada Allow seçeneğini seç, çünkü doğrudan Enter'a basmak Don't allow (izin verme) anlamına gelir. Pi bu yanıtı o proje ve onun çalışma ağaçları (`git worktree`, aynı deponun farklı bir iş için açılmış ayrı çalışma klasörleri) için hatırlar. İlk pm_run işçisini başlatmadan önce kendi projende `pi` komutunu bir kez açıp bu soruyu yanıtla ki hiçbir işçi ajan bu soruda takılıp beklemesin.
- Herdr: kendi kurucusuyla kurulur; bu kurucu en yeni sürümü `PATH` içine ekler ve dosyanın bozulmadığını `SHA-256` özetiyle doğrular.

Hiçbir otomatik kontrolün göremediği iki adımı Done ekranı sana hatırlatır: bir terminalde `herdr` komutunu bir kez başlatıp açık bırak ve Pi içinde bir modele giriş yap (`pi` çalıştır, ardından `/login` yaz; ChatGPT aboneliğin varsa OpenAI'ı, sonra Sign in with ChatGPT seçeneğini seç). `PM_RUN_HERDR` ortam değişkenini yalnızca `herdr` komutu `PATH` içinde değilse ayarla.

Herdr ilk açılışında bir karşılama ekranı, ardından bilgisayarda bulduğu ajanlar için entegrasyon kurmayı öneren bir "agent integrations" ekranı gösterir. pm_run bunlara ihtiyaç duymaz; `Esc` ile geçebilirsin. ChatGPT ile giriş yaptıktan sonra Pi, ChatGPT planının kullanamadığı bir modeli seçebilir (`gpt-5.5`, hata 400): `/model` yaz, `openai/gpt-6.1-sol` modelini seç ve yeni oturumlarda kalıcı olması için `Ctrl+S` tuşlarına bas. pm_run işçileri bundan etkilenmez, çünkü her görev kendi kullanacağı modeli açıkça belirtir.

Claude Code içinde çalışan bir işçi ajan, Claude Code'un kendi paket becerileri olmadan başlar (örneğin kendi gizli yardımcısını başlatan `/code-review`). Senin normal Claude Code kurulumun ise değişmez. İşçinin sana sormadan hangi komutları çalıştırabileceği Claude Code ayarlarına bağlıdır: `git status` gibi salt okunur komutlar hiçbir zaman izin istemez. Bir işçi ajan onay istediğinde pm_run durum olarak `WAITING` yazar ve yanıt vereceğin Herdr sekmesini gösterir.

## EVREN katmanı (isteğe bağlı)

[evren-bridge](https://github.com/Kscl1/evren-bridge), Pi gibi OpenAI Chat Completions (OpenAI'ın standart sohbet API formatı) konuşan ajanların [EVREN](https://evren.ssyz.org.tr) modellerine bağlanmasını sağlayan yerel bir köprüdür; resmî bir EVREN projesi değildir. TUI'de EVREN seçeneğini (başlangıçta işaretsiz gelir) yalnızca kendi EVREN hesabın varsa işaretle. Kurulum, köprünün kendi README dosyasındaki adımları izler: depoyu `~/evren-bridge` klasörüne klonlar ve tek bağımlılığı olan `rich` paketini kurar (Omarchy'de Arch'ın Python'u doğrudan `pip install` çalıştırmayı reddettiği için pacman üzerinden yükler). Köprüyü aynı `python` ile başlat. Kontrol adımı bu klondaki sürüm etiketini okur; daha eski bir klon varsa `git pull` ile güncellenir.

Kurulum senden hiçbir zaman EVREN API anahtarını (kişisel servis erişim parolanı) istemez ve okumaz. Anahtarını [evren-bridge README](https://github.com/Kscl1/evren-bridge#quick-start) dosyasının Quick start bölümünde anlatıldığı gibi kendin yerleştir (anahtarı [EVREN API keys](https://evren.ssyz.org.tr/api-keys) sayfasından alabilirsin). Ardından `~/evren-bridge` klasöründe `python evren_bridge.py` komutunu çalıştırıp açık bırak ve ajanına taban adresi (`base URL`) `http://127.0.0.1:8787/v1` olan OpenAI uyumlu bir sağlayıcı ekle; köprünün README dosyası Pi için `models.json` örneğini gösterir. Başka hiçbir parça buna bağımlı değildir. EVREN katmanı olmadan da diğer ekranlar ve kurucu aynı şekilde çalışır; `~/evren-bridge` klasörünü silmek yalnızca EVREN işaretliyken ilgili satırı eksik gösterir.

## Kurulumdan sonra: /pm-setup

Claude Code'da project-manager klasörünü değil, **kendi projeni** aç:

- **Windows:** Done ekranında `o` tuşuna bas ya da [Claude Desktop](https://code.claude.com/docs/en/desktop-quickstart) uygulamasını açıp Code sekmesinden proje klasörünü seç. Desktop ayrı kurulur ve Code sekmesi ücretli bir Claude planı gerektirir; terminal üzerinden de çalışabilirsin. Desktop önce giriş yapmanı isterse seçtiğin projeyi unutur: giriş yap, ardından tekrar `o` tuşuna bas.
- **Linux:** `cd ~/projects/my-project` komutunu, ardından `claude` komutunu çalıştır.

`/pm-setup` yazıp Enter'a bas. Ajanın Backlog içinde bir kurulum Epic'i (her soru için bir alt görev barındıran üst görev) açar ve konuları tek tek sorar: mevcut ajan kuralların, Git kancaların, CI (kod gönderildiğinde testleri otomatik çalıştıran sürekli entegrasyon akışı), testlerin, görev listelerin, kurulumun seninle birleştirmek üzere bıraktığı dosyalar, projenin amacı (proje tüzüğü / `charter`) ve elindeki yapay zekâ modelleri. Sen onay vermeden hiçbir şey değiştirilmez.

En sonda araçların sana nasıl açıklanmasını istediğini sorar: **kısa ipuçları** (varsayılan), **birlikte deneyelim** veya **kapalı**. Bunu sohbette istediğin zaman değiştirebilirsin ("öğretmeyi bırak", "Backlog'u zaten biliyorum").

## Bir şey bozulursa

`.pm` paketinin kendisiyle ilgili bir sorun yaşarsan projende `/pm-feedback` komutunu çalıştır. Bu komut yalnızca teşhis bilgisi içeren bir rapor hazırlar ve önce sana gösterir. Yalnızca sen onay verirsen GitHub üzerinde bir sorun kaydı (`issue`) açar; bunun için GitHub'ın `gh` komut satırı aracında (CLI) oturum açılmış olması gerekir. Kurulum henüz beceriler (`skill`) yüklenmeden önce hata verirse bunun yerine TUI'deki `a` tuşunu kullan.

**Windows, Akıllı Uygulama Denetimi (Smart App Control).** Şimdiye kadar gerçek bir bilgisayarda değil, yalnızca Windows Sandbox içinde görüldü: Akıllı Uygulama Denetimi açıkken Git for Windows'un imzasız DLL (kütüphane) dosyalarını engellediği için `git` komutu "Bad Image" hatasıyla (`0xc0e90002`) durur. Git kurucusu yine de kurulumun başarılı olduğunu söyler ama Git'i kimlik doğrulama yardımcısı (`credential helper`, tarayıcıda giriş penceresi açıp hesabı hatırlayan bileşen) olmadan bırakır. Bu yüzden `git clone` komutu giriş penceresi açmak yerine terminalde GitHub kullanıcı adı sorar. `git config --system credential.helper` komutuyla kontrol et (ekrana `manager` yazmalıdır). Hiçbir şey yazmıyorsa, Git tekrar çalışır duruma geldikten sonra Git'i bir kez yeniden kur: `winget install --id Git.Git --exact --source winget --force`. Akıllı Uygulama Denetimi bir Windows güvenlik ayarıdır (Windows Güvenliği, Uygulama ve tarayıcı denetimi); kapatıp kapatmamaya kendin karar ver.
