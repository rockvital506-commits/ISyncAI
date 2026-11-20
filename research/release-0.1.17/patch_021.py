"""Правки выпуска 0.1.11 (И-031): комплект проверяется тем же интерфейсом, которым пользуется владелец.

Три правки программы:
1. Всё, что дописывалось в конец файла после `if __name__ == '__main__'`, переносится до `def main`.
   До 0.1.10 карточка Copilot, заглушки и `CONDITIONS`/`OBSERVER` определялись уже после выхода из
   программы: при запуске файлом их не существовало, и сравнение наблюдений падало с NameError.
2. `adapter` добавляется в список команд консоли: карточка среды перестаёт быть доступной только
   импортом.
3. Консоль читает полезную нагрузку для `adapter` так же, как для `plan`/`apply`; пустой ввод —
   обычный отказ `fields`, а не падение.
"""

GUARD = "if __name__ == '__main__':\n    raise SystemExit(main())\n"
MAIN_DEF = "def main(argv=None):\n"


def relocate(text: str) -> str:
    """Перенести хвост файла (всё после выхода из программы) до объявления main()."""
    assert text.count(GUARD) == 1, 'ожидался один выход из программы'
    cut = text.index(GUARD)
    head, tail = text[:cut], text[cut + len(GUARD):]
    assert tail.strip(), 'переносить нечего: хвост пуст'
    assert MAIN_DEF in head, 'нет объявления main()'
    head = head.replace(MAIN_DEF, tail.strip('\n') + '\n\n\n' + MAIN_DEF, 1)
    return head + GUARD


CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'session', 'plan', 'apply')"

STDIN_OLD = "        data = parse(sys.stdin.buffer.read(MAX_BYTES+1)) if args.command in ('session', 'plan', 'apply') else {}"
STDIN_NEW = """        if args.command in ('session', 'plan', 'apply', 'adapter'):
            # 0.1.11: adapter принимает {"name": ...} тем же способом, что plan и apply.
            raw = sys.stdin.buffer.read(MAX_BYTES+1)
            data = parse(raw) if raw.strip() else {}
        else:
            data = {}"""

TEST_021 = r"""
    @case('X35', 'Карточка среды выдаётся из консоли; без имени и с неизвестным именем — отказ.',
          'Проверяется доступность карточки через опубликованную команду, а не через импорт.')
    def test_58_adapter_cli(self):
        self.install()
        rc,card=self.cli('adapter',dict(name='kilo'))
        self.assertEqual(rc,0);self.assertEqual(card['status'],'documented')
        self.assertEqual(card['priority']['rank'],3);self.assertFalse(card['writes'])
        rc,cop=self.cli('adapter',dict(name='copilot'))
        self.assertEqual((rc,cop['status'],cop['entry_shared']),(0,'documented',False))
        rc,stub=self.cli('adapter',dict(name='claude'))
        self.assertEqual((rc,stub['status'],stub['discovery_proven']),(0,'stub',False))
        self.assertIn('adapter_implemented',stub['not_proven'])
        rc,err=self.cli('adapter',{})
        self.assertEqual((rc,err['error']),(2,'fields'))
        rc,err=self.cli('adapter',dict(name='synthetic-unknown'))
        self.assertEqual((rc,err['error']),(2,'adapter_unknown'))

    @case('X36', 'Запуск файлом и импортом дают один ответ; наблюдатель не сравнивается и из консоли.',
          'Сравнивается поведение двух способов запуска одной программы.')
    def test_59_file_mode_matches_import(self):
        self.install()
        text=CLI.read_text(encoding='utf-8')
        self.assertTrue(text.rstrip().endswith('raise SystemExit(main())'),
                        'после выхода из программы не должно оставаться определений')
        for command in ('status','list','inventory','updates'):
            rc,out=self.cli(command)
            direct=self.call(command)
            self.assertEqual(rc,0,command)
            for key in direct:
                self.assertEqual(out.get(key),direct[key],(command,key))
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        obs=dict(case='синтетическая сборка',level=1,conditions='Синтетический проект',
                 expected='Проверка проходит.',actual='Проверка проходит.',status='pass',
                 evidence='tests.log, строка 12',limits='Только синтетические данные.',environment=dict(env))
        view=self.cli('plan',dict(op='record_check',observation=dict(obs)))[1]
        self.cli('apply',dict(request=dict(op='record_check',observation=dict(obs)),ticket=view['ticket']))
        seen=dict(env,editor='copilot',editor_version='1.300',extension='copilot',
                  extension_version='1.400',profile='pilot')
        same=self.cli('plan',dict(op='record_check',observation=dict(obs,environment=seen)))[1]
        self.assertEqual(same['changes'],[])
        other=self.cli('plan',dict(op='record_check',observation=dict(obs,environment=dict(env,model='synthetic-b'))))[1]
        self.assertEqual(len(other['changes']),1)
"""

PROTOCOL_021 = """

## Консольный контракт (0.1.11)

Комплект проверяется тем же способом, каким им пользуются. Команды `status`, `list`, `history`,
`updates`, `pending`, `operations`, `inventory`, `adapter` читают JSON на стандартном вводе (кроме
`status`/`list`/`history`/`updates`/`pending`/`operations`, которым нагрузка не нужна) и печатают JSON
на стандартный вывод. `adapter` принимает `{"name": "kilo"|"copilot"|"claude"|"cursor"|"antigravity"}`;
без имени — отказ `fields`, с неизвестным именем — отказ `adapter_unknown`. Запуск файлом и импорт
модуля дают один и тот же ответ: все определения находятся до выхода из программы, и после строки
`raise SystemExit(main())` в файле ничего не остаётся.

Это не косметика. До 0.1.11 карточка Copilot, заглушки сред и кортежи `CONDITIONS`/`OBSERVER`
определялись после выхода из программы: при запуске файлом их не существовало, `adapter` отсутствовал
в списке команд, а сравнение наблюдений падало с `NameError`. Собственные испытания этого не видели,
потому что вызывали внутреннюю функцию в том же процессе. Теперь регрессия `X36` сравнивает два
способа запуска и требует, чтобы файл заканчивался выходом из программы.
"""

README_021 = """
## Что изменилось в 0.1.11

Комплект стал проверяемым тем способом, каким им пользуются. Раньше часть определений дописывалась в
конец программы после строки выхода — при запуске файлом карточка Copilot, заглушки сред и сравнение
наблюдений не существовали, а команда `adapter` отсутствовала в консоли вовсе. Собственные испытания
этого не замечали: они вызывали внутреннюю функцию в том же процессе. Теперь `adapter` доступен из
консоли, запуск файлом и импорт дают один ответ, а регрессия проверяет, что после `raise
SystemExit(main())` в файле ничего не остаётся. Правило тождества не менялось.
"""
