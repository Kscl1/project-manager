# pm-setup: fixed texts

Show these as written, in the project language: do not shorten, reword or add to them, so every model shows the same words. For a language not here, translate the English faithfully, keeping the numbering and every sentence. Status names (Ready, Active, Done) and file names stay as they are in every language. `<ID>` is the real task ID.

## Opening and the teaching question

### EN

> `.pm/` is now in your project: a folder where your tasks, decisions and session notes live as plain text files. I write and keep those records up to date; you decide the work. Now we fit it to your project and finish one small, real job from your project together.
>
> While we work, how should I explain the project-management side? This choice sets how I work with you; you can change it any time.
>
> 1. **Short hint** (recommended): I do the work. The first time something new comes up, for example when I open the first task, I say in one sentence what it is and carry on. I explain the same thing at most twice. Pick this if you want to get to know project management gradually, while the work goes on.
> 2. **Try together**: when something new comes up, I leave the step to you and guide you. You never type commands; for example, when we open a task, you answer "when this is done, what will be true?" and I record it. It is slower, but you see better how the system works. Pick this if you really want to understand how it works.
> 3. **Off**: I don't explain, I just do the work. I still ask you before I change anything in your files. Pick this if you already know things like tasks, the board and decision files.
>
> Type 1, 2 or 3; if you don't answer, I go with 1. Unless you pick Off, we do the first job together: it is the fastest way to see the system. Any time you can say "stop teaching", "explain X" or "I already know X".

### TR

> Projende artık `.pm/` klasörü var: görevlerin, kararların ve oturum notların orada düz metin dosyaları olarak duruyor. Bu kayıtları ben yazıp güncel tutuyorum; işe sen karar veriyorsun. Şimdi bunu projene göre ayarlayıp projenden küçük, gerçek bir işi birlikte bitireceğiz.
>
> Çalışırken proje yönetimi tarafını nasıl anlatayım? Bu seçim, seninle nasıl çalışacağımı belirler; istediğin an değiştirebilirsin.
>
> 1. **Kısa ipucu** (önerilen): İşi ben yaparım. Yeni bir şey ilk kez çıktığında, mesela ilk görevi açtığımda, ne olduğunu tek cümleyle söyler ve işe devam ederim. Aynı şeyi en fazla iki kez anlatırım. Proje yönetimini iş yaparken yavaş yavaş tanımak istiyorsan bunu seç.
> 2. **Birlikte dene**: Yeni bir şey çıktığında adımı sana bırakır, yol gösteririm. Komut yazmazsın; örneğin bir görev açarken "bu iş bittiğinde ne değişmiş ya da çalışıyor olacak?" sorusunu sen cevaplarsın, ben kaydederim. Daha yavaş ilerler ama sistemin nasıl çalıştığını daha iyi görürsün. İşin mantığını gerçekten anlamak istiyorsan bunu seç.
> 3. **Kapalı**: Açıklama yapmam, yalnız işi yaparım. Dosyalarında bir şeyi değiştirmeden önce yine sana sorarım. Görev, pano ve karar dosyası gibi şeyleri zaten biliyorsan bunu seç.
>
> 1, 2 ya da 3 yaz; cevap vermezsen 1 ile giderim. Kapalı'yı seçmezsen ilk işi birlikte yaparız, sistemi en hızlı böyle görürsün. İstediğin an "anlatmayı bırak", "X'i açıkla" ya da "X'i biliyorum" diyebilirsin.

## The first three hints

Each comes after the action, as the last paragraph of the reply that did it.

**task**: when the first task is created, after its ID.

- EN: I opened a task for this (<ID>): one file that says what we are doing and what counts as done, so the next session continues from it, not from this chat.
- TR: Bunun için bir görev açtım (<ID>): ne yaptığımızı ve işin ne zaman bitmiş sayılacağını yazan tek bir dosya; sonraki oturum bu sohbetten değil, doğrudan o dosyadan devam eder.

**board**: the first time two tasks exist, or the user asks what is left; not before.

- EN: Every task sits on a board and moves through the columns Ready, Active and Done. Say "show the board" if you want to look; keeping it current is my job.
- TR: Her görev bir panoda durur ve Ready, Active, Done sütunları arasında ilerler. Bakmak istersen "panoyu göster" de; güncel tutmak benim işim.

**resume**: at the close of the first session, with the prompt for the next one.

- EN: Next time, open this folder and say "continue". I read the task's `Next:` line and git first, not this chat, so nothing is lost.
- TR: Bir dahaki sefere bu klasörü açıp "devam" demen yeter. Bu sohbeti değil, önce görevin `Next:` satırını ve git durumunu okurum; böylece hiçbir şey kaybolmaz.

## The task moment in try-together mode

Before the first task is created:

- EN: We open a task for this: one file that says what we are doing and what counts as done, like the setup task I opened earlier. Give me one sentence: when this is done, what will be true? I open the task with it.
- TR: Bu iş için bir görev açacağız: ne yaptığımızı ve işin ne zaman bitmiş sayılacağını yazan tek bir dosya; az önce açtığım kurulum görevi gibi. Tek bir cümleyle söyle: bu iş bittiğinde ne değişmiş ya da çalışıyor olacak? Görevi o cümleyle açacağım.

After it is created with that sentence as its acceptance criterion, show the ID and the line, then:

- EN: This is your criterion. When the work is done, we check it against this and close the task.
- TR: Bu senin kabul ölçütün. İş bitince sonucu buna göre kontrol edip görevi kapatacağız.

## What you can say

At the end of `/pm-setup`, after the resume hint (or alone when the mode is off), as written:

- EN: From now on you can just say: "continue" (where we are, then on), "what next?" (the next job), "show the board" (the task board opens), "explain <word>" (a plain answer) or "stop teaching".
- TR: Bundan sonra şunları demen yeter: "devam" (nerede kaldığımız, sonra devam), "sırada ne var?" (sıradaki iş), "panoyu göster" (görev panosu açılır), "<kelime> nedir?" (sade bir cevap) ya da "anlatmayı bırak".

## When a step the user did becomes known

- EN: You wrote the task's done-condition yourself, so I stop explaining tasks. Say "explain tasks" if you want it back.
- TR: Görevin bitiş ölçütünü kendin yazdın, bu yüzden artık görevlerin ne olduğunu anlatmayacağım. Tekrar anlatmamı istersen "görevleri açıkla" demen yeter.

For another concept, the same sentence with that step and that concept.
