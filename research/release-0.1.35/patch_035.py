"""Правки выпуска 0.1.25 (И-045): частичный сбой — половина записи, половина файла.

§12.3 спрашивает, что видит участник, когда операция оборвалась посередине. До 0.1.25 ответ был
коротким: `health: partial` и список незавершённых операций. Что именно осталось недописанным, какой файл
уже новый, какой ещё старый и чем спасать испорченный, приходилось выяснять восстановлением — то есть
действием, а не чтением.

Что меняется:

1. **Сбой виден до восстановления.** `status` при незавершённой операции отвечает `pending_detail`: для
   каждого файла — класс `before` (старый), `after` (новый) или `foreign` (не опознан), а для `foreign` —
   `salvage` с путём к копии `before` и признаком `intact`. Чтение ничего не пишет (`writes: false`).
2. **План восстановления называет спасение.** В заметках плана `restore` рядом с классификацией появляется
   `salvage` — откуда взять прежнее содержимое испорченного файла, не угадывая путь.
3. **Половина файла не перезаписывается.** Усечённый файл не совпадает ни с `before`, ни с `after` и
   остаётся `foreign`: восстановление возвращает `partial` с `unresolved`, а копия `before` цела и
   проверяема. Данные не теряются, и это сказано до записи.

Схема и операции не меняются: добавлены поля ответов, а не записи.
"""

STATUS_OLD = """    if outstanding and command == 'status':
        return {'health': 'partial', 'pending': outstanding, 'writes': False}"""

STATUS_NEW = """    if outstanding and command == 'status':
        # 0.1.25: частичный сбой виден до восстановления и называет, что осталось и чем спасать (И-045, §12.3).
        detail = []
        for tx in outstanding:
            try:
                j = journal(root, tx)
            except Refusal:
                detail.append({'tx': tx, 'op': None, 'files': {}, 'salvage': {}, 'next': 'restore'})
                continue
            files, salvage = {}, {}
            for path, h in j['files'].items():
                actual = digest(read(root, path))
                files[path] = 'before' if actual == h['before'] else 'after' if actual == h['after'] else 'foreign'
                if files[path] == 'foreign' and h['before'] is not None:
                    copy = OPS + tx + '/before/' + path
                    salvage[path] = {'copy': copy, 'intact': digest(read(root, copy)) == h['before']}
            detail.append({'tx': tx, 'op': j['op'], 'files': files, 'salvage': salvage,
                           'foreign_files_are_never_overwritten': True, 'next': 'restore'})
        return {'health': 'partial', 'pending': outstanding, 'pending_detail': detail, 'writes': False}"""

SALVAGE_OLD = """    p.notes.append({'classification': classes, 'foreign_files_are_never_overwritten': True})"""

SALVAGE_NEW = """    # 0.1.25: план восстановления называет, откуда взять прежнее содержимое неопознанного файла (И-045, §12.3).
    salvage = {path: OPS + tx + '/before/' + path for path, kind in classes.items()
               if kind == 'foreign' and j['files'][path]['before'] is not None}
    p.notes.append({'classification': classes, 'foreign_files_are_never_overwritten': True,
                    'salvage': salvage})"""

