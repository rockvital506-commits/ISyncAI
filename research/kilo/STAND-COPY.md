# Стенд: какие папки копировать в новый проект и как

**Короткий ответ:** для проб И‑122 **не нужно** копировать весь репозиторий ISyncAI. Нужны только
файлы проекта, с которыми агенту предстоит работать, и — отдельно — короткий указатель на Kit,
если проба проверяет именно точку входа.

**Почему не весь репозиторий:**

1. Проба должна быть маленькой: чем меньше файлов, тем понятнее, что прочитал агент.
2. В репозитории есть 31 файл досье и 20 итераций — это шум, который сам влияет на контекст.
3. Правила `.gitignore` и большие ZIP не нужны для наблюдения чтения.
4. Меньше риск случайно изменить рабочий репозиторий.

---

## 1. Структура стенда

```
D:\kilo-stand-122\          (или любой диск вне репозитория ISyncAI)
├── p1\                     проба П1, П7
│   └── .kilo\rules\canary.md
├── p2\                     пробы П2, П3, П6
│   ├── kilo.jsonc
│   ├── .kilo\rules\canary.md
│   ├── AGENTS.md
│   └── sample.txt
├── p3\                     пробы П4, П5
│   ├── kilo.jsonc
│   ├── .kilo\agents\reviewer.md
│   └── sample.txt
└── kit-entry\              нужен только для сценария SC-07 (позже)
    ├── entry.txt
    └── START.md
```

Каждая папка — **отдельный проект** в VS Code. Открывать по одной, не всё сразу.

## 2. Что именно копировать

### Минимальный набор (обязательный)

Из репозитория ISyncAI понадобятся **только два файла**, если вы захотите проверить сценарий
«точка входа Kit» (SC‑07, не входит в 8 проб):

| Файл в репозитории | Куда класть | Зачем |
|---|---|---|
| `kit/base/entry.txt` | `kit-entry\entry.txt` | короткий указатель, который обычно читает агент |
| `kit/base/START.md` | `kit-entry\START.md` | §0 — первая страница, ограниченная 4096 байтами |

**Как скопировать в Windows:**

```powershell
# из корня репозитория
$dst = "D:\kilo-stand-122\kit-entry"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "kit\base\entry.txt" $dst
Copy-Item "kit\base\START.md" $dst
```

### Всё остальное создаётся заново, а не копируется

Файлы `kilo.jsonc`, `.kilo/rules/canary.md`, `AGENTS.md`, `.kilo/agents/reviewer.md` **не копируются
из репозитория** — они создаются по шаблонам из `examples/` и `PROBES-GUIDE.md`. Причина: проба
должна видеть ровно то, что мы положили, без наследства.

### Чего копировать НЕ нужно

| Что | Почему |
|---|---|
| `.git\` | проба не про Git; история увеличит шум |
| `research\` | 20 итераций и 31 файл досье — лишний контекст |
| ZIP-архивы печатей | сотни килобайт, не нужны для чтения правил |
| `.env`, ключи | секреты вне проб; в П7 используется демонстрационный `.env` |
| `node_modules`, `.venv` | вес и шум |

## 3. Как создать заготовки (PowerShell, Windows)

```powershell
$root = "D:\kilo-stand-122"
Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
"p1","p2","p3","kit-entry" | ForEach-Object { New-Item -ItemType Directory -Force -Path "$root\$_" | Out-Null }

# П1: канарейка без kilo.jsonc
New-Item -ItemType Directory -Force -Path "$root\p1\.kilo\rules" | Out-Null
Set-Content -Path "$root\p1\.kilo\rules\canary.md" -Value "# Канарейка`n`nСтрока проверки: ZX-41-P1" -Encoding UTF8

# p2: kilo.jsonc + канарейка + чужой AGENTS.md + sample
@'
{
  "$schema": "https://app.kilo.ai/config.json",
  "instructions": [".kilo/rules/*.md"],
  "permission": { "bash": { "*": "ask" }, "edit": { "*": "ask" } },
  "compaction": { "auto": true, "threshold_percent": 60 }
}
'@ | Set-Content -Path "$root\p2\kilo.jsonc" -Encoding UTF8
New-Item -ItemType Directory -Force -Path "$root\p2\.kilo\rules" | Out-Null
Set-Content -Path "$root\p2\.kilo\rules\canary.md" -Value "# Канарейка`n`nСтрока проверки: ZX-41-P2" -Encoding UTF8
Set-Content -Path "$root\p2\AGENTS.md" -Value "# Правила чужого проекта`n`nFOREIGN-122: не менять без разрешения" -Encoding UTF8
Set-Content -Path "$root\p2\sample.txt" -Value "исходный текст" -Encoding UTF8

# p3: агент только на чтение + сужение прав
@'
{
  "$schema": "https://app.kilo.ai/config.json",
  "permission": {
    "bash": { "*": "ask", "git status*": "allow", "git log*": "ask" },
    "edit": { "*": "ask" }
  }
}
'@ | Set-Content -Path "$root\p3\kilo.jsonc" -Encoding UTF8
New-Item -ItemType Directory -Force -Path "$root\p3\.kilo\agents" | Out-Null
@'
---
description: Только чтение, без правок и команд
mode: primary
permission:
  edit: deny
  bash: deny
---
Ты рецензент. Объясняй, но не меняй файлы и не запускай команды.
'@ | Set-Content -Path "$root\p3\.kilo\agents\reviewer.md" -Encoding UTF8
Set-Content -Path "$root\p3\sample.txt" -Value "исходный текст" -Encoding UTF8
```

**Важно:** `Set-Content -Encoding UTF8` в PowerShell 5.1 добавляет BOM. Для Markdown это обычно
безвредно, но если агент не видит русский текст — сохраните без BOM (`-Encoding utf8NoBOM` в PS 7
или через VS Code).

## 4. Проверка стенда до проб (2 минуты)

```powershell
Get-ChildItem -Recurse D:\kilo-stand-122 | Select-Object FullName, Length
Get-FileHash D:\kilo-stand-122\p2\AGENTS.md -Algorithm SHA256
```

- Файлы на месте, длины не нулевые.
- SHA‑256 `AGENTS.md` записан — это исходное значение для П3.
- Ни в одной папке нет `.git`, `node_modules`, `.env` (кроме демонстрационного из П7).

## 5. Почему стенд вне репозитория

| Причина | Следствие |
|---|---|
| агент может изменить файлы | рабочая копия ISyncAI не портится |
| контрольные точки Kilo пишут снимки | не смешиваются с историей проекта |
| пробы повторяемы | `Remove-Item -Recurse` и заново, без остатка |
| изоляция от Git | проба не создаёт коммитов в вашем репозитории |

## 6. Как вернуть изменения после проб

Стенд одноразовый. Если нужно повторить: удалить `D:\kilo-stand-122` и создать заново по §3.
В репозитории ISyncAI за это время ничего не меняется — это и есть цель.
