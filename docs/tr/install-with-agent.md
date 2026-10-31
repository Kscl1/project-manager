---
title: Ajanınla kur
description: Kodlama ajanının project-manager'ı projene kurarken izlediği adımlar; her değişiklikten önce sana sorar.
---

project-manager'ı elle kurman gerekmez. Kodlama ajanını (Claude Code, Codex, Pi ya da başka biri) projenin bulunduğu klasörde aç ve şunu yapıştır:

```text
project-manager'ı projeme kur. https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/tr/install-with-agent.md sayfasının tamamını oku (web aracın yalnız özet veriyorsa curl ile indir), adım adım izle, her değişiklikten önce bana sor ve sayfanın dur dediği yerde dur.
```

Ajan birkaç soru sorar, makineni kontrol eder, projende yeni bir dalda kurar ve bir devir notu bırakır. Sonra projeni yeni bir oturumda açıp `/pm-setup` yazarsın; ajan paketi orada seninle birlikte projene uydurur. Demo proje kurmaz, koduna dokunmaz. Terminalde adım adım ilerleyen bir ekranı tercih edersen [kurulum ekranını (TUI)](getting-started.md) kullan.

## Ajan için

project-manager'ı kullanıcının projesine kuruyorsun. Adımları sırayla izle.

- Kullanıcıyla onun dilinde, sade konuş; projesini bildiğini, yapay zekâ ve proje yönetimi terimlerini bilmediğini varsay. Her seferinde tek soru sor.
- Bir şeyi değiştiren her komuttan önce (kurulum, yazan bir git komutu, kurucu) ne yaptığını tek cümleyle söyle, komutu göster ve ancak açık bir evetten sonra çalıştır. Yalnız okuyan kontroller evet gerektirmez. npm'e asla `sudo` ekleme.
- Projenin koduna dokunma, örnek dosya oluşturma. `/pm-setup`'ı burada çalıştırma.
- İlerlerken bir liste tut: ne kurdun, kullanıcı neyi atladı, her hata ve komutu. Bu liste 6. adımda devir dosyasına girer.
- 7. adımdan sonra dur.
- Commit mesajlarını türden sonra projenin dilinde yaz, örneğin `chore: project-manager kurulumu`; tür İngilizce kalır.

### 1. Sor

Bunları tek tek, her seçenek için tek cümleyle sor:

1. **Proje klasörü**, tam yoluyla. Kullanıcı emin değilse bulunduğun yerdeki klasörleri listeleyip sor.
2. **Dil**: konuşma ve proje kayıtlarının dili, `tr` ya da `en` gibi bir kodla. Alan adları ve durum adları İngilizce kalır, çünkü araçlar onları okur.
3. **Harita** (varsayılan evet): projenin mimarisini gösteren, ajanın okuyup güncel tuttuğu şemalar. Node.js gerektirir.
4. **Sürü** (varsayılan hayır): kullanıcının izleyebildiği terminal panellerinde çalışan yardımcı ajanlar. Pi ve Herdr gerektirir; sonradan da eklenebileceğini söyle.

Katmanlar `core`, seçildiyse `map` ve `swarm`'dır. Aşağıda `<layers>` olarak kullan, örneğin `core,map`.

### 2. Python'u ve Git'i kontrol et, project-manager'ı indir

Python 3.11 ya da daha yenisi ve Git gerekir. `python --version` ya da `git --version` hata verirse kullanıcıya [Başlangıç](getting-started.md) sayfasındaki ilk bölümün komutlarını ver, evetle çalıştır; program hâlâ bulunmuyorsa yeni bir terminal açmasını iste. İkisi de çalışmadan devam etme.

project-manager'ı projenin **yanına**, projeyi içeren klasöre indir, asla projenin içine değil:

```bash
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
```

Git sürüme geçmeden önce `warning: refs/tags/... is not a commit!` yazabilir: bir sürüm etiketi için bu beklenir, klon sağlamdır.

Orada zaten bir `project-manager` klasörü varsa kontrol et: `git -C project-manager describe --tags --exact-match` yukarıdaki sürümü yazmalı, `git -C project-manager status --porcelain` hiçbir şey yazmamalı. Sürüm farklıysa ve klasör temizse `git -C project-manager fetch --tags` ve `git -C project-manager switch --detach <sürüm>` öner; klasörde kendi değişiklikleri varsa dokunma: dur ve sor. Aşağıda `<pm>` bu klasör, `<project>` proje klasörüdür; yol boşluk içerebileceği için ikisini de her komutta tırnak içine al.

### 3. Projeyi güvenle değiştirilebilir yap

Proje klasöründe:

1. `.pm/` zaten varsa project-manager kuruludur: dur ve kullanıcıyı [Yükseltme ve geri alma](upgrading.md) sayfasına ya da o klasörde yeni bir oturumda `/pm-setup`'a yönlendir.
2. `git rev-parse --show-toplevel`. Hata verirse projenin henüz Git geçmişi yoktur: evet gelirse `git init` çalıştır, sonra `git status --short` çıktısını göster ve `.gitignore`'un gizli bilgileri ve büyük klasörleri (`.env`, `node_modules`) dışarıda tuttuğunu kontrol et. İkinci bir evetle `git add -A` ve projenin dilinde bir mesajla `git commit` çalıştır, örneğin "chore: project-manager öncesi ilk commit". Başka bir klasör yazarsa seçilen klasör başka bir deponun içindedir: dur ve hangi klasörün proje olduğunu sor.
3. `git status --porcelain`. Değişiklik listelerse göster ve iki yol sun: commit'lemek ya da `git stash push -u -m "before project-manager"` ile kenara koymak. İkisi de istenmezse burada dur.
4. Şu anki dalı (`git branch --show-current`) ve `git config core.hooksPath` bir şey yazıyor mu, not et. Sonra evet gelirse `git switch -c pm-setup`.

