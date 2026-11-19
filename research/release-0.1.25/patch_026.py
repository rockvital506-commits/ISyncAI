"""Правки выпуска 0.1.16 (И-036): достоверность, уровень 3 — содержимое прочитано и опознано.

Уровень 3 означает «содержимое прочитано». Проверить, что его прочитала **модель**, без живой среды
нельзя. Проверить можно другое и честное: что вход читается комплектом, что он опознан как наш (в нём
есть строка-указатель на `START.md`) и что чужой файл при этом не читается вовсе.

Новая команда `entry {"environment": …}`:

- для собственного входа отдаёт отпечаток, размер, число строк, найденную строку-указатель и превью;
- для чужого входа не читает содержимое: только размер с диска и `content: "not read (foreign)"`;
- всегда несёт `content_proven: false` и раздельные уровни: `3_content_read_by_contract` (измерено) и
  `3_content_read_by_model` (`not run`).

Заглушки отвечают `adapter_stub` — их порядок не сверялся.
"""

ENTRY_COMMAND = """    if command == 'entry':
        # 0.1.16: уровень 3 — что именно прочитает среда и опознан ли это наш вход (И-036).
        exact(payload, 'environment')
        need(not pending(root), 'pending', 'Сначала диагностика незавершённого изменения.')
        review = Review(root, {}, timestamp())
        s, files, _m, _r, _c, _d, _i = read_project(review, None, allow_drift=True,
                                                    allow_conflict=True)
        name = payload['environment']
        map_ = discovery(root, name)
        path = map_['chosen']
        line = files['entry.txt'].decode('utf-8').strip()
        levels = {'1_file_present': 'pass' if path else 'fail', '2_environment_found': 'not run',
                  '3_content_read_by_contract': 'not run', '3_content_read_by_model': 'not run',
                  '5_behavior_repeatable': 'not run'}
        if path is None:
            levels['1_file_present'] = 'fail'
            return {'environment': name, 'path': None, 'owned': False, 'foreign': False, 'read': None,
                    'levels': levels, 'content_proven': False, 'writes': False,
                    'note': 'Входа нет: читать нечего.'}
        owned = s['adapter'] is not None and path == ENTRY
        if not owned:
            levels['3_content_read_by_contract'] = 'not run'
            return {'environment': name, 'path': path, 'owned': False, 'foreign': True, 'read': None,
                    'bytes': safe(root, path).lstat().st_size, 'content': 'not read (foreign)',
                    'levels': levels, 'content_proven': False, 'writes': False,
                    'note': 'Это не вход комплекта: содержимое не читалось и не будет. Второй реестр '
                            'не создаётся, чужой файл не перезаписывается.'}
        raw = read(root, path, required=True)
        text = raw.decode('utf-8')
        levels['3_content_read_by_contract'] = 'pass'
        return {'environment': name, 'path': path, 'owned': True, 'foreign': False,
                'read': {'path': path, 'bytes': len(raw), 'sha256': digest(raw),
                         'lines': text.count('\\n') + (0 if text.endswith('\\n') else 1)},
                'marker_found': line in text, 'points_to': '.agent-contract/base/START.md' if line in text else None,
                'preview': text[:200],
                'levels': levels, 'content_proven': False, 'writes': False,
                'note': 'Содержимое прочитал комплект, а не модель: уровень 3 в смысле «модель прочитала» '
                        'остаётся not run.'}
"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'plan', 'apply')"

STDIN_OLD = "        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery'):"
STDIN_NEW = "        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry'):"

TEST_026 = r"""
    @case('X46', 'Уровень 3: собственный вход прочитан и опознан, но модель его не читала.', 'И-036.')
    def test_69_entry(self):
        self.install();self.apply(dict(op='connect'))
        card=self.call('entry',dict(environment='kilo'))
        self.assertTrue(card['owned']);self.assertFalse(card['foreign'])
        self.assertFalse(card['writes']);self.assertFalse(card['content_proven'])
        raw=(self.a/'AGENTS.md').read_bytes()
        self.assertEqual(card['read']['sha256'],c.digest(raw))
        self.assertEqual(card['read']['bytes'],len(raw))
        self.assertTrue(card['marker_found'])
        self.assertEqual(card['points_to'],'.agent-contract/base/START.md')
        self.assertTrue(card['preview'].strip())
        self.assertEqual(card['levels']['3_content_read_by_contract'],'pass')
        self.assertEqual(card['levels']['3_content_read_by_model'],'not run')
        self.assertEqual(card['levels']['2_environment_found'],'not run')
        self.assertRefused('adapter_stub',self.call,'entry',dict(environment='claude'))

    @case('X47', 'Уровень 3: чужой вход не читается, но и не мешает.', 'И-036; P2.')
    def test_70_entry_foreign(self):
        foreign='# инструкции проекта\n'
        (self.a/'AGENTS.md').write_text(foreign,encoding='utf-8')
        self.install()
        card=self.call('entry',dict(environment='kilo'))
        self.assertFalse(card['owned']);self.assertTrue(card['foreign'])
        self.assertIsNone(card['read'])
        self.assertEqual(card['content'],'not read (foreign)')
        self.assertEqual(card['levels']['3_content_read_by_contract'],'not run')
        self.assertEqual(card['bytes'],len(foreign.encode()))
        self.assertEqual((self.a/'AGENTS.md').read_text(encoding='utf-8'),foreign)
        (self.a/'.github').mkdir()
        (self.a/'.github/copilot-instructions.md').write_text('# copilot\n',encoding='utf-8')
        other=self.call('entry',dict(environment='copilot'))
        self.assertTrue(other['foreign']);self.assertIsNone(other['read'])
        self.assertEqual(other['path'],'.github/copilot-instructions.md')
        (self.a/'AGENTS.md').unlink()
        (self.a/'.github/copilot-instructions.md').unlink()
        gone=self.call('entry',dict(environment='kilo'))
        self.assertIsNone(gone['path']);self.assertEqual(gone['levels']['1_file_present'],'fail')
"""

PROTOCOL_026 = """

## Содержимое входа (0.1.16)

`entry {"environment": "kilo"}` отвечает, что именно прочитает среда и опознан ли этот файл как вход
комплекта. Для собственного входа — отпечаток, размер, число строк, найденная строка-указатель на
`START.md` и короткое превью. Для чужого (`AGENTS.md`, который комплект не создавал, или
`.github/copilot-instructions.md`) — только размер с диска и `content: "not read (foreign)"`: содержимое
не читается, второй реестр не создаётся.

Уровни названы раздельно: `3_content_read_by_contract` — измерено, `3_content_read_by_model` — `not run`.
Карточка всегда несёт `content_proven: false`: комплект не выдаёт своё чтение за чтение моделью.
"""

README_026 = """
## Что изменилось в 0.1.16

Команда `entry` показывает, что именно прочитает среда и опознан ли файл как вход комплекта: отпечаток,
размер, строки, найденная строка-указатель и превью — для своего входа; для чужого только размер и
пометка «не читалось». Уровень 3 назван раздельно: `3_content_read_by_contract` измерен,
`3_content_read_by_model` остаётся `not run`. Правило и операции не менялись.
"""
