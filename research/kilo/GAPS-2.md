{
  "schema": "kilo-dossier-gaps-2/1",
  "checked": "2026-11-22",
  "note": "Продолжение GAPS.md: конфликты и измерения, найденные после партии 2 скринов, settings.json и новых исследований.",
  "conflicts": [
    {
      "id": "C10",
      "topic": "Пресет «Сначала проверка» против документации о правах по умолчанию",
      "side_a": "S04: большинство инструментов по умолчанию allow; спрашивают .env, external_directory, doom_loop",
      "side_b": "observed_ui 2026-11-22: bash ask, edit ask, read allow с .env deny, task ask",
      "explanation": "Наблюдаемые значения — не заводские, а пресет «Сначала проверка» (Review first). Документация описывает заводские значения, UI показывает выбранный пресет.",
      "resolution": "Обе записи верны для своих условий. Перед сценарием нужно знать пресет, а не «права по умолчанию».",
      "status": "explained"
    },
    {
      "id": "C11",
      "topic": "`autoApprove.enabled=false` против разрешающих уровней read/glob/list",
      "side_a": "мастер-переключатель автоодобрения выключен",
      "side_b": "read, glob, list, skill, lsp, websearch, webfetch = Разрешить",
      "why_it_matters": "Фраза «автоодобрение выключено» не описывает фактическое поведение чтения",
      "how_to_settle": "E10: при выключенном мастере выполнить чтение и glob и посмотреть, был ли запрос",
      "status": "open"
    },
    {
      "id": "C12",
      "topic": "`.env`: спросить или отклонить",
      "side_a": "документация: чтение .env → ask",
      "side_b": "UI: *.env и .env* → deny",
      "why_it_matters": "Разная строгость меняет сценарий «секреты недоступны»",
      "how_to_settle": "E11: попытка чтения .env",
      "status": "open"
    },
    {
      "id": "C13",
      "topic": "Откуда берутся права: пресет или kilo.jsonc",
      "side_a": "«О Kilo Code»: правила автоутверждения хранятся в конфигурации CLI",
      "side_b": "UI Auto-Approve показывает значения, которые можно менять",
      "why_it_matters": "Если правила в CLI-конфиге, то их можно прочитать файлом и проверить; иначе только через UI",
      "how_to_settle": "открыть Local Config и Global Config по кнопкам в заголовке настроек",
      "status": "open"
    },
    {
      "id": "C14",
      "topic": "Автодополнение: UI показывает «включено», settings.json — false",
      "side_a": "скрин 1046xx: «Включить автодополнение чата» включено",
      "side_b": "settings.json: kilo-code.new.autocomplete.enableChatAutocomplete = false",
      "why_it_matters": "Расхождение между слоями настроек: профиль пользователя против рабочего. Без учёта можно списать отсутствие подсказок на Kilo",
      "how_to_settle": "E17: сравнить раздел «Автодополнение» в UI и значение в settings.json на одном окне",
      "status": "open_observed_ui"
    }
  ],
  "measurements": [
    {
      "id": "E10",
      "question": "Что сильнее: мастер автоодобрения или разрешение инструмента?",
      "state": "ST-ENV-1",
      "criterion": "был ли запрос при чтении",
      "next": "И‑122"
    },
    {
      "id": "E11",
      "question": "Чтение .env: запрос или отказ?",
      "state": "ST-ENV-1",
      "criterion": "наблюдаемая реакция",
      "next": "И‑122"
    },
    {
      "id": "E12",
      "question": "Есть ли в проекте kilo.jsonc, AGENTS.md, .kilo/rules?",
      "state": "ST-ENV-1",
      "criterion": "перечислить найденные пути без содержимого",
      "next": "И‑122"
    },
    {
      "id": "E13",
      "question": "Что перечислено во вкладке «Правила»?",
      "state": "ST-PROJECT-WIRED",
      "criterion": "список файлов и их область",
      "next": "И‑122"
    },
    {
      "id": "E14",
      "question": "Перечитывает ли Reload Config and Skills правила проекта без перезапуска VS Code?",
      "state": "ST-PROJECT-WIRED",
      "criterion": "появилась ли новая строка правила после reload",
      "next": "И‑122"
    },
    {
      "id": "E15",
      "question": "Применяются ли настройки VS Code (inline-автодополнение выключено) к поведению Kilo?",
      "state": "ST-ENV-1",
      "criterion": "появляются ли inline-подсказки Kilo",
      "next": "И‑122"
    },
    {
      "id": "E16",
      "question": "Что видно при выключенном провайдере и модели kilo-auto/free?",
      "state": "ST-ENV-1",
      "criterion": "можно ли начать сеанс, какая ошибка",
      "next": "И‑122",
      "note": "блокирует все прогоны, если сеанс не стартует"
    },
    {
      "id": "E17",
      "question": "Почему UI и settings.json расходятся по автодополнению?",
      "state": "ST-ENV-1",
      "criterion": "сравнение двух источников на одном окне",
      "next": "И‑122"
    }
  ],
  "hard_blockers_for_iteration_122": [
    "ни один провайдер не подключён: сеанс агента может не начаться (E16)",
    "нет подтверждённого признака чтения правил: нужен E13/E14",
    "VSCode-настройки не управляют входом агента: нужен E15, иначе сценарий путает слои"
  ],
  "resolved_by_evidence": [
    {
      "claim": "старшинство AGENTS.md против instructions проекта",
      "status": "not run",
      "note": "только документация; Д2 не подтверждена"
    }
  ]
}
