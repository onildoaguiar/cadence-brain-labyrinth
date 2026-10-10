"""One continuing Cadence brain racing a person through growing labyrinths."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from cadence import Brain

from maze import DIRS, generate, level_spec, move, observe

TICK_MS = 180
COUNTDOWN_S = 3.0
INTERLUDE_S = 2.6
GRACE_STEPS = 36
TRACE = 72
ACTIONS = ("north", "east", "south", "west")
CHALLENGES: tuple[dict[str, str], ...] = (
    {"id": "first-door", "title": "First door", "detail": "Reach the exit."},
    {"id": "novice", "title": "Novice", "detail": "Beat the brain while it is still young."},
    {"id": "clean", "title": "Clean run", "detail": "Beat the brain without touching a wall."},
    {"id": "perfect", "title": "Perfect line", "detail": "Reach the door along the shortest path."},
    {"id": "streak", "title": "Three straight", "detail": "Beat the brain three heats in a row."},
    {"id": "winding", "title": "One path", "detail": "Beat the brain in a labyrinth with a single winding path."},
    {"id": "trained", "title": "Fully trained", "detail": "Beat the brain after its youth is over."},
    {"id": "calm", "title": "Calm mind", "detail": "Beat the brain while it is calm and no longer learning."},
)


class Race:
    def __init__(self, seed: int = 11) -> None:
        self.seed = seed
        self._maze_rng = __import__("random").Random(seed)
        self.brain = self._new_brain(seed)
        self.level = 1
        self.scores = {"you": 0, "brain": 0, "ties": 0}
        self.doors_reached = 0
        self.heats = 0
        self.phase = "lobby"
        self.until = 0.0
        self.result: str | None = None
        self.winner: str | None = None
        self.grace_left: int | None = None
        self.step = 0
        self.limit = 1
        self.kind = ""
        self.maze = self._build_maze()
        self._reset_bodies()
        self.held: str | None = None
        self.queued: str | None = None
        self.ready_action: int | None = None
        self.pending_reward: float | None = None
        self.think_ms = 0.0
        self.episode_return = 0.0
        self.last_reward = 0.0
        self.reward_trace: list[float] = []
        self.arousal_trace: list[float] = []
        self.you_bumped = False
        self.brain_bumped = False
        self.you_facing = EAST_FACING
        self.brain_facing = EAST_FACING
        self.you_bumps = 0
        self.win_streak = 0
        self.achievements = {item["id"]: False for item in CHALLENGES}
        self.enshrined = False
        self.paused = False
        self._frozen_remaining = 0.0

    def start(self) -> None:
        if self.phase != "lobby":
            return
        self._begin_heat(first=True)

    def hatch(self) -> None:
        self.seed += 1
        self._maze_rng = __import__("random").Random(self.seed)
        self.brain = self._new_brain(self.seed)
        self.level = 1
        self.scores = {"you": 0, "brain": 0, "ties": 0}
        self.doors_reached = 0
        self.heats = 0
        self.result = None
        self.winner = None
        self.grace_left = None
        self.ready_action = None
        self.pending_reward = None
        self.reward_trace.clear()
        self.arousal_trace.clear()
        self.episode_return = 0.0
        self.last_reward = 0.0
        self.think_ms = 0.0
        self.you_bumps = 0
        self.win_streak = 0
        self.achievements = {item["id"]: False for item in CHALLENGES}
        self.enshrined = False
        self.paused = False
        self._frozen_remaining = 0.0
        self.maze = self._build_maze()
        self._reset_bodies()
        self.phase = "lobby"

    def new_brain(self) -> None:
        """Hatch when a life is already going, then start the race."""
        self.paused = False
        if self.phase != "lobby":
            self.hatch()
        self.start()

    def set_paused(self, paused: bool) -> None:
        if self.phase == "lobby" or paused == self.paused:
            return
        now = time.monotonic()
        if paused:
            if self.phase in {"countdown", "interlude"}:
                self._frozen_remaining = max(0.0, self.until - now)
            self.paused = True
            self.held = None
            self.queued = None
            return
        if self.phase in {"countdown", "interlude"}:
            self.until = now + self._frozen_remaining
        self.paused = False

    def hold(self, direction: str | None) -> None:
        if direction not in {None, "n", "e", "s", "w"}:
            return
        self.held = direction
        if direction is not None:
            self.queued = direction

    def tick(self) -> None:
        if self.paused:
            return
        now = time.monotonic()
        if self.phase == "countdown" and now >= self.until:
            self.phase = "race"
            return
        if self.phase == "interlude" and now >= self.until:
            self.level += 1
            self.maze = self._build_maze()
            self._reset_bodies()
            self._begin_heat(first=False)
            return
        if self.phase == "race":
            self._step_race()

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        countdown = None
        if self.phase == "countdown":
            remaining = self._frozen_remaining if self.paused else max(0.0, self.until - now)
            countdown = min(3, max(1, int(np.floor(remaining)) + 1))
        telemetry = self._telemetry()
        you_dist = self._dist(*self.you)
        brain_dist = self._dist(*self.brain_at)
        lead = "even"
        if self.phase == "race" and self.winner is None:
            if you_dist < brain_dist:
                lead = "you"
            elif brain_dist < you_dist:
                lead = "brain"
        return {
            "phase": self.phase,
            "level": self.level,
            "kind": self.kind,
            "width": self.maze.width,
            "height": self.maze.height,
            "walls": self.maze.flat_walls(),
            "exit": list(self.maze.exit),
            "shortest": self.maze.shortest,
            "limit": self.limit,
            "step": self.step,
            "scores": dict(self.scores),
            "doors_reached": self.doors_reached,
            "heats": self.heats,
            "result": self.result,
            "winner": self.winner,
            "grace_left": self.grace_left,
            "countdown": countdown,
            "paused": self.paused,
            "lead": lead,
            "tick_ms": TICK_MS,
            "you": self._body(
                self.you, self.you_trail, you_dist, self.you_bumped, self.you_facing, self.you_done
            ),
            "brain": self._body(
                self.brain_at, self.brain_trail, brain_dist, self.brain_bumped, self.brain_facing, self.brain_done
            ),
            "telemetry": telemetry,
            "challenges": self._challenge_snapshot(),
            "fame_ready": self.fame_ready(),
        }

    def fame_ready(self) -> bool:
        return bool(self.achievements) and all(self.achievements.values()) and not self.enshrined

    def enshrine(self) -> None:
        self.enshrined = True

    def _step_race(self) -> None:
        self.step += 1
        self.you_bumped = False
        self.brain_bumped = False
        if self.winner is not None and self.grace_left is not None:
            self.grace_left -= 1

        if not self.you_done:
            self._step_you()

        reward: float | None = None
        if not self.brain_done and self.ready_action is not None:
            reward = self._step_brain(self.ready_action)

        if self.winner is None and (self.you_done or self.brain_done):
            self._award()
            self.grace_left = GRACE_STEPS

        heat_over = (
            (self.you_done and self.brain_done)
            or self.step >= self.limit
            or (self.winner is not None and self.grace_left is not None and self.grace_left <= 0)
        )
        if heat_over:
            if not self.brain_done and reward is not None:
                self.pending_reward = reward - 0.35
            self._close_heat()
            return
        if not self.brain_done and reward is not None:
            obs = observe(self.maze, self.brain_at[0], self.brain_at[1], self.brain_seen)
            self.ready_action = self._live(obs, reward=reward)
            self.pending_reward = None

    def _step_you(self) -> None:
        direction = self.held or self.queued
        self.queued = None
        if direction is None:
            return
        action = "nesw".index(direction)
        ox, oy = self.you
        x, y, _reward, reached, bumped = move(self.maze, ox, oy, action, self.you_seen)
        self.you_bumped = bumped
        self.you_facing = action
        if bumped:
            self.you_bumps += 1
        else:
            self.you_seen[oy][ox] = True
        self.you = (x, y)
        self._push(self.you_trail, x, y)
        if reached:
            self.you_done = True
            self._on_you_door()

    def _step_brain(self, action: int) -> float:
        ox, oy = self.brain_at
        x, y, reward, reached, bumped = move(self.maze, ox, oy, action, self.brain_seen)
        self.brain_bumped = bumped
        self.brain_facing = int(action) % 4
        if not bumped:
            self.brain_seen[oy][ox] = True
        self.brain_at = (x, y)
        self._push(self.brain_trail, x, y)
        self.last_reward = float(reward)
        self.episode_return += float(reward)
        self.pending_reward = float(reward)
        self.reward_trace.append(round(float(reward), 4))
        del self.reward_trace[:-TRACE]
        if reached:
            self.brain_done = True
            self.doors_reached += 1
        return float(reward)

    def _award(self) -> None:
        self.heats += 1
        you_won = self.you_done and not self.brain_done
        if self.you_done and self.brain_done:
            self.winner = "tie"
            self.result = "Dead heat — both reached the door."
            self.scores["ties"] += 1
            self.scores["you"] += 1
            self.scores["brain"] += 1
            self.win_streak = 0
        elif you_won:
            self.winner = "you"
            self.result = "You reached the door."
            self.scores["you"] += 1
            self.win_streak += 1
            self._unlock_win(self._mode())
        else:
            self.winner = "brain"
            self.result = "The brain reached the door."
            self.scores["brain"] += 1
            self.win_streak = 0

    def _close_heat(self) -> None:
        if self.winner is None:
            self.heats += 1
            self.result = "The door sealed. Nobody made it."
            self.win_streak = 0
        self.phase = "interlude"
        self.until = time.monotonic() + INTERLUDE_S
        self.held = None
        self.queued = None

    def _begin_heat(self, first: bool) -> None:
        self.result = None
        self.winner = None
        self.grace_left = None
        self.step = 0
        self.episode_return = 0.0
        self.you_done = False
        self.brain_done = False
        obs = observe(self.maze, 0, 0, self.brain_seen)
        if first or self.pending_reward is None:
            self.ready_action = self._live(obs)
        else:
            self.ready_action = self._live(obs, reward=self.pending_reward, done=True)
            self.pending_reward = None
        self.phase = "countdown"
        self.until = time.monotonic() + COUNTDOWN_S

    def _build_maze(self):
        width, height, extras, kind = level_spec(self.level)
        self.kind = kind
        self.limit = width * height * 4
        maze = generate(width, height, self._maze_rng, extras)
        return maze

    def _reset_bodies(self) -> None:
        self.you = (0, 0)
        self.brain_at = (0, 0)
        self.you_done = False
        self.brain_done = False
        self.you_seen = _blank(self.maze)
        self.brain_seen = _blank(self.maze)
        self.you_trail = [(0, 0)]
        self.brain_trail = [(0, 0)]
        self.you_bumped = False
        self.brain_bumped = False
        self.you_facing = EAST_FACING
        self.brain_facing = EAST_FACING
        self.you_bumps = 0

    def _on_you_door(self) -> None:
        self._unlock("first-door")
        walked = max(0, len(self.you_trail) - 1)
        if walked == self.maze.shortest:
            self._unlock("perfect")

    def _unlock_win(self, mode: str) -> None:
        if mode == "youth":
            self._unlock("novice")
        if self.you_bumps == 0:
            self._unlock("clean")
        if self.win_streak >= 3:
            self._unlock("streak")
        if self.kind == "one winding path":
            self._unlock("winding")
        if mode in {"aroused", "routine"}:
            self._unlock("trained")
        if mode == "routine":
            self._unlock("calm")

    def _unlock(self, challenge_id: str) -> None:
        self.achievements[challenge_id] = True

    def _challenge_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "title": item["title"],
                "detail": item["detail"],
                "done": bool(self.achievements[item["id"]]),
            }
            for item in CHALLENGES
        ]

    def _live(self, obs: np.ndarray, reward: float | None = None, done: bool = False) -> int:
        kwargs: dict[str, Any] = {}
        if reward is not None:
            kwargs["reward"] = [float(reward)]
        if done:
            kwargs["done"] = np.array([True])
        started = time.perf_counter()
        try:
            action = self.brain.live(obs, **kwargs)
        except RuntimeError:
            if reward is not None and self.brain.pending_feedback:
                action = self.brain.live(obs, **kwargs)
            else:
                action = self.brain.live(obs)
        self.think_ms = (time.perf_counter() - started) * 1000.0
        self._note_arousal()
        return int(action[0]) % 4

    def _note_arousal(self) -> None:
        report = self.brain.last_arousal
        level = 0.0 if report is None else float(report["level"])
        self.arousal_trace.append(round(level, 4))
        del self.arousal_trace[:-TRACE]

    def _telemetry(self) -> dict[str, Any]:
        arousal = self.brain.last_arousal
        settlement = self.brain.last_settlement
        learning = self.brain.last_learning
        age = 0
        youth = 0
        moments = {"routine": 0, "aroused": 0}
        if self.brain.arousal is not None:
            state = self.brain.arousal.to_dict()
            age = int(state.get("age") or 0)
            moments = {
                "routine": int(state.get("moments", {}).get("routine", 0)),
                "aroused": int(state.get("moments", {}).get("aroused", 0)),
            }
        described = self.brain.describe().get("arousal") or {}
        youth = int(described.get("youth") or 0)
        mode = self._mode(age=age, youth=youth, arousal=arousal)
        residual = None if settlement is None else float(settlement["max_residual"])
        tolerance = None if settlement is None else float(settlement["tolerance"])
        return {
            "mode": mode,
            "arousal": None if arousal is None else round(float(arousal["level"]), 4),
            "surprise": None if arousal is None else round(float(arousal["surprise"]), 4),
            "want": None if arousal is None else round(float(arousal["want"]), 4),
            "learned": False if arousal is None else bool(arousal["learned"]),
            "recorded": False if arousal is None else bool(arousal["recorded"]),
            "choice": None if self.ready_action is None else ACTIONS[self.ready_action],
            "reward": round(self.last_reward, 4),
            "episode_return": round(self.episode_return, 4),
            "forecast_error": None
            if learning is None
            else round(float(learning.get("td_error", 0.0)), 4),
            "dopamine": None if learning is None else round(float(learning.get("dopamine", 0.0)), 4),
            "value": None if learning is None else round(float(learning.get("value", 0.0)), 4),
            "updates": int(getattr(self.brain.learner, "updates", 0)),
            "age": age,
            "youth": youth,
            "moments": moments,
            "qualified": None if settlement is None else bool(settlement["qualified"]),
            "residual": None if residual is None else round(residual, 6),
            "tolerance": tolerance,
            "sweeps": None if settlement is None else int(settlement["steps"]),
            "budget": None if settlement is None else int(settlement["budget"]),
            "think_ms": round(self.think_ms, 2),
            "rewards": list(self.reward_trace),
            "arousal_trace": list(self.arousal_trace),
            "shortest": self.maze.shortest,
            "walked": max(0, len(self.brain_trail) - 1),
        }

    def _mode(self, age: int | None = None, youth: int | None = None, arousal: Any = None) -> str:
        if age is None or youth is None or arousal is None:
            report = self._telemetry_parts()
            age, youth, arousal = report
        if arousal is None:
            return "idle"
        if age < youth:
            return "youth"
        return str(arousal.get("mode") or "routine")

    def _telemetry_parts(self) -> tuple[int, int, Any]:
        arousal = self.brain.last_arousal
        age = 0
        if self.brain.arousal is not None:
            age = int(self.brain.arousal.to_dict().get("age") or 0)
        described = self.brain.describe().get("arousal") or {}
        youth = int(described.get("youth") or 0)
        return age, youth, arousal

    def _dist(self, x: int, y: int) -> int:
        return abs(self.maze.exit[0] - x) + abs(self.maze.exit[1] - y)

    @staticmethod
    def _body(pos, trail, dist, bumped, facing, done) -> dict[str, Any]:
        return {
            "x": pos[0],
            "y": pos[1],
            "dist": dist,
            "bumped": bumped,
            "done": done,
            "facing": ACTIONS[facing],
            "trail": [[x, y] for x, y in trail[-18:]],
        }

    @staticmethod
    def _push(trail: list[tuple[int, int]], x: int, y: int) -> None:
        if not trail or trail[-1] != (x, y):
            trail.append((x, y))

    @staticmethod
    def _new_brain(seed: int) -> Brain:
        return Brain.compose(
            inputs=8,
            actions=4,
            modules=(32, 16),
            seed=seed,
            arousal=True,
            arousal_youth=250,
            arousal_need=0.08,
            working_memory_amplitude=0.35,
            consolidation=0.3,
            actor_eta=0.12,
            actor_eta_bias=0.02,
        )


EAST_FACING = 1


def _blank(maze) -> list[list[bool]]:
    return [[False for _ in range(maze.width)] for _ in range(maze.height)]
