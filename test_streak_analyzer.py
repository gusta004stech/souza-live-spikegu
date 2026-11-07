"""Testes unitários da lógica de consolidação de streaks.

ATENÇÃO: estes testes usam dados sintéticos e verificam apenas o NOSSO código.
Eles NÃO provam que o TikTok se comporta assim. Isso só se prova em live real
(ver README, teste T3).

Executar:  python -m unittest -v
"""
import unittest

from streak_analyzer import GiftObservation, StreakAnalyzer


def obs(ts, count, end, user="u1", gid="5655", name="Rose", dia=1, streakable=True):
    return GiftObservation(
        ts=ts, user_key=user, gift_id=gid, gift_name=name, diamonds=dia,
        streakable=streakable, repeat_count=count, repeat_end=end,
    )


class StreakAnalyzerTests(unittest.TestCase):
    def test_streak_final_count_comes_from_repeat_end(self):
        a = StreakAnalyzer()
        self.assertIsNone(a.feed(obs(0.0, 1, False)))
        self.assertIsNone(a.feed(obs(0.5, 2, False)))
        self.assertIsNone(a.feed(obs(1.0, 3, False)))
        fin = a.feed(obs(1.5, 3, True))
        self.assertIsNotNone(fin)
        self.assertEqual(fin.count, 3)
        self.assertEqual(fin.ended_by, "repeat_end")
        self.assertEqual(fin.events_seen, 4)
        self.assertEqual(fin.total_diamonds, 3)
        self.assertEqual(fin.anomalies, [])

    def test_naive_sum_shows_double_counting(self):
        a = StreakAnalyzer()
        for i, c in enumerate([1, 2, 3]):
            a.feed(obs(i, c, False))
        fin = a.feed(obs(3, 3, True))
        self.assertEqual(fin.naive_sum, 1 + 2 + 3 + 3)
        self.assertNotEqual(fin.naive_sum, fin.count)

    def test_non_streakable_finalizes_immediately(self):
        a = StreakAnalyzer()
        fin = a.feed(obs(0, 1, True, streakable=False, gid="9", name="Universe", dia=34999))
        self.assertEqual(fin.ended_by, "non_streakable")
        self.assertEqual(fin.count, 1)
        self.assertEqual(fin.total_diamonds, 34999)

    def test_streaks_are_separated_per_user_and_gift(self):
        a = StreakAnalyzer()
        a.feed(obs(0, 1, False, user="u1"))
        a.feed(obs(0, 1, False, user="u2"))
        f1 = a.feed(obs(1, 2, True, user="u1"))
        f2 = a.feed(obs(1, 5, True, user="u2"))
        self.assertEqual((f1.user_key, f1.count), ("u1", 2))
        self.assertEqual((f2.user_key, f2.count), ("u2", 5))

    def test_repeat_end_without_previous_event_is_flagged(self):
        a = StreakAnalyzer()
        fin = a.feed(obs(0, 4, True))
        self.assertEqual(fin.count, 4)
        self.assertIn("repeat_end_sem_evento_parcial_anterior", fin.anomalies)

    def test_stale_streak_is_flushed_with_timeout(self):
        a = StreakAnalyzer(stale_timeout_s=5)
        a.feed(obs(0, 1, False))
        a.feed(obs(1, 2, False))
        self.assertEqual(a.flush_stale(3), [])
        out = a.flush_stale(7)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].ended_by, "timeout")
        self.assertEqual(out[0].count, 2)
        self.assertIn("sem_repeat_end", out[0].anomalies)

    def test_flush_all_on_shutdown(self):
        a = StreakAnalyzer()
        a.feed(obs(0, 7, False))
        out = a.flush_all()
        self.assertEqual(out[0].ended_by, "shutdown")
        self.assertEqual(out[0].count, 7)
        self.assertEqual(a.flush_all(), [])

    def test_count_decrease_is_flagged(self):
        a = StreakAnalyzer()
        a.feed(obs(0, 5, False))
        a.feed(obs(1, 3, False))
        fin = a.feed(obs(2, 3, True))
        self.assertTrue(any(x.startswith("contagem_diminuiu") for x in fin.anomalies))

    def test_unknown_user_key_is_labeled(self):
        a = StreakAnalyzer()
        fin = a.feed(obs(0, 1, True, user="", streakable=False))
        self.assertEqual(fin.user_key, "(desconhecido)")


if __name__ == "__main__":
    unittest.main()
