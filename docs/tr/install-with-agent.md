---
title: Ajanınla kur
description: Kodlama ajanının project-manager'ı projene kurarken izlediği adımlar; her değişiklikten önce sana sorar.
---

project-manager'ı elle kurman gerekmez. Kodlama ajanını (coding agent: Claude Code, Codex, Pi ya da bir başkası) projenin durduğu klasörde aç ve şunu yapıştır:

```text
project-manager'ı projeme kur. https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/tr/install-with-agent.md sayfasının tamamını oku (web aracın yalnız özet veriyorsa curl ile indir), adım adım izle, her değişiklikten önce bana sor ve sayfanın dur dediği yerde dur.
```

Ajan birkaç soru sorar, bilgisayarını kontrol eder, kurulumu projende yeni bir dalda (branch) yapar ve bir devir notu bırakır. Sonra projeni yeni bir oturumda (session) açıp `/pm-setup` yazarsın; ajan paketi orada seninle birlikte projene uyarlar. Demo proje kurmaz, koduna dokunmaz. Terminalde adım adım yol gösteren bir ekranı tercih edersen [kurulum ekranını (TUI)](getting-started.md) kullan. Dal, commit ya da MCP sunucusu (MCP server) gibi kelimeler [sözlükte](glossary.md) açıklanır.

**Okumayı burada bırakabilirsin:** sayfanın geri kalanı senin için değil, ajanın için yazıldı.

## Ajan için

project-manager'ı kullanıcının projesine kuruyorsun. Bu adımları sırayla izle.

- Kullanıcıyla kendi dilinde, sade konuş; projesini bildiğini ama yapay zekâ ve proje yönetimi terimlerini bilmediğini varsay. Her seferinde tek bir soru sor.
- Bir şeyi değiştiren her komuttan önce (paket kurulumu, yazma yapan bir git komutu ya da kurucu) ne işe yaradığını tek cümleyle söyle, komutu göster ve ancak kullanıcı açıkça onayladıktan sonra çalıştır. Salt okunur kontroller için onay gerekmez. npm komutlarına asla `sudo` ekleme.
- Projenin kodunu düzenleme ve örnek dosyalar oluşturma. Bu sohbette `/pm-setup` çalıştırma.
- İlerlerken bir liste tut: ne kurdun, kullanıcı neyi atladı ve hangi komutta hangi hata çıktı. Bu liste 6. adımda devir dosyasına yazılır.
- 7. adımdan sonra dur.
- Commit mesajlarında türden sonraki kısmı projenin dilinde yaz, örneğin `chore: project-manager kurulumu`; commit türü İngilizce kalır.

### 1. Sor

Bunları tek tek, her seçeneği tek cümleyle açıklayarak sor:

1. **Proje klasörü**, tam dosya yoluyla. Kullanıcı emin değilse bulunduğun klasördeki alt klasörleri listeleyip sor.
2. **Dil**: konuşma ve proje kayıtlarının dili, `tr` ya da `en` gibi bir dil kodu olarak. Alan adları ve durum adları İngilizce kalır, çünkü araçlar onları okur.
3. **Map (harita)** (varsayılan: evet): proje parçalarının birbirine nasıl bağlandığını gösteren, ajanın okuyup güncel tutabildiği mimari şema. Node.js gerektirir. Kullanıcıya şimdi atlayıp sonradan da ekleyebileceğini söyle.
4. **Swarm (sürü)** (varsayılan: hayır): kullanıcının izleyebildiği terminal bölmelerinde çalışan yardımcı ajanlar. Pi ve Herdr gerektirir; sonradan da eklenebileceğini söyle.

Katmanlar `core` ve seçildiyse `map`, `swarm`, `evren` olur; `evren`'i (bazı kullanıcıların zaten abonesi olduğu bir model servisi) yalnızca halihazırda EVREN hesabı olan kullanıcıya öner. Bunları aşağıda `<layers>` olarak kullan, örneğin `core,map`.

### 2. Python'u ve Git'i kontrol et, project-manager'ı indir

