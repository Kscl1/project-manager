---
title: Başlangıç
description: Çalışma sistemi paketini projene kur, ardından ajanınla birlikte projeye uyarla.
sidebar:
  order: 3
---

project-manager, görevlerini, kararlarını ve çalışma kurallarını kodunun yanında tutar. Böylece kodlama ajanın her oturumda aynı yöntemle plan yapar ve işini kontrol eder.

İki yoldan başlayabilirsin: terminalde adım adım ilerleyen **kurulum ekranı (TUI, önerilen yol)** veya aşağıdaki katmanları izleyerek **elle kurulum**. Her iki yolun sonunda da kendi projende `/pm-setup` çalıştırırsın; ajanın paketi seninle birlikte projeye uyarlar.

## Başlamadan önce

İnternet bağlantısı, **Python 3.11 veya üstü** ve **Git** gerekir. Kurulum ekranı, kendisini çalıştıran Python'u yükleyemez.

**Windows 11:** PowerShell'de [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) ile [Python Install Manager](https://docs.python.org/3/using/windows.html) ve [Git for Windows](https://git-scm.com/install/windows) yükle. Ardından yeni bir terminal aç ve Python'un kendisini `py` ile kur:

```powershell
winget install --id Python.PythonInstallManager --exact --source winget
winget install --id Git.Git --exact --source winget
py install 3.13
```

Eski kurucular (`Python.Python.3.11` gibi), Akıllı Uygulama Denetimi tarafından “Bad Image” hatasıyla (`0xc0e90002`) durdurulabilir; Install Manager bu soruna takılmaz.

