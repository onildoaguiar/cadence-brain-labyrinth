"""Procedural labyrinths that stay solvable as they grow."""

from __future__ import annotations

import random
from collections import deque

# Bit 0 north, bit 1 east, bit 2 south, bit 3 west. A set bit is a wall.
NORTH, EAST, SOUTH, WEST = 0, 1, 2, 3
DIRS: tuple[tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))
OPP = (SOUTH, WEST, NORTH, EAST)


def level_spec(level: int) -> tuple[int, int, int, str]:
    """Return width, height, extra openings, and a short description.

    Early heats are small and have shortcuts. Later heats are larger perfect
    mazes with a single winding path.
    """
    level = max(1, int(level))
    size = min(5 + (level - 1) // 2, 13)
    extras = max(0, 8 - level)
    if extras >= 4:
        kind = "open corridors"
    elif extras > 0:
        kind = "a few shortcuts"
    else:
        kind = "one winding path"
    return size, size, extras, kind


class Maze:
    def __init__(self, width: int, height: int, walls: list[list[int]]):
        self.width = width
        self.height = height
        self.walls = walls
        self.exit = (width - 1, height - 1)
        self.shortest = self._shortest()

    def blocked(self, x: int, y: int, direction: int) -> bool:
        return bool(self.walls[y][x] & (1 << direction))

    def flat_walls(self) -> list[int]:
        return [int(self.walls[y][x]) for y in range(self.height) for x in range(self.width)]

    def _shortest(self) -> int:
        goal = self.exit
        seen = {(0, 0)}
        queue: deque[tuple[int, int, int]] = deque([(0, 0, 0)])
        while queue:
            x, y, dist = queue.popleft()
            if (x, y) == goal:
                return dist
            for direction, (dx, dy) in enumerate(DIRS):
                if self.blocked(x, y, direction):
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                nxt = (nx, ny)
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append((nxt[0], nxt[1], dist + 1))
        raise RuntimeError("generated labyrinth has no path to the door")


def generate(width: int, height: int, rng: random.Random, extra_passages: int) -> Maze:
    """Recursive-backtracker labyrinth, then optional extra openings."""
    walls = [[0b1111 for _ in range(width)] for _ in range(height)]
    seen = [[False for _ in range(width)] for _ in range(height)]
    stack = [(0, 0)]
    seen[0][0] = True
    while stack:
        x, y = stack[-1]
        options: list[tuple[int, int, int]] = []
        for direction, (dx, dy) in enumerate(DIRS):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and not seen[ny][nx]:
                options.append((direction, nx, ny))
        if not options:
            stack.pop()
            continue
        direction, nx, ny = options[rng.randrange(len(options))]
        _open(walls, x, y, direction, nx, ny)
        seen[ny][nx] = True
        stack.append((nx, ny))

    candidates: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            for direction, (dx, dy) in enumerate(DIRS):
                if direction >= 2:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if walls[y][x] & (1 << direction):
                    candidates.append((x, y, direction, nx, ny))
    rng.shuffle(candidates)
    for x, y, direction, nx, ny in candidates[: max(0, extra_passages)]:
        _open(walls, x, y, direction, nx, ny)
    return Maze(width, height, walls)


def _open(walls: list[list[int]], x: int, y: int, direction: int, nx: int, ny: int) -> None:
    walls[y][x] &= ~(1 << direction)
    walls[ny][nx] &= ~(1 << OPP[direction])


def observe(maze: Maze, x: int, y: int, visited: list[list[bool]]):
    """Local walls plus a bearing to the door. The full map stays hidden."""
    import numpy as np

    blocked = [1.0 if maze.blocked(x, y, direction) else 0.0 for direction in range(4)]
    span_x = max(1, maze.width - 1)
    span_y = max(1, maze.height - 1)
    door_x = (maze.exit[0] - x) / span_x
    door_y = (maze.exit[1] - y) / span_y
    seen = 1.0 if visited[y][x] else 0.0
    openings = sum(1.0 for direction in range(4) if not maze.blocked(x, y, direction)) / 4.0
    return np.array([[*blocked, door_x, door_y, seen, openings]], dtype=float)


def move(maze: Maze, x: int, y: int, action: int, visited: list[list[bool]]) -> tuple[int, int, float, bool, bool]:
    """Apply one step. Returns x, y, reward, reached_door, bumped."""
    action = int(action) % 4
    before = abs(maze.exit[0] - x) + abs(maze.exit[1] - y)
    if maze.blocked(x, y, action):
        return x, y, -0.55, False, True
    dx, dy = DIRS[action]
    nx, ny = x + dx, y + dy
    after = abs(maze.exit[0] - nx) + abs(maze.exit[1] - ny)
    reward = 0.30 if after < before else -0.25
    if visited[ny][nx]:
        reward -= 0.10
    reward -= 0.02
    reached = (nx, ny) == maze.exit
    if reached:
        reward += 1.0
    return nx, ny, reward, reached, False