TEST_035 = r"""
    @case('X64', 'Половина записи: статус называет, что осталось, восстановление завершает.', '§12.3 (И-045).')
    def test_87_half_write(self):
        self.install(); self.make()
        for n in ('START.md','entry.txt'): (self.kbase/n).write_bytes((self.kbase/n).read_bytes()+b'\nfixture update\n')
        r=self.publish(); t=self.preview(r)['ticket']
        with self.assertRaisesRegex(RuntimeError,'fixture stop'):
            c.apply(self.lab,'A',r,t,_after_write=lambda n: (_ for _ in ()).throw(RuntimeError('fixture stop')) if n==3 else None)
        tx=self.call('pending')['pending'][0]
        status=self.call('status')
        self.assertEqual(status['health'],'partial')
        self.assertFalse(status['writes'])
        self.assertEqual(status['pending'],[tx])
        detail=status['pending_detail'][0]
        self.assertEqual(detail['tx'],tx)
        self.assertTrue(detail['files'])
        self.assertIn('after',detail['files'].values())
        self.assertIn('before',detail['files'].values())
        self.assertNotIn('foreign',detail['files'].values())
        self.assertRefused('pending',self.preview,self.install_req)
        rr=dict(op='restore',tx=tx); view=self.preview(rr)
        self.assertEqual(view['notes'][0]['salvage'],{})
        self.assertEqual(self.apply(rr)['outcome'],'restored')
        self.assertEqual(self.call('pending')['pending'],[])
        self.assertEqual(self.call('status')['health'],'valid')

    @case('X65', 'Половина файла: не перезаписывается, копия «до» цела и названа.', '§12.3 (И-045).')
    def test_88_half_file(self):
        self.install(); self.make()
        for n in ('START.md','entry.txt'): (self.kbase/n).write_bytes((self.kbase/n).read_bytes()+b'\nfixture update\n')
        r=self.publish(); t=self.preview(r)['ticket']
        with self.assertRaisesRegex(RuntimeError,'fixture stop'):
            c.apply(self.lab,'A',r,t,_after_write=lambda n: (_ for _ in ()).throw(RuntimeError('fixture stop')) if n==3 else None)
        tx=self.call('pending')['pending'][0]
        detail=self.call('status')['pending_detail'][0]
        written=[p for p,k in detail['files'].items() if k=='after']
        self.assertTrue(written)
        target=self.a/written[0]
        whole=target.read_bytes()
        target.write_bytes(whole[:max(1,len(whole)//2)])
        half=target.read_bytes()
        status=self.call('status')
        self.assertEqual(status['health'],'partial')
        detail=status['pending_detail'][0]
        self.assertEqual(detail['files'][written[0]],'foreign')
        self.assertTrue(detail['salvage'][written[0]]['intact'])
        copy=self.a/detail['salvage'][written[0]]['copy']
        self.assertEqual(copy.read_bytes()!=half,True)
        rr=dict(op='restore',tx=tx); view=self.preview(rr)
        self.assertEqual(view['notes'][0]['salvage'][written[0]],detail['salvage'][written[0]]['copy'])
        out=self.apply(rr)
        self.assertEqual(out['outcome'],'partial')
        self.assertIn(written[0],out['unresolved'])
        self.assertEqual(target.read_bytes(),half)
        target.write_bytes(copy.read_bytes())
        self.assertEqual(self.apply(rr)['outcome'],'restored')
        self.assertEqual(self.call('status')['health'],'valid')
"""

PROTOCOL_035 = """

## Частичный сбой (0.1.25)

Когда операция обрывается посередине, комплект отвечает состоянием, а не догадкой. `{"command": "status"}`
при незавершённой операции возвращает `health: partial`, `pending` со списком операций и `pending_detail`:
для каждого файла — класс `before` (старый), `after` (новый) или `foreign` (не опознан), а для `foreign` —
`salvage` с путём к копии `before` и признаком `intact`. Чтение ничего не пишет.

**Восстановление по шагам.** `{"op": "restore", "tx": "…"}` возвращает `restored`, если все файлы опознаны,
и `partial` со списком `unresolved`, если нет. Заметки плана называют `salvage` — откуда взять прежнее
содержимое неопознанного файла. Половина файла (усечённая запись) не совпадает ни с одной стороной и остаётся
`foreign`: комплект её не перезаписывает, а копия `before` цела и проверяема.

**Новая работа ждёт.** Пока операция не завершена, любая другая отклоняется кодом `pending`: половина записи
не смешивается со следующей.
"""

README_035 = """
## Что изменилось в 0.1.25

Частичный сбой стал виден до восстановления: `status` при незавершённой операции отдаёт `pending_detail` —
класс каждого файла (`before`, `after`, `foreign`), `salvage` с путём к целой копии `before` и `intact`.
План `restore` называет `salvage`, восстановление возвращает `restored` или `partial` с `unresolved`, усечённый
файл не перезаписывается. Пока операция не завершена, новая работа отклоняется кодом `pending`.
"""
