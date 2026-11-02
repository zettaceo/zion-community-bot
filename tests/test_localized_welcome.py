from __future__ import annotations

import unittest

from zion.telegram_app import localized_welcome


class LocalizedWelcomeTests(unittest.TestCase):
    def test_member_language_selects_text(self):
        self.assertIn('Bem-vindo(a), Ana', localized_welcome('Ana', 'pt-br'))
        self.assertIn('Welcome, Bob', localized_welcome('Bob', 'en'))
        self.assertIn('Bienvenido(a), Luz', localized_welcome('Luz', 'es'))
        self.assertIn('欢迎你，李', localized_welcome('李', 'zh-hans'))

    def test_unknown_language_falls_back_to_bilingual(self):
        text = localized_welcome('Ivan', 'ru')
        self.assertIn('Bem-vindo(a) / Welcome, Ivan', text)
        self.assertIn('Welcome, Ivan', localized_welcome('Ivan', None))

    def test_every_welcome_warns_about_secrets(self):
        for code in ('pt', 'en', 'es', 'zh', None):
            text = localized_welcome('X', code).lower()
            self.assertTrue(any(w in text for w in ('seed', 'semilla', '助记词')), code)


if __name__ == '__main__':
    unittest.main()
