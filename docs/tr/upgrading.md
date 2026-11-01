---
title: Yükselt ve geri al
description: Kurulu bir projeyi her seferinde tek katman ilerleyerek yükselt; görevlerini veya kararlarını kaybetmeden paket dosyalarını eski sürüme geri al.
---

Bir proje birbirinden bağımsız birkaç katmandan oluşur. Commit, dal ya da katman gibi kelimeler [sözlükte](glossary.md). project-manager kaynak klasörünü (`checkout`) güncellemek; kurulu bir projeyi, bilgisayardaki genel (`global`) araçlarını veya kendi eklentilerini **güncellemez**. Her seferinde tek bir katmanı güncelle, önceki sürümü sakla ve bir sonrakine geçmeden önce kontrol et.

## Hiçbir şeyi değiştirmeden önce

1. Çalışmakta olan işçi ajanları (`worker`, tek bir alt işi yapan yardımcı ajanlar) bitir veya durdur. Kendi projende değişiklikleri Git'e kaydet (`commit`) ya da dışarıda özel bir yedek al. Görevleri, karar kayıtlarını (`decision record`), çalışma günlüğünü (`worklog`), proje tüzüğünü (`charter`), şartnameleri (`specs`), kök dizindeki talimatları ve yapılandırma dosyalarını bu yedeğe dahil et. Ayrıca Git'in yok saydığı (`ignored`) `.pm/local/` klasörünü de güvenli bir yere kopyala: bu klasör yerel kurulum kayıtlarını ve paket yedeklerini tutar; Git burayı kaydetmez.
2. `git status --short` çıktısını, project-manager kaynak etiketini/commit'ini (`git describe --tags --always`), projenin `.pm/VERSION` dosyasını, seçili katmanları ve araçların sürüm çıktılarını bir yere not et. Eski sürümün `tools/setup/bom.toml` dosyasının bir kopyasını sakla.
3. Yeni [sürüm notlarını](https://github.com/Kscl1/project-manager/releases) oku. Alfa sürümlerinde dosya biçimleri değişebilir: eski bir kontrol aracı, daha yeni bir paketle yazılmış kayıtları anlamayabilir. Aracı susturmak için kayıtları baştan yazma veya silme.

## 1. Kaynak sürümü seç

Bu komutlar senin projende değil, **project-manager kaynak klonunda** çalıştırılır. Başlangıç rehberi `v0.1.0-alpha.6` sürümünü kurar. Yükseltme yaparken aşağıdaki `<new-tag>` yerine gerçek ve daha yeni bir sürüm etiketi (`tag`) yaz.

```bash
git status --short
git fetch --tags origin
git checkout --detach <new-tag>
git describe --tags --always
```

Kaynak klasörde yerel değişiklikler varsa önce durup bunları kaydet. Bir sürüm etiketine geçildiğinde Git'in "detached HEAD" (daldan ayrılmış durum) bildirmesi normaldir. `git pull` komutu sürüm yükseltme yolu değildir. Normal kullanımda yayımlanmış sürüm etiketlerini kullan; `git fetch origin` ve `git checkout --detach origin/main` komutları yalnızca henüz yayımlanmamış kodu bilerek test etmek istediğinde kullanılır. Bunu yaparsan tam `commit` kimliğini not et.

## 2. Kurulu `.pm` paketini yükselt

Bu kaynak klonun içinden, kurucuyu kendi projene karşı çalıştır. Aşağıdaki örnek isteğe bağlı her iki katmanı da dahil eder; eklemek istemiyorsan `--map` / `--swarm` seçeneklerini çıkar. Zaten kurulu olan isteğe bağlı katmanlar, bu bayrakları (`flag`, komut seçeneği) yazmasan bile yükseltilmeye devam eder. Bayraklar yalnızca yeni katman ekler; kurulu bir katmanı kaldırmaz.

```bash
python template/.pm/tools/pm_init.py ../my-project --upgrade --dry-run --map --swarm
python template/.pm/tools/pm_init.py ../my-project --upgrade --map --swarm
```

Önce deneme çalışmasının (`--dry-run`, hiçbir dosyayı değiştirmeden ne yapılacağını gösteren ön izleme) çıktısını oku. Bu çalışma yeni eklenecek veya kaldırılacak dosyaları, yerel düzenlemeleri ve her iki tarafta değişmiş dosyaları listeler. Hiçbir dosya yazmaz. Gerçek yükseltme ise şunları yapar:

- `.pm/tools`, `tests`, `hooks`, `roles`, `templates` klasörlerini ve kurulu sürü (`swarm`) katmanını yenileriyle değiştirir. Paketten kaldırılmış dosyalar bu yönetilen klasörlerden silinir.
- `.agents/skills/` içindeki paketle gelen `pm-*` becerilerini (`skill`, ajana belirli bir işi nasıl yapacağını öğreten komut paketleri) yeniler ve bunların Claude Code yönlendirmelerini günceller. **Yönetilen klasörlerin içindeki yerel düzenlemelerin üzerine yazılır.** Bu klasörlerin eski hâlleri `.pm/local/backup/<timestamp>/` altına taşınır (paketle zaten birebir aynı olan klasör olduğu gibi kalır ve yedeklenmez); bu yedekleri yeni paketin tamamının üzerine körü körüne yazmak için değil, bilerek yaptığın değişiklikleri yeniden uygulamak için kullan. Yedek klasörleri saniye hassasiyetinde zaman damgası (`timestamp`) kullanır: ikinci bir gerçek yükseltme çalıştırmadan önce bir sonraki saniyeye geçmesini bekle.
- Projenin görevlerine, karar kayıtlarına, çalışma günlüğüne, şartnamelerine, proje tüzüğüne ve `.pm/models.md` gibi başlangıç (`seed`) dosyalarına dokunmaz. Paketle gelen `pm-*` isimlerinin dışındaki kendi becerilerine dokunulmaz; kişisel bir beceriye paketle gelen isimlerden birini verme.
- Mevcut kök dizin talimatlarını, Backlog yapılandırmasını, `.claude/settings.json` ve `.mcp.json` dosyalarını korur; eksik entegrasyonları `.pm/local/merge-by-hand.md` dosyasına yazar. `.gitignore` / `.gitattributes` / `.ignore` dosyalarının sonuna paket kurallarını ekleyebilir ve projenin kendi Git kancaları (`hooks`) yoksa paket kancalarını etkinleştirebilir veya hazırlayabilir.

Kod farkını (`diff`) ve birleştirme listesini incele. Sürüm notları değişiklik gerektirdiğini söylüyorsa, korunan kök dizin ve başlangıç dosyalarını yeni şablonlarla karşılaştır; `--upgrade` seçeneği bunları bilerek otomatik eşitlemez. **Kendi projenin içinden** şu komutları çalıştır:

```bash
python .pm/tools/pm_check.py
python -m unittest discover -s .pm/tests
python .pm/tools/pm_board.py --resume
```

Sürü (`swarm`) katmanını kurduysan `python -m unittest discover -s .pm/swarm` komutunu da çalıştır; yükseltme aracı bu kontrolleri sıradaki adımlar olarak ekrana yazdırır. `.pm/VERSION` dosyasını incele: burada son paket commit'i ve bir sürüm etiketindeysen etiket adı yazar. Ardından normal bir görev ve oturum devam (`resume`) akışını dene. Tutarlılık kontrolünün geçmesi, tam uyumluluk onayı anlamına gelmez. Yükseltmeyi projende Git'e kaydetmeden (`commit`) önce değişiklikleri incele ve sonuçtan emin olana kadar Git dışı yedekleri sakla.

## 3. Araçları ayrı yükselt

Komutların kaynağı, sürümün [malzeme listesidir (`bill of materials` / BOM)](https://github.com/Kscl1/project-manager/blob/main/tools/setup/bom.toml). Burada `min` desteklenen en düşük sürümü, `tested` insan tarafından çalıştırılan kontrollerle doğrulanmış sürümü, `install.*` ise kurucu destekliyorsa sabitlenmiş (`pinned`) kurulum sürümünü gösterir. Bu üç değerin birbirine eşit olması şart değildir. Kurulu bir sürümün `tested` değerinden yüksek olması, bozuk olduğu değil **henüz test edilmediği** anlamına gelir.

2. adımdaki yükseltme kısa bir listeyle biter: "Programs on this machine against this release". Listede eksik ya da `min` altında olan (gerekli), sabitlenmiş `tested` sürümünden eski olan (isteğe bağlı) veya ondan yeni olan (bir şey bozulmadıkça kalsın) her program komutuyla yazılır. Hiçbir şey kurulmaz. Ajan listeyi okur, her satırı sana anlatır ve bir komutu yalnızca sen "evet" dersen çalıştırır. Listeyi yeniden görmek için: `python tools/setup/bom.py --updates --layers core,map,swarm`.

Yeni sürümlerden haberdar olmak için depoyu GitHub'da aç ve **Watch → Custom → Releases** seç.

Sürüm değiştirdikten sonra kurulum ekranını (`TUI`, metin tabanlı arayüz) veya onun salt okunur döküm komutunu kullan:

```bash
python tools/setup/bom.py --project ../my-project --layers core,map,swarm
```

`evren` katmanını yalnızca bu isteğe bağlı katmanı kullanıyorsan ekle. Komutun `1` çıkış koduyla (`Exit 1`) bitmesi, kalan adımlar veya uyarılar olduğu anlamına gelebilir; tabloyu oku. TUI, kurulu her aracı yeni sabit sürüme zorla geçirmez: bir aracı bilerek yükseltirken sürümün ilgili `install.*` / `upgrade.*` komutunu inceleyip kendin çalıştır, ardından tekrar kontrol et. TUI gereksinimleri değiştiyse bunları TUI'nin ayrı sanal ortamına (`virtual environment`) yeniden kur.

| Araç grubu | Yükseltme yolu | Geri alma (`rollback`) hazırlığı |
|---|---|---|
| Backlog.md, Pi | Sürümün sabitlenmiş `npm i -g package@version` komutunu çalıştır. | Eski sürüm numarasını not et; gerekirse bir önceki npm sürümünü birebir yeniden kur. |
| Pi uzantıları | Sürümün `pi install npm:package@version` komutunu çalıştır. | Eski paket sürümlerini kaydet ve aynı sabitlenmiş kurulum biçimiyle geri yükle. Pi'yi yeniden başlat ve gerçek paket listesini doğrula. |
| LikeC4 CLI | Sürümün sabitlenmiş `npx likec4@version ...` komutunu çalıştır. Bu işlem genel (`global`) hiçbir paketi yükseltmez. | Önceki sabit sürümü tekrar kullan; model dosyalarını koru. Projenin MCP komutu başka bir paketi veya sürümü sabitliyorsa onu ayrıca incele. |
| Herdr | Ana kaynaktaki (`upstream`) en son sürümü kabul etmeden önce aracın kendi resmî kurulum/güncelleme talimatlarını ve sürüm bildirimini (`manifest`) incele. | Değiştirmeden önce eski çalıştırılabilir dosyayı (`binary`) ve kaynak bilgisini / doğrulama özetini (`provenance/checksum`) yedekle. Desteklenen daha eski bir sürüm geri yüklenemiyorsa başka bir kurtarma yolun olmadan yükseltme yapma. En son sürümü kuran kurucu bir geri alma komutu değildir. |
| Python, Git, Node.js, Claude Code | İşletim sisteminin veya üreticinin desteklediği yükseltme yolunu izle; bu komutların hepsi belirli bir sürüme sabitlenmemiştir. | Üreticinin desteklediği önceki kurucuyu/çalışma ortamını (`runtime`) ve ayar yedeğini sakla. Araçlarının hâlâ ihtiyaç duyduğu bir yorumlayıcıyı (`interpreter`, örneğin eski Python sürümü) kaldırma. Otomatik güncellenen araçlar için üreticiye özel ayarlar gerekebilir. |
| İsteğe bağlı köprü/uygulama klonları | İlgili aracın kendi sürüm talimatlarını izle; eski `commit` kimliğini ve bağımlılık ortamını kaydet. | Proje kayıtlarına dokunmadan o klonun önceki desteklenen sürüm etiketini (`ref`) ve ortamını geri yükle. Sürekli değişen bir `git pull` tekrarlanabilir bir sürüm sabitlemesi değildir. |

Herdr için yeni bir sürümün çıkmış olması, çalıştırıcı (`runner`) ile sorunsuz çalıştığının kanıtı **değildir**. `tested` değerini ileri taşımadan önce **Pi ve Claude Code ile ayrı ayrı** ekranda görünen küçük birer işçi ajan çalıştır; bölme, durum, çıktı ve kanıt adımlarını doğrula ve sonuçları sakla. Bu rehberdeki otomatik paket testlerini bunun yerine kullanma. Döküm komutu (`bom.py`) hiçbir işçi ajan başlatmaz.

## Kendi üçüncü taraf becerilerin

Kullanıcının **kendi** kurduğu üçüncü taraf beceriler için, o becerinin kendi kurucusunu ve sürüm sabitlemesini kullan ve önceki kopyasını yedekte tut. Bunlar `.pm` tarafından yönetilmez; [kendi araçların](own-tools.md) sayfasına bak.

## Bakımı yapanlar için

Pakete dahil edilmiş becerilerin incelenmesi, Renovate ilkesi ve `pi-mcp-adapter` 5.x'ten 7.0'a geçiş notları, paketi geliştirenler ya da bağımlılıklarını izleyenler içindir. Bu notlar katkı rehberine taşındı: [Bakımı yapanlar](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md#maintainers).

## Kayıtları kaybetmeden eski sürüme geri al (`rollback`)

**Tüm projeni eski bir commit'e sıfırlama (`git reset`) veya `.pm` klasörünün tamamını eski bir kopyayla değiştirme.** Bunu yapmak, yükseltmeden sonra yazılmış görevleri ve kararları siler. Geri alma işlemi (`rollback`, sorun çıktığında önceki sürüme dönme) yalnızca yönetilen paket dosyalarını değiştirir; en güncel proje verilerini koru.

1. İşçi ajanları durdur ve Git'in yok saydığı yedekler dahil mevcut durumu yedekle. Sorun çıkaran sürümü ve belirtileri kaydet.
2. **Kaynak klonda**, çalıştığını bildiğin bir önceki sürümü seç; örneğin:

   ```bash
   git fetch --tags origin
   git checkout --detach v0.1.0-alpha.1
   python template/.pm/tools/pm_init.py ../my-project --upgrade --dry-run --map --swarm
   python template/.pm/tools/pm_init.py ../my-project --upgrade --map --swarm
   ```

3. Kendi projende `.pm/VERSION` dosyasını, kod farkını (`diff`) ve birleştirme listesini kontrol et. Yönetilen paket dosyalarında bilerek yaptığın yerel düzenlemeler varsa, bunları ancak eski sürümle karşılaştırdıktan sonra doğru zaman damgalı yedekten geri yükle. Yükseltme sırasında kök dizinde veya ayar dosyalarında elle yaptığın değişiklikleri ayrıca incele: kurucu bunları geri almaz, olduğu gibi korur. Yalnızca yeni sürümde bulunan beceri klasörleri veya isteğe bağlı katmanlar elle inceleme gerektirebilir; eski bir kurucu gelecekteki paket adlarını bilemez. Bir klasörün hiçbir proje kaydı içermediğinden ve yalnızca paket dosyalarından oluştuğundan emin olmadan onu asla silme.
4. Değişen genel (`global`) araçları, kaydettiğin eski sürüm numaralarını ve kurucuları kullanarak tek tek eski sürümlerine döndür. `.pm` paketini geri almak Herdr, Pi, uzantılar, uygulamalar veya MCP sunucularını eski sürüme döndürmez.
5. Paket kontrollerini ve normal bir çalışma akışını tekrar çalıştır. Yükseltmeden **sonra** oluşturulmuş kayıtların hâlâ yerinde olduğunu doğrula. Eski sürüm yeni kayıt biçimini okuyamıyorsa dur ve biçime özel bir geçiş (`migration`) planlamak için yedeği kullan; bu kayıtları silme.

### Ne prova edildi?

2026-10-18 tarihinde yapılan bir geliştirici provasında; `v0.1.0-alpha.1` sürümünden yerel kurulum, `185f9ca` commit'indeki `main` dalına yükseltme ve Map ile Swarm katmanları açıkken tekrar etiketli sürüme geri alma adımları denendi. Provada yönetilen dosyalar, bilerek düzenlenmiş bir paket aracı ve yükseltmeden sonra eklenen bir görev dahil proje kayıtlarının korunması kontrol edildi. Bu bir geliştirici provasıdır; bağımsız bir kullanıcının kabul testi veya genel araçların yükseltildiğinin kanıtı değildir. Hiçbir sürüm veya araç uyumluluğunu garanti etmez.