Kullanıcıya, kurulum dalda commit'lendikten sonra (5. adım) projede olan her şeyi nasıl geri alacağını söyle: `git switch <eski dal>`, sonra `git branch -D pm-setup`; `.pm` klasörü hâlâ duruyorsa sil (önceden yoktu, içinde kullanıcının bir şeyi olamaz); `core.hooksPath` önceden boşsa `git config --unset core.hooksPath`; kenara konan değişiklikler `git stash pop` ile geri gelir. Makineye kurulan programlar (4. adım) kalır; onlar için [Yükseltme ve geri alma](upgrading.md) sayfasına bak.

### 4. Makineyi kontrol et

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>"
```

Hiçbir şey kurmaz. Neyin kurulu olduğunu ve her adım için tek komutluk bir yapılacaklar listesi yazar; çıkış 1 yalnız adım kaldığını, 2 yanlış bir argümanı gösterir. `.pm` proje dosyalarının adımını 5. adıma bırak. Diğer her adımda programın ne işe yaradığını tek cümleyle söyle, komutu göster ve evetle çalıştır; atlanan adım listene girer. `Note:` ile başlayan satırları yalnız kullanıcı yapabilir; ona söyle. Her adımdan sonra kontrolü yeniden çalıştır, ta ki yalnız proje dosyaları kalana kadar.

### 5. Paketi kur

```bash
python "<pm>/template/.pm/tools/pm_init.py" "<project>" --check --lang <code>
```

Seçildiyse `--map` ve `--swarm` ekle. Hiçbir şey yazmaz. Çıkış 0 çakışma yok demektir; 3, projenin kendi ajan kuralları, hook'ları ya da ayarları olduğu demektir: bunlar korunur ve `/pm-setup` kullanıcıyla birleştirsin diye listelenir; başka bir çıkışta dur ve hatayı yaz. Planı birkaç sade satırla anlat, evet gelirse aynı komutu `--check` olmadan çalıştır (3 çıkışından sonra `--keep-existing` ekle).

Sonra kurulumu `/pm-setup` için kaydet:

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>" --record
```

Evet gelirse kurulan dosyaları `pm-setup` dalında commit'le: `git add -A` ve projenin dilinde bir mesajla `git commit`, örneğin "chore: project-manager kurulumu". Yukarıdaki geri alma bu commit sayesinde çalışır. Paketin commit kontrolü çalışır; geçmezse atlatma, hatayı yaz. Kullanıcı hayır derse devir dosyasının Undo bölümüne `pm_init --check`'in listelediği dosyaların elle silinmesi gerektiğini yaz.

### 6. Devir dosyasını yaz

`<project>/.pm/local/handover.md` dosyasını yaz (git dışında, `setup.json`'ın yanında). Sonraki oturum her şeyden önce onu okur ve kurulum sorunlarını oraya geri yazar; böylece kullanıcı iki sohbet arasında hata metni taşımaz. Başlıklar araçlar ve her model için İngilizce kalır, içerik kullanıcının dilinde:

```markdown
# Hand-over from the install chat

Date: <YYYY-MM-DD> · Release: <tag> · Source: <pm> · Layers: <layers> · Language: <code>
Branch: pm-setup, made from <old branch> · Stash: <none, or its message> · core.hooksPath before: <empty, or its value>

## Installed

## Skipped

## Open problems

## Next steps

1. Open <project> in a new session and run /pm-setup.

## Undo

git switch <old branch>, git branch -D pm-setup, then delete .pm if it is still there.
```

Her bölümü listenden doldur; boş olana `none` yaz. Her açık sorunu sıradaki adımlara da ekle.

### 7. Devret ve dur

Kullanıcıya birkaç satırla neyin kurulduğunu ve neyin açık kaldığını söyle. Sonra sıradaki adımı, izlenmeye hazır biçimde ver:

> Proje klasörünün kendisini bu oturumda değil, yeni bir oturumda aç: ajan bir projenin ayarlarını, hook'larını ve skill'lerini yalnız başladığı klasörden okur.
> - Terminalde Claude Code: `cd "<project>"`, sonra `claude`. Claude Desktop: Code, sonra klasörü seç.
> - Pi: `cd "<project>"`, sonra `pi`.
>
> Claude Code önce klasöre güvenip güvenmediğini sorar: bu senin projen, "Yes, I trust this folder" seç. Projenin güncel belge ve şema sunucularını (Context7, LikeC4) açmak için de sorabilir: izin ver. Okuyan araçlarına projenin ayarlarında izin verilmiştir; yazan her şey yine sorar. Context7 sorgularını kendi sunucusuna gönderir, bu yüzden sorgulara gizli bilgi yazılmaz.
>
> Sonra `/pm-setup` yaz (Pi'de `/skill:pm-setup`, Codex'te `$pm-setup`).

Burada dur. Kurulumu bu sohbette sürdürme.