Python 3.11 veya daha yeni bir sürüm ile Git gerekir. `python --version` ya da `git --version` hata verirse kullanıcıya [Başlangıç](getting-started.md) sayfasındaki "Başlamadan önce" bölümünün komutlarını göster, onay verirse çalıştır; program hâlâ bulunamıyorsa yeni bir terminal açmasını iste. İkisi de çalışmadan devam etme.

project-manager'ı projenin içine değil, **yanına** (projeyi barındıran üst klasöre) klonla:

```bash
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
```

Git sürüme geçmeden önce `warning: refs/tags/... is not a commit!` uyarısı yazabilir: bir sürüm etiketinde bu normaldir ve klon sağlamdır.

Orada zaten bir `project-manager` klasörü varsa kontrol et: `git -C project-manager describe --tags --exact-match` yukarıdaki sürümü yazmalı ve `git -C project-manager status --porcelain` boş dönmelidir. Sürüm farklıysa ve klasör temizse `git -C project-manager fetch --tags` ve `git -C project-manager switch --detach <release>` komutlarını öner; klasörde yerel değişiklikler varsa dokunma: dur ve sor. Aşağıda `<pm>` bu klasörü, `<project>` ise proje klasörünü gösterir; dosya yolunda boşluk olabileceği için ikisini de her komutta tırnak içine al.

### 3. Projeyi güvenle değiştirilebilir hâle getir

Proje klasöründe:

1. `.pm/` zaten varsa project-manager kuruludur: dur ve kullanıcıyı [Yükselt ve geri al](upgrading.md) sayfasına ya da o klasörde açacağı yeni bir oturumda `/pm-setup` komutuna yönlendir.
2. `git rev-parse --show-toplevel` çalıştır. Hata verirse projenin henüz Git geçmişi yoktur: onay alırsan `git init` çalıştır, ardından `git status --short` çıktısını göster ve `.gitignore` dosyasının gizli bilgileri ve büyük klasörleri (`.env`, `node_modules`) dışarıda tuttuğunu kontrol et. İkinci kez onay alırsan `git add -A` ve projenin dilinde "chore: project-manager öncesi ilk commit" gibi bir mesajla `git commit` çalıştır. Komut farklı bir klasör yazarsa seçilen klasör başka bir Git deposunun içindedir: dur ve hangi klasörün asıl proje olduğunu sor.
3. `git status --porcelain` çalıştır. Değişiklik listelerse kullanıcıya göster ve iki seçenek sun: bunları commit etmek ya da `git stash push -u -m "before project-manager"` ile geçici olarak kenara ayırmak. Kullanıcı ikisini de istemezse burada dur.
4. Mevcut dalı (`git branch --show-current`) ve `git config core.hooksPath` komutunun bir şey yazıp yazmadığını not et. Ardından onay alırsan `git switch -c pm-setup` çalıştır.

Kurulum dalda commit edildikten sonra (5. adım), bu noktadan itibaren projede yapılan her şeyin nasıl geri alınacağını kullanıcıya anlat: `git switch <old branch>`, ardından `git branch -D pm-setup`; `.pm` klasörü hâlâ duruyorsa sil (önceden yoktu, içinde kullanıcıya ait bir dosya bulunmaz); `core.hooksPath` önceden boşsa `git config --unset core.hooksPath`; kenara ayrılan değişiklikler ise `git stash pop` ile geri gelir. Bilgisayara kurulan programlar (4. adım) yerinde kalır; onları [Yükselt ve geri al](upgrading.md) sayfası anlatır.

