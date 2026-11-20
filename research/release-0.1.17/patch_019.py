"""Правки выпуска 0.1.9 (И-029): наблюдатель выведен из сравнения. Только тексты."""

SAME_OLD = r"""    for key in _CRITICAL:
        if key == 'environment':
            if dict(a[key]) != dict(b[key]):
                return False
        elif a[key] != b[key]:
            return False"""

SAME_NEW = r"""    for key in _CRITICAL:
        if key == 'environment':
            # 0.1.9: наблюдатель (редактор, расширение, версии, профиль) — происхождение записи,
            # как место улики в 0.1.5. Две среды видят одно событие — это одно наблюдение.
            for part in CONDITIONS:
                if str(a[key].get(part)) != str(b[key].get(part)):
                    return False
        elif a[key] != b[key]:
            return False"""

NOTE_OLD = r"""            p.notes.append(f'Наблюдение совпадает с уже записанным (запись {match}); новая запись не создаётся.')"""

NOTE_NEW = r"""            p.notes.append(f'Наблюдение совпадает с уже записанным (запись {match}); новая запись не создаётся. '
                           'Наблюдатель (редактор, расширение, версии) не сравнивается.')"""

SORT_OLD = r"""        for d in sorted(root.iterdir()):"""

SORT_NEW = r"""        def _order(folder):
            # 0.1.9: порядок по версии, а не по строке: иначе 0.1.10 встаёт перед 0.1.9.
            return tuple(map(int, folder.name.split('.'))) if SEV.fullmatch(folder.name) else (0,)
        for d in sorted(root.iterdir(), key=_order):"""

CONSTANTS = r"""# --- 0.1.9: наблюдатель отделён от условий (И-029, решение владельца Б) ------------------
# Условия наблюдения сравниваются точно, как и прежде. Наблюдатель — редактор, расширение, их версии и
# профиль — это происхождение записи, а не её содержание: он выведен из сравнения так же, как место
# улики в 0.1.5. Причина измерена стендом И-028: одно событие, увиденное Kilo и Copilot, давало две
# записи, потому что environment сравнивался целиком.
CONDITIONS = ('os', 'mode', 'model', 'permissions')
OBSERVER = ('editor', 'editor_version', 'extension', 'extension_version', 'profile')


"""

TEST_019 = r"""
    @case('X32', 'Наблюдатель выведен из сравнения: одно событие под двумя расширениями — одна запись.')
    def test_55_observer_not_compared(self):
        self.install();self.apply(dict(op='connect'))
        env=dict(os='linux',editor='vscode',editor_version='1.105',extension='kilo.kilo-code',
                 extension_version='5.0',mode='agent',model='synthetic',profile='default',permissions='read-write')
        def obs(**changes):
            e=dict(env);e.update(changes)
            return dict(case='сборка',level=1,conditions='Проект в VS Code',expected='Сборка проходит.',
                        actual='Сборка прошла.',status='pass',evidence='tests.log, строка 12',
                        limits='Только синтетические данные.',environment=e)
        self.apply(dict(op='record_check',observation=obs()))
        self.apply(dict(op='record_check',observation=obs(extension='github.copilot')))
        self.assertEqual(len(self.call('status')['observations']),1)
        self.apply(dict(op='record_check',observation=obs(editor='cursor',extension_version='2.7',profile='ci')))
        self.assertEqual(len(self.call('status')['observations']),1)
        for part,value in (('os','windows'),('mode','chat'),('model','other'),('permissions','read-only')):
            self.apply(dict(op='record_check',observation=obs(**{part:value})))
        self.assertEqual(len(self.call('status')['observations']),5)
        missing=obs();missing['environment'].pop('extension')
        self.assertRefused('fields',self.preview,dict(op='record_check',observation=missing))
"""

TEST_019B = r"""
    @case('X33', 'Каталог выпусков упорядочен по версии, а не по строке: 0.1.10 после 0.1.9.')
    def test_56_version_order(self):
        import json as _json
        self.install()
        kit=self.lab/'releases'
        name='0.1.10'
        (kit/name).mkdir()
        data=_json.loads((kit/BASE_VERSION/'manifest.json').read_bytes().decode('utf-8'))
        data['base_version']=name
        (kit/name/'manifest.json').write_bytes((_json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        names=[r['version'] for r in self.call('updates')['local_candidates']]
        self.assertEqual(names, sorted(names, key=lambda v: tuple(map(int, v.split('.')))))
        self.assertEqual(names[-2:], ['0.1.9','0.1.10'])
"""

PROTOCOL_019 = """

Наблюдатель отделён от условий. Поле `environment` делится на две части: условия — `os`, `mode`, `model`, `permissions` — и наблюдатель — `editor`, `editor_version`, `extension`, `extension_version`, `profile`. Условия сравниваются точно, как и раньше: другая операционная система, другой режим, другая модель или другие права — другое наблюдение. Наблюдатель не сравнивается вовсе: это происхождение записи, как место улики, снятое в 0.1.5. Так два расширения, увидевшие одно событие, дают одно наблюдение, а не два. Все девять полей `environment` по-прежнему обязательны: наблюдение без расширения или без модели не принимается, потому что происхождение записи должно быть указано, даже если оно не участвует в сравнении."""

README_019 = """
## Что изменилось в 0.1.9

`environment` разделён: условия (`os`, `mode`, `model`, `permissions`) сравниваются точно, наблюдатель (`editor`, `editor_version`, `extension`, `extension_version`, `profile`) выведен из сравнения так же, как место улики в 0.1.5. Причина измерена в И-028: одно событие, увиденное Kilo и Copilot в одном проекте, давало две записи. Теперь оно даёт одну, а шесть поочерёдных ходов двух сред — одну запись вместо двух. Все девять полей обязательны по-прежнему: происхождение указывается, но не сравнивается.
"""
