"""Правки выпуска 0.1.24 (И-044): миграция при неизвестной версии.

§12.2 спрашивает, что происходит, когда проект пришёл с версией схемы, которой комплект не знает. До
0.1.24 ответ был общим: «схема неизвестна или требует отдельной миграции» — один код на три разных
случая (не число, чужая версия, своя версия в неверной форме), без того, что нашлось, без того, что
поддерживается, и без пути назад.

Что меняется:

1. **Неизвестная версия — отдельный код.** `unknown_schema` с деталями `{found, supported, migrate,
   recover}`: что нашли, что поддерживаем, возможна ли миграция, чем вернуться. Данные не переписаны —
   отказ выдаётся до любой записи.
2. **Миграция не угадывает.** `migrate` на версии, отличной от 0 и 1, отклоняется тем же кодом: комплект
   не пытается «примерно» прочитать чужую схему.
3. **Путь назад назван честно.** Возврат — копия проекта или файл `before` из журнала операции. Это
   проверяемо: файл `before` существует и равен прежнему состоянию байт в байт, а чтение с неизвестной
   схемой ничего не пишет.

Схема не ужесточается: своя версия 1 читается как прежде, форма отказа уточнена, а не добавлена в данные.
"""

UNKNOWN_SCHEMA_OLD = """    need(isinstance(s, dict) and type(s.get('schema_version')) is int and s['schema_version'] == 1, 'schema', 'Схема проекта неизвестна или требует отдельной миграции.')"""

UNKNOWN_SCHEMA_NEW = """    need(isinstance(s, dict) and type(s.get('schema_version')) is int, 'schema', 'Схема проекта не названа числом.')
    if s['schema_version'] != 1:
        # 0.1.24: неизвестная версия — отказ с ответом «что нашлось и чем вернуться» (И-044, §12.2).
        raise Refusal('unknown_schema',
                      'Схема проекта этой версии неизвестна: данные не переписаны, миграции для неё нет. '
                      'Вернуться к прежнему состоянию можно копией проекта или файлом before из журнала операции.',
                      {'found': s['schema_version'], 'supported': [1], 'migrate': False,
                       'recover': ['копия проекта', 'local/ops/<tx>/before/' + STATE.split('/')[-1]]})"""

LEGACY_OLD = """    exact(s, 'schema_version project_revision next_id entries decisions base adapter retired')
    need(type(s['schema_version']) is int and s['schema_version'] == 0 and type(s['entries']) is list,
         'schema', 'Поддерживается только явно определённый обменный формат 0 → 1.')"""

LEGACY_NEW = """    need(isinstance(s, dict) and type(s.get('schema_version')) is int and s['schema_version'] in (0, 1),
         'unknown_schema', 'Миграция этой версии схемы неизвестна: данные не переписаны, migrate не угадывает.',
         {'found': s.get('schema_version') if isinstance(s, dict) else None, 'supported': [0, 1],
          'migrate': False})
    exact(s, 'schema_version project_revision next_id entries decisions base adapter retired')
    need(s['schema_version'] == 0 and type(s['entries']) is list,
         'schema', 'Миграции подлежит только схема 0; текущая схема уже читается без неё.')"""

CHECK04_OLD = """        self.assertRefused('schema', self.preview, dict(op='connect'))"""

CHECK04_NEW = """        self.assertRefused('unknown_schema', self.preview, dict(op='connect'))"""

TEST_034 = r"""
    @case('X62', 'Неизвестная схема: отказ с ответом, данные не переписаны.', '§12.2 (И-044).')
    def test_85_unknown_schema(self):
        self.install();self.make()
        raw=(self.a/c.STATE).read_bytes()
        self.assertEqual(self.call('status')['health'],'valid')
        (self.a/c.STATE).write_bytes(raw.replace(b'"schema_version": 1',b'"schema_version": 2',1))
        before=snapshot(self.a)
        err=self.assertRefused('unknown_schema',self.call,'status')
        self.assertEqual(err.details['found'],2)
        self.assertEqual(err.details['supported'],[1])
        self.assertFalse(err.details['migrate'])
        self.assertTrue(err.details['recover'])
        self.assertEqual(before,snapshot(self.a))
        self.assertRefused('unknown_schema',self.call,'list')
        self.assertRefused('unknown_schema',self.preview,dict(op='migrate',reason='обновить'))
        self.assertRefused('unknown_schema',self.preview,dict(op='edit',id='P-1',fields=dict(text='иначе'),
                                                             reason='правка'))
        self.assertEqual(before,snapshot(self.a))
        (self.a/c.STATE).write_bytes(raw)
        self.assertEqual(self.call('status')['health'],'valid')

    @case('X63', 'Восстановление без потери: файл «до» из журнала возвращает проект.', '§12.2 (И-044).')
    def test_86_restore_from_journal(self):
        self.install();self.make()
        good=(self.a/c.STATE).read_bytes()
        self.apply(dict(op='edit',id='P-1',fields=dict(text='новый текст'),reason='правка'))
        ops=[o for o in self.call('operations')['operations'] if o['status']=='committed']
        self.assertTrue(ops)
        backup=next(p for p in (self.a/c.OPS/o['tx']/'before'/c.STATE for o in ops)
                    if p.exists() and p.read_bytes()==good)
        (self.a/c.STATE).write_bytes(good.replace(b'"schema_version": 1',b'"schema_version": 2',1))
        self.assertRefused('unknown_schema',self.call,'status')
        (self.a/c.STATE).write_bytes(backup.read_bytes())
        status=self.call('status')
        self.assertEqual(status['health'],'valid')
        self.assertEqual(self.state()['schema_version'],1)
        self.assertEqual(len(self.state()['entries']),1)
        self.assertEqual(self.state()['entries'][0]['text'],'synthetic token')
"""

PROTOCOL_034 = """

## Миграция при неизвестной версии (0.1.24)

**Неизвестная схема — отдельный код.** Если проект пришёл со схемой, которой комплект не знает,
`{"command": "status"}` (и любое чтение) отвечает отказом `unknown_schema` с деталями `{found, supported,
migrate, recover}`: какая версия найдена, какие поддерживаются, возможна ли миграция и чем вернуться.
Данные не переписаны: отказ выдаётся до записи, а чтение проекта остаётся чтением.

**Миграция не угадывает.** `{"op": "migrate", "reason": "…"}` на версии, отличной от 0 и 1, отклоняется тем
же кодом: комплект не пытается прочитать чужую схему «примерно». Миграция поддерживает только 0 → 1.

**Путь назад назван честно.** Возврат — копия проекта или файл `before` из журнала операции:
`.agent-contract/local/ops/<tx>/before/state.json` — это состояние до операции, байт в байт. Комплект не
делает вид, что умеет откатить чужую схему сам.
"""

README_034 = """
## Что изменилось в 0.1.24

Неизвестная версия схемы проекта — отдельный отказ `unknown_schema` с деталями `{found, supported, migrate,
recover}`: что найдено, что поддерживается, возможна ли миграция, чем вернуться. Чтение с такой схемой ничего
не пишет, `migrate` не угадывает и отклоняется тем же кодом, миграция поддерживает только 0 → 1. Путь назад —
копия проекта или `before` из журнала операции, равный прежнему состоянию байт в байт.
"""
