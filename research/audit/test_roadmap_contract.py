#!/usr/bin/env python3
"""Ограниченная механическая проверка ориентира; не оценка понимания агентом."""
from pathlib import Path
import hashlib
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / 'research/kilo/ROADMAP.md'


def validate(text):
    """Проверяет только явные опорные формулировки, не все возможные противоречия."""
    sections = {
        'authority': ('## 0. Как пользоваться и что главнее', '## 1. Итог:'),
        'goal': ('## 1. Итог:', '## 2. Области,'),
        'move': ('## 2. Области,', '## 3. Два режима'),
        'contexts': ('## 3. Два режима', '## 4. Маршрут'),
        'route': ('## 4. Маршрут', '## 5. Полигон'),
        'test': ('## 5. Полигон', '## 6. Ворота'),
        'gates': ('## 6. Ворота', '## 7. Границы'),
        'bounds': ('## 7. Границы', None),
    }
    required = {
        'authority': ('единый действующий роадмап', 'перед началом', 'после каждой итерации',
                      'SHA-256', 'P10', 'не являются действующей целью', 'исторические файлы'),
        'goal': ('пользователя, проекта и AI-агентов', 'L0/L1/L2', '0.1.36', 'ISAI', 'DomainAgentKit', 'не требует их установки',
                 'Совместимость со старым', 'не требуются'),
        'move': ('L0 — системная область', 'L1 — переносимая область', 'L2 — проектная область',
                 'A1:', 'A2:', 'A3:', 'A4:', 'с удалением исходной записи', 'нельзя удалять источник',
                 'рабочий перенос не объявляется реализованным', 'отдельное подтверждение'),
        'contexts': ('**Проектная задача.**', 'не разработка Kit', 'минимум инструкций Kit',
                     '**Операция Kit.**', 'системные контракты', 'нужны самой операции'),
        'route': ('чистая рабочая установка `not run`', 'полный цикл и перенос `not run`',
                  'действие агентом `not run`'),
        'test': ('новым контекстом', 'не связаны с разработкой', 'Второй проект',
                 'Контроль без выбранной сущности', '`pass`/`fail`/`not run`', 'обычным unit-тестом'),
        'gates': ('**G1:**', '**G2:**', '**G3:**', '**G4:**', '**G5:**', '**G6:**',
                  'Миграция донора не требуется', 'пока обязательные G1–G6 не пройдены'),
        'bounds': ('не отключать sandbox', 'чужие проекты', '`MVP-ROADMAP.md`', 'ROADMAP-IMPLEMENTATION.md'),
    }
    failures = []
    for label, (start, end) in sections.items():
        if text.count(start) != 1 or (end is not None and text.count(end) != 1):
            failures.append(label + ':section')
            continue
        begin = text.index(start)
        finish = len(text) if end is None else text.index(end)
        if finish <= begin:
            failures.append(label + ':order')
            continue
        section = text[begin:finish]
        for marker in required[label]:
            if marker not in section:
                failures.append(label + ':' + marker)
    # Узкий список ранее испытанных противоречий. Совпадение строки может быть ложным
    # срабатыванием (например, цитата), отсутствие совпадения не доказывает смысла.
    forbidden = ('при перемещении обязательно сохраняйте исходную запись.',
                 'миграция 0.1.36 обязательна для выпуска.',
                 'чистый агент уже доказал соблюдение во всех средах.')
    lower = text.lower()
    for index, phrase in enumerate(forbidden, 1):
        if phrase in lower:
            failures.append('known_contradiction:' + str(index))
    return failures


class RoadmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = ROADMAP.read_text(encoding='utf-8')

    def test_explicit_anchors(self):
        self.assertIn('**Версия роадмапа:** `3.1.0`', self.text[:500])
        self.assertEqual(validate(self.text), [])

    def test_missing_or_changed_essential_anchor_detected(self):
        markers = ('с удалением исходной записи', 'нельзя удалять источник',
                   'Миграция донора не требуется', 'не связаны с разработкой',
                   'после каждой итерации', 'DomainAgentKit', 'обычным unit-тестом')
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertGreaterEqual(self.text.count(marker), 1)
                self.assertTrue(validate(self.text.replace(marker, '[удалено]')))

    def test_three_known_contradictions_detected(self):
        examples = ('При перемещении обязательно сохраняйте исходную запись.',
                    'Миграция 0.1.36 обязательна для выпуска.',
                    'Чистый агент уже доказал соблюдение во всех средах.')
        for i, example in enumerate(examples, 1):
            with self.subTest(example=example):
                self.assertIn('known_contradiction:' + str(i), validate(self.text + '\n' + example))

    def test_reminder_and_deferral_are_explicit(self):
        self.assertIn('напомнить владельцу предоставить', self.text)
        self.assertIn('отдельного агента с чистым контекстом в Arena', self.text)
        self.assertIn('не автоматическое уведомление вне активного диалога', self.text)

    def test_reordered_sections_detected(self):
        mutated = self.text.replace('## 2. Области,', '## 9. Области,')
        self.assertTrue(validate(mutated))

    def test_history_is_explicitly_distinguished(self):
        for rel in ('research/README.md','research/kilo/README.md','research/kilo/MVP-ROADMAP.md',
                    'research/kilo/VISION-END-STATE.md','research/kilo/TARGETS.md',
                    'research/kilo/ROADMAP-PROTOCOL.md','research/kilo/KIT-MVP-ANALYSIS.md',
                    'research/kilo/GAP-RENDER.md','research/kilo/DECISION-ROADMAP.md'):
            with self.subTest(path=rel):
                content = (ROOT / rel).read_text(encoding='utf-8')
                self.assertIn('ROADMAP.md', content[:700])
                self.assertIn('3.1.0', content[:700])

    def test_historical_strategy_and_roadmap_bytes_unchanged(self):
        for name, expected in [('research/STRATEGY.md','0360a91a9797ee69c63837cae20bf484332e999514e2bfa567cf56b2ce99b248'),
                               ('research/ROADMAP.md','1fb5f540e92b69ee71dc100c8969b9441341852b5df079cd1109abdef4c9d46d')]:
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), expected)

    def test_new_g5_and_transfer_in_vision_and_targets(self):
        vision=(ROOT/'research/kilo/VISION-END-STATE.md').read_text(encoding='utf-8')
        targets=(ROOT/'research/kilo/TARGETS.md').read_text(encoding='utf-8')
        for content in (vision, targets):
            self.assertIn('удалением источника', content)
            self.assertIn('обновление собственного Kit', content)
        self.assertIn('миграция донора не требуется',vision)
        self.assertNotIn('миграция 0.1.36→0.2.0',targets)

    def test_selected_product_name_and_history_remain_distinct(self):
        self.assertTrue(self.text.startswith('# Действующий роадмап DomainAgentKit\n'))
        for marker in ('историческим именем AgentContractKit',
                       'Ранний код текущего кандидата также', 'не превращение кандидата в донорский релиз',
                       'не меняет пути, интерфейсы, подписи, формат или номера версий'):
            self.assertIn(marker, self.text)
        questions=(ROOT/'research/kilo/roadmap-evaluation/QUESTIONS.md').read_text(encoding='utf-8')
        rubric=(ROOT/'research/kilo/roadmap-evaluation/RUBRIC.md').read_text(encoding='utf-8')
        self.assertIn('Как называется конечная система', questions)
        self.assertIn('Текущее имя DomainAgentKit', rubric)

    def test_iteration_plan_keeps_required_boundaries(self):
        plan = (ROOT/'research/kilo/ROADMAP-ITERATIONS.md').read_text(encoding='utf-8')
        self.assertIn('ROADMAP-ITERATIONS.md', self.text)
        for n in range(1, 21):
            self.assertIn('| D%02d |' % n, plan)
        for marker in ('с удалением источника', 'P00 → П1…П8', 'одна ячейка среда × операция',
                       'Миграция донора не обязательна', 'чистого агента Arena', 'не заменяет ворота'):
            self.assertIn(marker, plan if marker != 'не заменяет ворота' else
                          (ROOT/'research/kilo/roadmap-evaluation/RUBRIC.md').read_text(encoding='utf-8'))
        self.assertIn('ROADMAP-ITERATIONS.md', (ROOT/'research/kilo/roadmap-evaluation/PROTOCOL.md').read_text(encoding='utf-8'))

    def test_every_gate_named_once(self):
        for n in range(1,7): self.assertEqual(len(re.findall(r'\*\*G'+str(n)+r':\*\*',self.text)),1)

    def test_protocol_separates_questions_from_private_rubric(self):
        base=ROOT/'research/kilo/roadmap-evaluation'
        protocol=(base/'PROTOCOL.md').read_text(encoding='utf-8')
        questions=(base/'QUESTIONS.md').read_text(encoding='utf-8')
        rubric=(base/'RUBRIC.md').read_text(encoding='utf-8')
        self.assertIn('Статус: `not run`',protocol)
        self.assertIn('Не копировать этот протокол, `RUBRIC.md`',protocol)
        self.assertEqual(len(re.findall(r'(?m)^\d+\.',questions)),12)
        self.assertEqual(len(re.findall(r'(?m)^\d+\.',rubric)),12)
        self.assertNotIn('Закрытая шкала',questions)
        self.assertIn('историческая матрица',protocol)

    def test_fixture_contains_only_declared_documents_without_answer_key(self):
        sources = ['research/README.md', 'research/STRATEGY.md', 'research/ROADMAP.md',
                   'research/strategy/COMPATIBILITY.json', 'research/kilo/ROADMAP.md',
                   'research/kilo/ROADMAP-ITERATIONS.md', 'research/kilo/README.md', 'research/kilo/VISION-END-STATE.md',
                   'research/kilo/TARGETS.md', 'research/kilo/ROADMAP-PROTOCOL.md',
                   'research/kilo/MVP-ROADMAP.md']
        with tempfile.TemporaryDirectory(prefix='roadmap-fixture-') as name:
            dest = Path(name)
            for rel in sources:
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / rel).read_bytes())
            questions = dest / 'research/kilo/QUESTIONS.md'
            questions.write_bytes((ROOT/'research/kilo/roadmap-evaluation/QUESTIONS.md').read_bytes())
            actual = {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}
            self.assertEqual(actual, set(sources) | {'research/kilo/QUESTIONS.md'})
            self.assertFalse((dest/'research/kilo/roadmap-evaluation/RUBRIC.md').exists())
            self.assertFalse((dest/'kit').exists())
            self.assertEqual((dest/'research/kilo/ROADMAP.md').read_bytes(), ROADMAP.read_bytes())

    def test_unverified_efficacy_is_explicit(self):
        strategy=(ROOT/'research/kilo/REVISION-ROADMAP-IMPLEMENTATION.md').read_text(encoding='utf-8')
        self.assertIn('не подтверждена',strategy)
        self.assertIn('только после выполнения перечисленных заданий',strategy)
        self.assertIn('не выполнять сброс',strategy)


if __name__=='__main__': unittest.main()
