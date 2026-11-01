---
title: Başlangıç
description: Çalışma sistemi paketini projene kur, ardından ajanınla birlikte projene uyarla.
---

project-manager; görevlerini (yapılacak iş kayıtlarını), karar kayıtlarını (teknik seçimlerin nedenlerini) ve çalışma kurallarını kodunun yanında tutar. Böylece kodlama ajanın (kod okuyup yazan yapay zekâ aracın) her oturumda (çalışma sohbetinde) işi aynı yöntemle planlar ve kontrol eder.

Kuruluma üç yoldan başlayabilirsin: kurulumu **kodlama ajanına** yaptırarak ([Ajanınla kur](install-with-agent.md): tek bir prompt yapıştırır, sorularını cevaplarsın), terminalde adım adım yol gösteren **kurulum ekranı (TUI, yani metin tabanlı arayüz)** ile ya da aşağıdaki katmanları sırayla **elle** kurarak. Hangi yolu seçersen seç, sonunda kendi projende `/pm-setup` komutunu çalıştırırsın ve ajanın paketi seninle birlikte projene uyarlar. Commit, beceri (skill) ya da katman gibi kelimeler [sözlükte](glossary.md).

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
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

`--branch v0.1.0-alpha.6` seçeneği en son `main` dalını değil, yayımlanmış sürümü kurar. Git bu durumda "detached HEAD" uyarısı verir. Bu beklenen bir durumdur; klonun bir geliştirme dalı yerine sabit bir sürüm üzerinde durduğunu gösterir. Daha yeni sürümler [Releases](https://github.com/Kscl1/project-manager/releases) sayfasında listelenir.

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
| Choose | Core (çekirdek katman) her zaman açıktır; şemalar istiyorsan Map'i, izleyebileceğin işçi ajanlar (`worker`, tek bir alt işi yapan yardımcı ajan) istiyorsan Swarm'ı, yalnızca EVREN hesabın varsa EVREN'i işaretle. Bu bilgisayarda gereken adımları listeler. | `Space` işaretler, `Enter` devam eder, `Esc` geri döner |
| Install | Her seferinde tek bir adım ilerler. Önce çalıştıracağı komutu gösterir; proje adımında kurucunun planını da gösterir. | `y` çalıştırır, `s` atlar, `c` kopyalar, `r` tekrar kontrol eder |
| Done | Nelerin hazır olduğunu, geriye ne kaldığını ve projeni nasıl açacağını gösterir. | `o` Claude Desktop'ı açar (Windows), `c` komutları kopyalar |

Bir adımda `y` tuşuna basana kadar hiçbir şey kurulmaz. Test edilmiş sürümün üzerindeki bir sürüm **henüz test edilmedi** demektir, bozuk demek değildir. Kurulum senin hiçbir dosyanı baştan yazmaz; yalnızca `.gitignore`, `.gitattributes` ve `.ignore` dosyalarının sonuna satır ekler (sonuncusu, ripgrep gibi arama araçlarının gizli `.pm/` klasörüne de bakmasını sağlar). Projende zaten kendi `AGENTS.md` dosyan (ajan çalışma kuralları), Git kancaların (`git hooks`, yani `commit` gibi işlemlerde otomatik çalışan betikler), `.claude/settings.json` veya `.mcp.json` (dış araç bağlantı ayarları) varsa bunlara dokunulmaz. Hepsi olduğu gibi korunur ve `/pm-setup` aşamasında seninle birlikte birleştirilmek üzere listelenir.

**Takıldın mı? `a` tuşuna bas.** Bu tuş, kodlama ajanına verebileceğin bir mesajı kopyalar; böylece ajan kurulumu TUI olmadan tamamlayabilir. Kopyalama çalışmazsa ekrandaki metni fareyle seç. `python tools/setup/bom.py --project <folder>` komutu da aynı kontrolü ve komutları ekrana yazdırır; hiçbir şey kurmaz.

Bir kurucu tamamlandığında çıktısını oku ve `Enter` ile geri dön. Kurulan program hâlâ bulunamıyorsa yeni bir terminal açıp kurulumu tekrar başlat. Linux'ta `sudo` parola isterken yazdığın karakterleri ekranda göstermez.

## Çekirdek katman (Core)

Her projenin ihtiyaç duyduğu temel katman. Elle kuruyorsan tabloyu yukarıdan aşağıya sırayla uygula.

| Araç | Ne işe yarar ve nasıl kurulur? |
|---|---|
| [Node.js](https://nodejs.org/en/download) | Aşağıdaki JavaScript araçlarını çalıştırır. Windows: `winget install --id OpenJS.NodeJS.LTS --exact --source winget`. Omarchy: `omarchy install dev-env node`. |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | Görevlerini projede Markdown dosyaları olarak ve bir kanban panosu (işleri Yapılacak, Yapılıyor, Bitti sütunlarında izleyen pano) düzeninde tutar. `npm i -g backlog.md@1.55.3`. npm `EACCES` yetki hatası verirse [npm's guide](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally) adımlarını izle; komutun başına `sudo` ekleme. |
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

**Senin dilin.** Komuta `--lang tr` (ya da başka bir dil kodu) eklersen ajan seninle o dilde konuşur; görevleri, kararları, worklog'ları ve commit mesajlarını da o dilde yazar. `Next:` gibi anahtarlar ve `Done` gibi durum adları İngilizce kalır, çünkü araçlar onları okur: `Next: İlk testi çalıştır`. Bayrak `AGENTS.md`'ye tek bir `Language: tr` satırı, projenin `.claude/settings.json` dosyasına da Claude Code'un `language` ayarını yazar; böylece ayar projeyi açan herkes için geçerli olur (ayar dosyası senin kendi dosyansa yazılmaz, `/pm-setup` için listelenir). Bayrağı vermezsen `/pm-setup` bir kez sorar. Dili sonradan değiştirmek için projede `python .pm/tools/pm_init.py . --lang <kod>` çalıştır; eski kayıtlar çevrilmez. Bir görev ya da karar hâlâ İngilizce görünüyorsa `pm_check` bunun için bir `Info:` satırı basar, kontrolü düşürmez.

## İsteğe bağlı katmanlar

Map mimari şemaları ekler ve ajanın bunları güncel tutar; Swarm yardımcı ajanları izleyebileceğin bölmelerde çalıştırır; EVREN ise kendi EVREN modellerini yerel bir köprü üzerinden bağlar. İlk görev için hiçbiri gerekmez, birini sonradan da ekleyebilirsin.

[Map, Swarm ve EVREN](optional-layers.md): her birinin neyi eklediği, neye ihtiyaç duyduğu ve nasıl eklendiği.

## Kurulumdan sonra: /pm-setup

Claude Code'da project-manager klasörünü değil, **kendi projeni** aç:

- **Windows:** Done ekranında `o` tuşuna bas ya da [Claude Desktop](https://code.claude.com/docs/en/desktop-quickstart) uygulamasını açıp Code sekmesinden proje klasörünü seç. Desktop ayrı kurulur ve Code sekmesi ücretli bir Claude planı gerektirir; terminal üzerinden de çalışabilirsin. Desktop önce giriş yapmanı isterse seçtiğin projeyi unutur: giriş yap, ardından tekrar `o` tuşuna bas.
- **Linux:** `cd ~/projects/my-project` komutunu, ardından `claude` komutunu çalıştır.

`/pm-setup` yazıp Enter'a bas. Kurulum sohbeti bir devir notu (`.pm/local/handover.md`) bıraktıysa ajan önce onu okur. Üç cümleyle `.pm`'in ne olduğunu anlatır ve proje yönetimi tarafını nasıl anlatmasını istediğini sorar (aşağıda). Sonra Backlog içinde bir kurulum Epic'i (adımlarını alt görev olarak tutan üst görev) açar ve bulduklarını tek tek sorar: mevcut ajan kuralların, Git kancaların, CI (kod gönderildiğinde testleri otomatik çalıştıran sürekli entegrasyon akışı), testlerin, görev listelerin, kurulumun seninle birleştirmek üzere bıraktığı dosyalar, projenin amacı (proje tüzüğü / `charter`) ve elindeki yapay zekâ modelleri. Sen onay vermeden hiçbir şey değiştirilmez. Kurulum, projenden küçük ve gerçek bir işle ve sonraki oturum için hazır bir promptla biter.

Zaten kullandığın MCP sunucuları, eklentiler (`plugin`), beceriler veya uygulamalar var mı? [Kendi araçlarını işe yarar kıl](own-tools.md) sayfasına bak. `/pm-setup` bunları tek tek ele alır, mevcut kurulumunu korur ve onay verirsen kısa bir “hangi araç ne zaman” kuralı ile gerçek bir duman testi (`smoke check`, aracın gerçekten çalıştığını gösteren küçük bir deneme) ekler.

Nasıl anlattığı: **kısa ipucu** (varsayılan: yeni bir şey ilk kez çıktığında tek cümle, aynı şey için en fazla iki kez), **birlikte dene** (adımı sana bırakır, yol gösterir; hiç komut yazmazsın) ya da **kapalı** (açıklama yok; dosyalarını değiştirmeden önce yine sorar). Kapalı'yı seçmezsen ilk gerçek iş birlikte yapılır. Sohbette istediğin an değiştirebilirsin: "anlatmayı bırak", "görevleri açıkla", "Backlog'u zaten biliyorum".

## Sonradan güncelleme

Sürüm etiketiyle yükseltme, araçların ve becerilerin ayrı güncellenmesi ve geri alırken proje kayıtlarının korunması için [Yükselt ve geri al](upgrading.md) sayfasına bak.

## Bir şey bozulursa

`.pm` paketinin kendisiyle ilgili bir sorun yaşarsan projende `/pm-feedback` komutunu çalıştır. Bu komut yalnızca teşhis bilgisi içeren bir rapor hazırlar ve önce sana gösterir. Yalnızca sen onay verirsen GitHub üzerinde bir sorun kaydı (`issue`) açar; bunun için GitHub'ın `gh` komut satırı aracında (CLI) oturum açılmış olması gerekir. Kurulum henüz beceriler (`skill`) yüklenmeden önce hata verirse bunun yerine TUI'deki `a` tuşunu kullan.

**Windows, Akıllı Uygulama Denetimi (Smart App Control).** Şimdiye kadar gerçek bir bilgisayarda değil, yalnızca Windows Sandbox içinde görüldü: Akıllı Uygulama Denetimi açıkken Git for Windows'un imzasız DLL (kütüphane) dosyalarını engellediği için `git` komutu "Bad Image" hatasıyla (`0xc0e90002`) durur. Git kurucusu yine de kurulumun başarılı olduğunu söyler ama Git'i kimlik doğrulama yardımcısı (`credential helper`, tarayıcıda giriş penceresi açıp hesabı hatırlayan bileşen) olmadan bırakır. Bu yüzden `git clone` komutu giriş penceresi açmak yerine terminalde GitHub kullanıcı adı sorar. `git config --system credential.helper` komutuyla kontrol et (ekrana `manager` yazmalıdır). Hiçbir şey yazmıyorsa Git'i bir kez yeniden kur, ama ancak `git --version` yeniden çalıştıktan sonra (yani Akıllı Uygulama Denetimi Git'i artık engellemiyorken): `winget install --id Git.Git --exact --source winget --force`. Akıllı Uygulama Denetimi bir Windows güvenlik ayarıdır (Windows Güvenliği, Uygulama ve tarayıcı denetimi); kapatıp kapatmamaya kendin karar ver.