**Omarchy ve diğer Arch tabanlı sistemler:** Python ve Git genellikle zaten vardır. `python --version` ve `git --version` ile kontrol et. Yoksa [pacman](https://man.archlinux.org/man/pacman.8.en) kullan:

```bash
sudo pacman -S --needed python git
```

Projen bir Git deposu olmalı. Yeni bir projeyse klasörünü oluşturup içinde `git init` çalıştır. Kurulumdan önce çalışmalarını commit et veya yedekle.

## Kurulum ekranını çalıştır

Projenin bulunduğu **üst klasörde** project-manager'ı klonla: kendi projenin içine değil, **yanına**. TUI için ayrı bir sanal ortam oluştur; bu klasör Python kitaplıklarını sistemin geri kalanından ayrı tutar:

```bash
git clone --branch v0.1.0-alpha.1 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

`--branch v0.1.0-alpha.1`, en yeni `main` yerine yayımlanmış sürümü indirir. Git'in “detached HEAD” mesajı vermesi normaldir: klon bir geliştirme dalında değil, sürüm etiketindedir. Yeni sürümler [Releases](https://github.com/Kscl1/project-manager/releases) sayfasında listelenir.

Ardından kitaplıkları yükle ve ekranı **kendi projenin klasör yoluyla** başlat. Örnek yolu kendi projeninkiyle değiştir.

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
| Check | Programları ve proje dosyalarını; kurulu, en düşük ve denenmiş sürümleri gösterir. Hiçbir şeyi değiştirmez. Yeniden çalıştırıldığında eksik yoksa `Enter` doğrudan Done'a geçer. | `Enter`: devam, `r`: yeniden kontrol, `c`: yol kopyala, `l`: yeniden kurulumda katmanları değiştir |
| Choose | Core her zaman açıktır. Şema istiyorsan Map'i, izlenebilir çalışan ajanlar istiyorsan Swarm'ı seç. Bu makinede gereken adımları listeler. | `Space`: seç, `Enter`: devam, `Esc`: geri |
| Install | Her seferinde tek adım. Önce komutu, proje adımında ayrıca kurucunun planını gösterir. | `y`: çalıştır, `s`: atla, `c`: kopyala, `r`: yeniden kontrol |
| Done | Nelerin hazır, nelerin eksik olduğunu ve projeyi nasıl açacağını gösterir. | `o`: Claude Desktop'ta aç (Windows), `c`: komutları kopyala |

Bir adımda `y` tuşuna basmadan hiçbir şey yüklenmez. Denenmiş sürümün üstünde bir sürüm **henüz denenmedi** demektir, bozuk demek değildir. Kurulum sana ait dosyaları yeniden yazmaz; yalnız `.gitignore` ve `.gitattributes` sonuna satır ekler. Projendeki `AGENTS.md`, Git hook'ları, `.claude/settings.json` ve `.mcp.json` korunur; `/pm-setup` sırasında seninle birleştirilecekler listelenir.

**Takıldın mı? `a` tuşuna bas.** Kodlama ajanına verebileceğin bir mesajı kopyalar; ajan kurulumu TUI olmadan tamamlayabilir. Kopyalama çalışmazsa ekrandaki metni seç. `python tools/setup/bom.py --project <klasör>` aynı kontrolü ve komutları yazdırır, hiçbir şey yüklemez.

Bir kurucu bitince çıktısını oku ve `Enter` ile geri dön. Program hâlâ bulunamıyorsa yeni bir terminal açıp kurulumu tekrar başlat. Linux'ta `sudo` parola isterken yazdıkların ekranda görünmez.

## Çekirdek katman (Core)

Her proje için gerekli parçalar. Elle kuruyorsan tabloyu sırayla izle.

| Araç | Ne işe yarar, nasıl kurulur? |
|---|---|
| [Node.js](https://nodejs.org/en/download) | Aşağıdaki JavaScript araçlarını çalıştırır. Windows: `winget install --id OpenJS.NodeJS.LTS --exact --source winget`. Omarchy: `omarchy install dev-env node`. |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | Görevlerini projede Markdown dosyaları olarak tutar. `npm i -g backlog.md@1.54.0`. npm `EACCES` hatası verirse [npm rehberini](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally) izle; komuta `sudo` ekleme. |
| [Claude Code](https://code.claude.com/docs/en/setup) | Kodlama ajanın. Windows PowerShell: `irm https://claude.ai/install.ps1 \| iex`. Linux: `curl -fsSL https://claude.ai/install.sh \| bash`. İkisi de `claude` komutunu ev klasöründeki `.local\bin` (`~/.local/bin`) içine koyar. Windows'ta bu klasör PATH'e eklenmez; TUI senin için kullanıcı PATH'ine ekler. Elle kuruyorsan `%USERPROFILE%\.local\bin` ekle, sonra yeni terminal aç. İlk çalıştırmada hesabına giriş yap. |
| `.pm` paketi | Kurallar, kararlar, kontroller ve `pm-` skill'leri: `pm-setup`, `pm-grilling`, `pm-grill-me`, `pm-scratch`, `pm-feedback`. |
| Oturum hook'ları | Oturum açılırken ve ajanın belleği özetlendikten sonra işin nerede kaldığını gösterir. |
| [Context7](https://github.com/upstash/context7) | Ajana güncel kitaplık belgeleri sağlar. Hesap gerekmez; ücretsiz anahtar yalnız istek sınırını yükseltir. |

Son üçü tek kurucu komutuyla gelir. Komutları project-manager klasöründe çalıştır; TUI bunları senin yerine yapar:

```bash
python template/.pm/tools/pm_init.py ../my-project --check
python template/.pm/tools/pm_init.py ../my-project
```

`--check`, yazılacakları gösterir ama hiçbir şey yazmaz. Projende zaten ajan talimatları, Backlog.md veya Git hook'ları varsa kurucu durur. `--keep-existing` ile yeniden çalıştırarak paketi kurabilir ve kendi dosyalarını koruyabilirsin. Aynı kurucuyu ikinci kez çalıştırmak bir şey değiştirmez.

## Harita katmanı (Map, isteğe bağlı)

[LikeC4](https://likec4.dev/tooling/cli/), mimari modelini gezilebilir şemalara dönüştürür: projenin içinde `npx likec4@1.60.0 start`. [MCP sunucusu](https://likec4.dev/tooling/mcp/) ajanın modeli okumasını sağlar. `pm-likec4-dsl` skill'i, LikeC4'ün v1.60.0 sürümünden alınmış sözdizimi rehberidir. TUI'de Map'i seç veya kurucu komutuna `--map` ekle. Projende zaten `.mcp.json` varsa sunucu dosyaya yazılmaz; `/pm-setup` ile eklenecekler arasında gösterilir.

## Sürü katmanı (Swarm, isteğe bağlı)

Sürü, yardımcı ajanları izleyebileceğin çalışanlar olarak başlatır. Her biri ayrı bir [Herdr](https://herdr.dev) panelinde çalışır; `.pm/swarm/pm_run.py` başlatır ve durumlarını denetler. Başlamak için gerekli değildir. TUI'de Swarm'ı seç (başlangıçta kapalıdır) veya kurucuya `--swarm` ekle. Gerekenler:

- [Pi](https://github.com/earendil-works/pi) ve `pi-mcp-adapter` (Context7 gibi proje MCP sunucuları için), `pi-web-access` (web araması ve sayfa okuma için) eklentileri. Pi projeye güvenmeni istediğinde onayladıktan sonra `.agents/skills/` içindeki `pm-` skill'lerini bulur; `/skill:pm-setup` gibi çağırabilirsin.
  npm bu araçlar kurulurken bağımlılıklarından kaynaklanan “high severity vulnerabilities” ve kurulum betiği uyarıları gösterebilir; kurulum devam eder.
  `pi-mcp-adapter`, Pi'nin yerleşik MCP desteğinin yerini alır. İlk açılışta yerleşik desteği kullanıcı ayarlarında kapatır (`pi config` ile geri açabilirsin) ve Claude Code'un da okuduğu proje `.mcp.json` dosyasını okur.
  MCP sunucuları yalnız izin verdiğinde başlar. Pi projeyi ilk açtığında her sunucu için “Allow project MCP server?” diye sorar. **Allow seç; yalnız Enter'a basmak Don't allow demektir.** Pi yanıtı o proje ve worktree'leri için hatırlar. İlk pm_run çalışanından önce kendi projende `pi` açıp bu izinleri bir kez ver; çalışan soruda takılmasın.
- Herdr: kendi kurucusu en yeni sürümü PATH'e koyar ve SHA-256 doğrulamasını yapar.

Hiçbir kontrolün göremediği iki adımı Done ekranı hatırlatır: terminalde bir kez `herdr` başlatıp açık bırak ve Pi'de modele giriş yap (`pi`, sonra `/login`; ChatGPT planıyla OpenAI, ardından Sign in with ChatGPT). `PM_RUN_HERDR` değişkenini yalnız `herdr` PATH'te değilse ayarla.

Herdr ilk açılışta hoş geldin ekranından sonra bulduğu ajanlara entegrasyon kurmayı önerir. pm_run bunlara ihtiyaç duymaz; `Esc` ile geçebilirsin. ChatGPT ile girişten sonra Pi, planın kullanamadığı bir modeli seçerse (`gpt-5.5`, hata 400) `/model` yaz, `openai/gpt-6.1-sol` seç ve sonraki oturumlar için `Ctrl+S` ile kaydet. pm_run çalışanları bundan etkilenmez; her iş kendi modelini belirtir.

Claude Code'da çalışan bir ajan, Claude Code'un kendi paketli skill'leri olmadan başlar (örneğin kendi görünmez yardımcısını açan `/code-review`). Senin Claude Code kurulumun değişmez. İzin istemeden hangi komutları çalıştırabileceği Claude Code ayarlarına bağlıdır; `git status` gibi salt okunur komutlar izin istemez. Çalışan izin istediğinde pm_run `WAITING` ve yanıt vermen gereken Herdr sekmesini gösterir.

## EVREN katmanı (isteğe bağlı)

[evren-bridge](https://github.com/Kscl1/evren-bridge), [EVREN](https://evren.ssyz.org.tr) modellerine Pi gibi OpenAI Chat Completions konuşan ajanlardan erişmek için yerel bir köprüdür; resmî EVREN projesi değildir. Yalnız kendi EVREN hesabın varsa TUI'de EVREN'i seç (başlangıçta kapalıdır). Kurulum, köprünün README'sini izleyerek depoyu `~/evren-bridge` içine klonlar ve tek bağımlılığı `rich` kitaplığını yükler; Omarchy'de Arch Python'u `pip install` kabul etmediği için pacman kullanır. Köprüyü aynı `python` ile başlat. Kontrol, klondaki sürüm etiketini okur; eski klon `git pull` ile güncellenir.

Kurulum EVREN API anahtarını istemez ve okumaz. Anahtarını [evren-bridge README'sindeki Quick start](https://github.com/Kscl1/evren-bridge#quick-start) bölümüne göre kendin yerleştir ([EVREN API keys](https://evren.ssyz.org.tr/api-keys)). `~/evren-bridge` içinde `python evren_bridge.py` çalıştırıp açık bırak. Ajanına `http://127.0.0.1:8787/v1` taban adresli, OpenAI uyumlu bir sağlayıcı ekle; README, Pi'nin `models.json` örneğini gösterir. Diğer katmanlar buna bağlı değildir. EVREN olmadan da kurulum çalışır; `~/evren-bridge` klasörünü silmek yalnız EVREN seçiliyken ilgili satırı eksik gösterir.

## Kurulumdan sonra: /pm-setup

Claude Code'da project-manager'ı değil, **kendi projeni** aç:

- **Windows:** Done ekranında `o` tuşuna bas veya [Claude Desktop](https://code.claude.com/docs/en/desktop-quickstart) açıp Code bölümünden proje klasörünü seç. Desktop ayrı kurulur ve Code sekmesi ücretli Claude planı ister; terminalden de çalışabilirsin. Desktop önce giriş isterse projeyi unutur: giriş yap, ardından yeniden `o` tuşuna bas.
- **Linux:** `cd ~/projects/my-project`, ardından `claude`.

`/pm-setup` yazıp Enter'a bas. Ajanın Backlog'da bir kurulum Epic'i açar (her soru için bir alt görev taşıyan üst görev). Mevcut ajan kuralları, Git hook'ları, CI, testler, görev listeleri, kurulumdan kalan birleştirmeler, projenin amacı ve elindeki modeller hakkında **bir seferde tek konu** sorar. Sen onaylamadan değişiklik yapmaz.

Sonunda araçların nasıl açıklanmasını istediğini sorar: **kısa ipuçları** (varsayılan), **birlikte deneyelim** veya **kapalı**. Bunu sohbette istediğin zaman değiştirebilirsin: “öğretmeyi bırak”, “Backlog'u zaten biliyorum” gibi.

## Bir şey bozulursa

`.pm` paketinin kendisiyle ilgili bir sorun için projende `/pm-feedback` çalıştır. Yalnız tanı bilgisi içeren bir rapor yazıp sana gösterir; ancak onayınla issue açar. Bunun için GitHub'ın `gh` CLI aracında giriş yapılmış olmalı. Skill'ler kurulmadan önce takıldıysan TUI'nin `a` tuşunu kullan.

**Windows, Akıllı Uygulama Denetimi.** Şu ana kadar yalnız Windows Sandbox'ta görüldü, gerçek bir bilgisayarda henüz görülmedi: açık olduğunda Git for Windows'un imzasız DLL'lerini engelleyerek `git` komutunu “Bad Image” hatasıyla (`0xc0e90002`) durdurabilir. Git kurucusu başarılı görünse bile kimlik bilgisi yardımcısı eksik kalabilir; `git clone`, tarayıcıda giriş ekranı açmak yerine terminalde GitHub kullanıcı adı ister. `git config --system credential.helper` ile kontrol et; `manager` yazmalıdır. Boşsa, Git yeniden çalışır hâle geldikten sonra bir kez yeniden kur: `winget install --id Git.Git --exact --source winget --force`. Akıllı Uygulama Denetimi bir Windows güvenlik ayarıdır (Windows Güvenliği, Uygulama ve tarayıcı denetimi); kapatıp kapatmamaya sen karar ver.
