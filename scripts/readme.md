## 🔧 Как теперь запускать именно твой кейс

У тебя файл:

.\content\education\01. Стресс.md


Тогда из корня проекта:
```powershell 
cd D:\PROJECT\GPT-SUPPORT
python -m scripts.import_lesson_from_md `
  --md ".\content\education\01. Стресс.md" `
  --dir ".\content\education" `
  --code "stress_intro" `
  --topic "stress" `
  --title "Стресс: базовый модуль" `
  --short "Короткие карточки"
```

**Что произойдёт:**

* скрипт подхватит `.env`,
* возьмёт `DATABASE_URL`, 
* импортирует файл как урок:
  * `lesson.code = "stress_intro"`
  * `topic = "stress"`
  * title = "Стресс: базовый модуль"
  * порежет markdown по ``##`` и создаст `lesson_cards`.