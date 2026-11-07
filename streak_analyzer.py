"""Consolidação de sequências (streaks) de presentes.

Lógica pura, sem dependências externas, para poder ser testada sem conexão.

Ideia: presentes "streakáveis" chegam várias vezes com repeat_count crescente
enquanto o espectador continua clicando. Só o evento com repeat_end=True traz
a contagem final. Somar todos os eventos conta em dobro.

Este módulo apenas OBSERVA e consolida o que a biblioteca entrega. Se o
comportamento real do TikTok for diferente do suposto, as anomalias abaixo
registram a diferença (é para isso que serve o teste em live real).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class GiftObservation:
    ts: float
    user_key: str
    gift_id: str
    gift_name: str
    diamonds: int
    streakable: bool
    repeat_count: int
    repeat_end: bool


@dataclass
class FinalizedGift:
    user_key: str
    gift_id: str
    gift_name: str
    diamonds: int
    count: int
    events_seen: int
    naive_sum: int  # soma ingênua de repeat_count de todos os eventos (mostra o erro de contar em dobro)
    ended_by: str  # repeat_end | non_streakable | timeout | shutdown
    duration_s: float
    anomalies: List[str] = field(default_factory=list)

    @property
    def total_diamonds(self) -> int:
        return self.diamonds * self.count


@dataclass
class _OpenStreak:
    first_ts: float
    last_ts: float
    gift_name: str
    diamonds: int
    last_count: int = 0
    events_seen: int = 0
    naive_sum: int = 0
    anomalies: List[str] = field(default_factory=list)


class StreakAnalyzer:
    def __init__(self, stale_timeout_s: float = 10.0) -> None:
        self.stale_timeout_s = stale_timeout_s
        self._open: Dict[Tuple[str, str], _OpenStreak] = {}

    # ------------------------------------------------------------------
    def feed(self, obs: GiftObservation) -> Optional[FinalizedGift]:
        user = obs.user_key or "(desconhecido)"
        count = max(1, int(obs.repeat_count or 1))

        if not obs.streakable:
            anomalies = []
            if obs.repeat_count and obs.repeat_count > 1:
                anomalies.append("presente_nao_streakavel_com_repeat_count_maior_que_1")
            return FinalizedGift(
                user_key=user,
                gift_id=obs.gift_id,
                gift_name=obs.gift_name,
                diamonds=obs.diamonds,
                count=count,
                events_seen=1,
                naive_sum=count,
                ended_by="non_streakable",
                duration_s=0.0,
                anomalies=anomalies,
            )

        key = (user, obs.gift_id)
        st = self._open.get(key)
        if st is None:
            st = _OpenStreak(
                first_ts=obs.ts,
                last_ts=obs.ts,
                gift_name=obs.gift_name,
                diamonds=obs.diamonds,
            )
            self._open[key] = st
            if obs.repeat_end:
                st.anomalies.append("repeat_end_sem_evento_parcial_anterior")

        if obs.repeat_count < st.last_count:
            st.anomalies.append(f"contagem_diminuiu({st.last_count}->{obs.repeat_count})")

        st.events_seen += 1
        st.naive_sum += count
        st.last_ts = obs.ts

        if not obs.repeat_end:
            st.last_count = max(st.last_count, count)
            return None

        # repeat_end: contagem final autoritativa
        if st.last_count and count < st.last_count:
            st.anomalies.append(f"final_menor_que_parcial({st.last_count}->{count})")
        del self._open[key]
        return self._finalize(key, st, count, "repeat_end")

    # ------------------------------------------------------------------
    def flush_stale(self, now: float) -> List[FinalizedGift]:
        out: List[FinalizedGift] = []
        for key, st in list(self._open.items()):
            if now - st.last_ts >= self.stale_timeout_s:
                st.anomalies.append("sem_repeat_end")
                del self._open[key]
                out.append(self._finalize(key, st, max(1, st.last_count), "timeout"))
        return out

    def flush_all(self) -> List[FinalizedGift]:
        out: List[FinalizedGift] = []
        for key, st in list(self._open.items()):
            st.anomalies.append("sessao_encerrada_com_streak_aberto")
            del self._open[key]
            out.append(self._finalize(key, st, max(1, st.last_count), "shutdown"))
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _finalize(key: Tuple[str, str], st: _OpenStreak, count: int, ended_by: str) -> FinalizedGift:
        return FinalizedGift(
            user_key=key[0],
            gift_id=key[1],
            gift_name=st.gift_name,
            diamonds=st.diamonds,
            count=count,
            events_seen=st.events_seen,
            naive_sum=st.naive_sum,
            ended_by=ended_by,
            duration_s=round(st.last_ts - st.first_ts, 3),
            anomalies=list(st.anomalies),
        )