### 4. Bilgisayarı kontrol et

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>"
```

Bu komut hiçbir şey kurmaz. Neyin kurulu olduğunu ve her adım için tek komutluk bir yapılacaklar listesini basar; çıkış kodunun `1` olması yalnızca geriye adım kaldığını, `2` olması ise yanlış bir argüman verildiğini gösterir. `.pm` proje dosyaları adımını 5. adıma bırak. Diğer her adımda programın ne işe yaradığını tek cümleyle söyle, komutu göster ve onay alırsan çalıştır; atlanan adımları listene ekle. `Note:` ile başlayan satırlar yalnızca kullanıcının yapabileceği işlerdir; bunları kullanıcıya söyle. Geriye yalnız proje dosyaları kalana kadar her adımdan sonra kontrolü tekrar çalıştır.

### 5. Paketi kur

```bash
python "<pm>/template/.pm/tools/pm_init.py" "<project>" --check --lang <code>
```

Seçildiyse `--map` ve `--swarm` ekle. Bu komut hiçbir dosya yazmaz. Çıkış kodu `0` ise çakışma yoktur; `3` ise projede zaten kendi ajan kuralları, kancaları (hooks) ya da ayarları vardır ve bunlar korunup `/pm-setup` sırasında kullanıcıyla birleştirilmek üzere listelenir; başka bir çıkış kodunda dur ve hatayı not et. Planı birkaç sade satırla anlat, ardından onay alırsan aynı komutu `--check` olmadan çalıştır (`3` kodundan sonra `--keep-existing` ekle).

Ardından kurulumu `/pm-setup` için kaydet:

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>" --record
```

Onay alırsan kurulan dosyaları `pm-setup` dalında commit et: `git add -A` ve projenin dilinde "chore: project-manager kurulumu" gibi bir mesajla `git commit` çalıştır. Yukarıdaki geri alma adımı bu commit sayesinde çalışır. Paketin kendi commit kancası çalışacaktır; hata verirse atlatma, hatayı not et. Kullanıcı commit istemezse devir dosyasının Undo bölümüne, `pm_init --check` komutunun listelediği dosyaların elle silinmesi gerektiğini yaz.

### 6. Devir dosyasını yaz

`<project>/.pm/local/handover.md` dosyasını yaz (Git tarafından yok sayılır, `setup.json` dosyasının yanındadır). Sonraki oturum her şeyden önce bu dosyayı okur ve kurulum sorunlarını yine buraya yazar; böylece kullanıcı iki sohbet arasında hata mesajı taşımak zorunda kalmaz. Araçlar ve tüm modeller okuyabilsin diye başlıkları İngilizce bırak, içeriği ise kullanıcının dilinde yaz:

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

Her bölümü tuttuğun listeden doldur; boş kalan yerlere `none` yaz. Açık kalan her sorunu sıradaki adımlara da ekle.

### 7. Devret ve dur

Kullanıcıya birkaç satırla nelerin kurulduğunu ve nelerin açık kaldığını söyle. Ardından doğrudan uygulayabileceği sıradaki adımı ver:

> Proje klasörünün kendisini bu oturumda değil, yeni bir oturumda aç: ajan bir projenin ayarlarını, kancalarını ve becerilerini (skills) yalnızca başlatıldığı klasörden okur.
>
> - Terminalde Claude Code: `cd "<project>"`, ardından `claude`. Claude Desktop: Code sekmesi, ardından klasörü seç.
> - Pi: `cd "<project>"`, ardından `pi`.
>
> Sonra kullandığın ajana göre kurulum komutunu yaz:
>
> | Ajan | Yazılacak komut |
> | --- | --- |
> | Claude Code | `/pm-setup` |
> | Pi | `/skill:pm-setup` |
> | Codex | `$pm-setup` |
>
> **Karşına neler çıkacak:**
>
> - Önce klasöre güvenip güvenmediğin sorulur. Bu senin projen: "Yes, I trust this folder" seçeneğini seç.
> - Sonra her proje sunucusu için bir soru gelir (Context7, LikeC4). Bunlara izin ver: yalnızca güncel belgeleri ve şemaları okurlar, dosyaya yazan her işlem yine senden onay ister; hayır demek yalnızca daha az yanıt almak demektir. Context7 sorgularını kendi sunucusuna gönderir, bu yüzden sorgularda gizli bilgi yer almaz.
> - Ardından ne kadar açıklama istediğinle ilgili üç kısa soru, panoda (board) bir kurulum Epic'i ve küçük, gerçek bir görev gelir.
> - Bu sırada bir etiketin "commit olmadığı" ("is not a commit") uyarısını görebilirsin. Kurulum sırasında bu normaldir ve kurulum sağlamdır.

Burada dur. Kurulumu bu sohbette sürdürme.
