"""Правки выпуска 0.1.10 (И-030): завершающая точка не входит в идентификатор. Только тексты."""

FACTS_OLD = r"""    return frozenset(m.lower() for m in _IDENT.findall(text)) | frozenset(_NUMBER.findall(text))"""

FACTS_NEW = r"""    # 0.1.10: завершающая точка — пунктуация предложения, а не часть идентификатора. Точка внутри
    # имени (`a.b`, `test_build.py`) остаётся значимой: strip снимает только завершающие точки.
    return (frozenset(m.rstrip('.').lower() for m in _IDENT.findall(text))
            | frozenset(_NUMBER.findall(text)))"""

TEST_020 = r"""
    @case('X34', 'Завершающая точка не входит в идентификатор, точка внутри имени — входит.')
    def test_57_trailing_dot(self):
        self.install();self.apply(dict(op='connect'))
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        def obs(actual,case='сборка модуля'):
            return dict(case=case,level=1,conditions='Синтетический проект',expected='Проверка проходит.',
                        actual=actual,status='pass',evidence='tests.log, строка 12',
                        limits='Только синтетические данные.',environment=dict(env))
        self.apply(dict(op='record_check',observation=obs('Падает TypeError в test_build.')))
        self.apply(dict(op='record_check',observation=obs('Падает TypeError в test_build')))
        self.assertEqual(len(self.call('status')['observations']),1)
        self.apply(dict(op='record_check',observation=obs('Разбор файла a.b.')))
        self.apply(dict(op='record_check',observation=obs('Разбор файла a.b')))
        self.assertEqual(len(self.call('status')['observations']),2)
        self.apply(dict(op='record_check',observation=obs('Модуль test_build.py не найден.')))
        self.assertEqual(len(self.call('status')['observations']),3)
        self.apply(dict(op='record_check',observation=obs('Модуль test_build не найден.')))
        self.assertEqual(len(self.call('status')['observations']),4)
        self.apply(dict(op='record_check',observation=obs('Версия v1.0 принята.')))
        self.apply(dict(op='record_check',observation=obs('Версия v1.1 принята.')))
        self.assertEqual(len(self.call('status')['observations']),6)
"""

PROTOCOL_020 = """

Завершающая точка в идентификаторе не считается частью идентификатора. Точка, которой заканчивается предложение, — пунктуация, и она на склейку не влияет: `test_build.` и `test_build` — один и тот же факт, `a.b.` и `a.b` — тоже. Точка внутри имени остаётся значимой: `test_build.py` и `test_build` — разные идентификаторы, как и `v1.0` против `v1.1`. Снимаются только завершающие точки, и ничего больше: дефис, подчёркивание, двоеточие и скобки в идентификатор не входят и без этого. Причина правки измерена в И‑029: пять пар из восьми «та же запись другой формой» не склеивались, потому что точка в конце предложения попадала в набор фактов, и обещание «пунктуация не влияет» для этого случая не выполнялось."""

README_020 = """
## Что изменилось в 0.1.10

Завершающая точка больше не входит в идентификатор: `test_build.` и `test_build` — один факт, а `test_build.py` и `test_build` — по-прежнему разные. Повод измерен в И‑029: пять пар из восьми «та же запись другой формой» не склеивались из-за точки в конце предложения. Правка проверена тремя корпусами: 112 пар, 80 пар И‑029 и журналы.
"""



# X33 в 0.1.9 был записан под конкретную версию; здесь он становится версионно-независимым.
FIX_LINES = [
    ("        name='0.1.10'\n",
     "        major,minor,patch=map(int,BASE_VERSION.split('.'))\n"
     "        name=f'{major}.{minor}.{patch+1}'\n"),
    ("        self.assertEqual(names[-2:], ['0.1.9','0.1.10'])",
     "        self.assertEqual(names[-1], name)\n"
     "        self.assertEqual(names[-2], BASE_VERSION)"),
]
