from __future__ import annotations

import random
import tkinter as tk
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Optional


CELL_SIZE = 28
GRID_WIDTH = 21
GRID_HEIGHT = 15
HUD_HEIGHT = 92
WINDOW_WIDTH = GRID_WIDTH * CELL_SIZE
WINDOW_HEIGHT = GRID_HEIGHT * CELL_SIZE + HUD_HEIGHT

BG_COLOR = "#08111b"
GRID_COLOR = "#10253d"
WALL_COLOR = "#21466d"
PLAYER_COLOR = "#52f7c5"
ENEMY_COLOR = "#ff6f5e"
ORB_COLOR = "#ffe38a"
BOOST_COLOR = "#9c8cff"
TEXT_COLOR = "#e8f1ff"
ACCENT_COLOR = "#60c2ff"
WARNING_COLOR = "#ffb84d"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


class MindMazeGame:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Mind Maze: BAD202 AI Challenge")
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack()

        self.keys_down = set()
        self.after_id: Optional[str] = None
        self.last_direction = (1, 0)

        self.root.bind_all("<KeyPress>", self.on_key_press)
        self.root.bind_all("<KeyRelease>", self.on_key_release)
        self.root.bind("<space>", self.use_emp)
        self.root.bind("<Return>", self.restart_if_over)
        self.canvas.bind("<Button-1>", self.on_click)

        self.showing_title = True
        self.best_score = 0

        self.start_new_game()
        self.draw_title_screen()
        self.root.after(100, self.ensure_focus)

    def start_new_game(self) -> None:
        self.tick_count = 0
        self.score = 0
        self.level = 1
        self.lives = 3
        self.emp_charges = 2
        self.enemy_stun_ticks = 0
        self.game_over = False
        self.orbs_collected = 0
        self.move_history = []
        self.player_speed_ticks = 5
        self.pending_player_move = 0
        self.boost_ticks = 0
        self.generate_level()

    def generate_level(self) -> None:
        self.grid = self.build_maze(self.level)
        self.player = Point(1, 1)
        self.reachable_cells = self.find_reachable_cells(self.player)
        self.enemy = max(
            self.reachable_cells,
            key=lambda point: self.manhattan(point, self.player),
        )
        self.enemy_path = []
        self.enemy_repath_cooldown = 0
        self.enemy_move_ticks = max(3, 8 - self.level)
        self.enemy_pending_move = 0
        free_tiles = max(0, len(self.reachable_cells) - 2)
        orb_count = 0
        if free_tiles > 0:
            orb_count = min(9 + self.level * 2, max(1, free_tiles - 1))
        self.orbs = self.spawn_orbs(orb_count)
        remaining_tiles = len(self.reachable_cells) - len(self.orbs) - 2
        self.boost = None
        if remaining_tiles > 0:
            self.boost = self.spawn_item(exclude=self.orbs | {self.player, self.enemy})
        self.safe_ticks = 45

    def build_maze(self, level: int):
        grid = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]

        for x in range(GRID_WIDTH):
            grid[0][x] = 1
            grid[GRID_HEIGHT - 1][x] = 1
        for y in range(GRID_HEIGHT):
            grid[y][0] = 1
            grid[y][GRID_WIDTH - 1] = 1

        rng = random.Random(level * 19 + 7)
        for x in range(2, GRID_WIDTH - 2, 2):
            for y in range(2, GRID_HEIGHT - 2, 2):
                grid[y][x] = 1
                carve_options = []
                if x > 2:
                    carve_options.append((x - 1, y))
                if y > 2:
                    carve_options.append((x, y - 1))
                if x < GRID_WIDTH - 3:
                    carve_options.append((x + 1, y))
                if y < GRID_HEIGHT - 3:
                    carve_options.append((x, y + 1))
                wx, wy = rng.choice(carve_options)
                grid[wy][wx] = 1

        for _ in range(7 + level):
            x = rng.randint(1, GRID_WIDTH - 2)
            y = rng.randint(1, GRID_HEIGHT - 2)
            if (x, y) not in {(1, 1), (GRID_WIDTH - 2, GRID_HEIGHT - 2)}:
                grid[y][x] = 0

        return grid

    def spawn_orbs(self, count: int):
        orbs = set()
        while len(orbs) < count:
            point = self.spawn_item(exclude=orbs | {self.player, self.enemy})
            orbs.add(point)
        return orbs

    def spawn_item(self, exclude) -> Point:
        while True:
            point = random.choice(tuple(self.reachable_cells))
            if point not in exclude:
                return point

    def on_key_press(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        self.keys_down.add(key)
        if self.showing_title and key in {"return", "space", "w", "a", "s", "d", "up", "down", "left", "right"}:
            self.start_game()

    def on_key_release(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        self.keys_down.discard(key)

    def on_click(self, event=None) -> None:
        if self.showing_title:
            self.start_game()
        else:
            self.ensure_focus()

    def start_game(self) -> None:
        if self.showing_title:
            self.showing_title = False
            self.ensure_focus()
            self.loop()

    def ensure_focus(self) -> None:
        self.root.focus_force()
        self.canvas.focus_set()

    def restart_if_over(self, event=None) -> None:
        if self.game_over:
            self.start_new_game()
            self.showing_title = False
            self.ensure_focus()
            self.loop()

    def use_emp(self, event=None) -> None:
        if self.showing_title or self.game_over:
            return
        if self.emp_charges > 0 and self.enemy_stun_ticks == 0:
            self.emp_charges -= 1
            self.enemy_stun_ticks = 22

    def loop(self) -> None:
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        self.update()
        self.draw()

        if not self.game_over and not self.showing_title:
            self.after_id = self.root.after(70, self.loop)

    def update(self) -> None:
        if self.game_over or self.showing_title:
            return

        self.tick_count += 1
        self.safe_ticks = max(0, self.safe_ticks - 1)
        self.boost_ticks = max(0, self.boost_ticks - 1)
        self.enemy_stun_ticks = max(0, self.enemy_stun_ticks - 1)

        self.pending_player_move += 1
        move_gap = 3 if self.boost_ticks > 0 else self.player_speed_ticks
        if self.pending_player_move >= move_gap:
            self.pending_player_move = 0
            self.handle_player_movement()

        self.enemy_pending_move += 1
        adaptive_gap = max(2, self.enemy_move_ticks - min(2, self.score // 60))
        if self.enemy_pending_move >= adaptive_gap and self.enemy_stun_ticks == 0:
            self.enemy_pending_move = 0
            self.handle_enemy_movement()

        if self.player == self.enemy and self.safe_ticks == 0:
            self.lose_life()

        if not self.orbs:
            self.level += 1
            self.emp_charges += 1
            self.score += 40
            self.generate_level()

    def handle_player_movement(self) -> None:
        direction_map = {
            "up": (0, -1),
            "w": (0, -1),
            "down": (0, 1),
            "s": (0, 1),
            "left": (-1, 0),
            "a": (-1, 0),
            "right": (1, 0),
            "d": (1, 0),
        }

        dx = dy = 0
        for key in ("up", "w", "down", "s", "left", "a", "right", "d"):
            if key in self.keys_down:
                dx, dy = direction_map[key]
                break

        if dx == dy == 0:
            return

        target = Point(self.player.x + dx, self.player.y + dy)
        if self.is_walkable(target):
            self.player = target
            self.last_direction = (dx, dy)
            self.move_history.append((dx, dy))
            self.move_history = self.move_history[-6:]

        if self.player in self.orbs:
            self.orbs.remove(self.player)
            self.orbs_collected += 1
            self.score += 10

        if self.boost and self.player == self.boost:
            self.boost_ticks = 35
            self.boost = None
            self.score += 15

    def handle_enemy_movement(self) -> None:
        target = self.predict_player_target()

        if self.enemy_repath_cooldown <= 0 or not self.enemy_path:
            self.enemy_path = self.find_path(self.enemy, target)
            self.enemy_repath_cooldown = 3
        else:
            self.enemy_repath_cooldown -= 1

        if self.enemy_path:
            next_step = self.enemy_path.pop(0)
            self.enemy = next_step

    def predict_player_target(self) -> Point:
        px, py = self.player.x, self.player.y
        dx, dy = self.infer_direction_bias()

        if self.level >= 3:
            prediction_steps = min(4, 1 + self.level // 2)
            predicted = Point(px, py)
            for _ in range(prediction_steps):
                candidate = Point(predicted.x + dx, predicted.y + dy)
                if self.is_walkable(candidate):
                    predicted = candidate
                else:
                    break
            if self.manhattan(self.enemy, predicted) < self.manhattan(self.enemy, self.player):
                return predicted

        return self.player

    def infer_direction_bias(self) -> tuple[int, int]:
        if not self.move_history:
            return self.last_direction

        score_x = sum(move[0] for move in self.move_history)
        score_y = sum(move[1] for move in self.move_history)

        if abs(score_x) > abs(score_y):
            return (1 if score_x > 0 else -1, 0)
        if score_y != 0:
            return (0, 1 if score_y > 0 else -1)
        return self.last_direction

    def lose_life(self) -> None:
        self.lives -= 1
        self.safe_ticks = 30
        if self.lives <= 0:
            self.game_over = True
            self.best_score = max(self.best_score, self.score)
            return

        self.player = Point(1, 1)
        self.enemy = max(
            self.reachable_cells,
            key=lambda point: self.manhattan(point, self.player),
        )
        self.enemy_path = []

    def neighbors(self, point: Point):
        result = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = Point(point.x + dx, point.y + dy)
            if self.is_walkable(nxt):
                result.append(nxt)
        return result

    def find_reachable_cells(self, start: Point):
        frontier = [start]
        visited = {start}
        index = 0

        while index < len(frontier):
            current = frontier[index]
            index += 1
            for nxt in self.neighbors(current):
                if nxt not in visited:
                    visited.add(nxt)
                    frontier.append(nxt)

        return visited

    def find_path(self, start: Point, goal: Point):
        frontier = []
        heappush(frontier, (0, 0, start))
        came_from = {start: None}
        cost_so_far = {start: 0}
        order = 0

        while frontier:
            _, _, current = heappop(frontier)
            if current == goal:
                break

            for nxt in self.neighbors(current):
                new_cost = cost_so_far[current] + 1
                if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                    cost_so_far[nxt] = new_cost
                    priority = new_cost + self.manhattan(nxt, goal)
                    order += 1
                    heappush(frontier, (priority, order, nxt))
                    came_from[nxt] = current

        if goal not in came_from:
            reachable = min(came_from, key=lambda p: self.manhattan(p, goal))
            goal = reachable

        path = []
        current = goal
        while current != start and current in came_from:
            path.append(current)
            current = came_from[current]
            if current is None:
                break
        path.reverse()
        return path

    def is_walkable(self, point: Point) -> bool:
        if not (0 <= point.x < GRID_WIDTH and 0 <= point.y < GRID_HEIGHT):
            return False
        return self.grid[point.y][point.x] == 0

    @staticmethod
    def manhattan(a: Point, b: Point) -> int:
        return abs(a.x - b.x) + abs(a.y - b.y)

    def draw(self) -> None:
        self.canvas.delete("all")
        self.draw_background()
        self.draw_maze()
        self.draw_items()
        self.draw_entities()
        self.draw_hud()

        if self.game_over:
            self.draw_game_over()

    def draw_background(self) -> None:
        self.canvas.create_rectangle(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT, fill=BG_COLOR, outline="")
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                x1 = x * CELL_SIZE
                y1 = y * CELL_SIZE
                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + CELL_SIZE,
                    y1 + CELL_SIZE,
                    outline=GRID_COLOR,
                )

    def draw_maze(self) -> None:
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if self.grid[y][x] == 1:
                    x1 = x * CELL_SIZE
                    y1 = y * CELL_SIZE
                    self.canvas.create_rectangle(
                        x1 + 2,
                        y1 + 2,
                        x1 + CELL_SIZE - 2,
                        y1 + CELL_SIZE - 2,
                        fill=WALL_COLOR,
                        outline="",
                    )

    def draw_items(self) -> None:
        for orb in self.orbs:
            cx = orb.x * CELL_SIZE + CELL_SIZE // 2
            cy = orb.y * CELL_SIZE + CELL_SIZE // 2
            self.canvas.create_oval(
                cx - 5,
                cy - 5,
                cx + 5,
                cy + 5,
                fill=ORB_COLOR,
                outline="",
            )

        if self.boost:
            x1 = self.boost.x * CELL_SIZE + 7
            y1 = self.boost.y * CELL_SIZE + 7
            self.canvas.create_rectangle(
                x1,
                y1,
                x1 + 14,
                y1 + 14,
                fill=BOOST_COLOR,
                outline="",
            )

    def draw_entities(self) -> None:
        self.draw_glow(self.player, "#2edcb3")
        self.draw_glow(self.enemy, "#ff8f82")

        self.draw_circle(self.player, PLAYER_COLOR, inset=5)
        enemy_color = "#6aa1ff" if self.enemy_stun_ticks else ENEMY_COLOR
        self.draw_circle(self.enemy, enemy_color, inset=5)

        if self.enemy_stun_ticks:
            ex = self.enemy.x * CELL_SIZE + CELL_SIZE // 2
            ey = self.enemy.y * CELL_SIZE + CELL_SIZE // 2
            self.canvas.create_text(
                ex,
                ey - 18,
                text="EMP",
                fill=ACCENT_COLOR,
                font=("Consolas", 9, "bold"),
            )

    def draw_glow(self, point: Point, color: str) -> None:
        x1 = point.x * CELL_SIZE + 2
        y1 = point.y * CELL_SIZE + 2
        self.canvas.create_oval(
            x1,
            y1,
            x1 + CELL_SIZE - 4,
            y1 + CELL_SIZE - 4,
            fill=color,
            outline="",
            stipple="gray25",
        )

    def draw_circle(self, point: Point, color: str, inset: int) -> None:
        x1 = point.x * CELL_SIZE + inset
        y1 = point.y * CELL_SIZE + inset
        self.canvas.create_oval(
            x1,
            y1,
            point.x * CELL_SIZE + CELL_SIZE - inset,
            point.y * CELL_SIZE + CELL_SIZE - inset,
            fill=color,
            outline="",
        )

    def draw_hud(self) -> None:
        top = GRID_HEIGHT * CELL_SIZE
        self.canvas.create_rectangle(
            0,
            top,
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
            fill="#091827",
            outline="",
        )

        self.canvas.create_text(
            16,
            top + 18,
            anchor="w",
            text="BAD402  Mind Maze",
            fill=TEXT_COLOR,
            font=("Consolas", 16, "bold"),
        )
        self.canvas.create_text(
            16,
            top + 46,
            anchor="w",
            text=f"Score: {self.score}    Level: {self.level}    Lives: {self.lives}    EMP: {self.emp_charges}",
            fill=ACCENT_COLOR,
            font=("Consolas", 12, "bold"),
        )

        ai_text = "AI: A* pathfinding + move prediction + adaptive speed"
        if self.enemy_stun_ticks:
            ai_text = "AI stunned by EMP. Use the opening to collect orbs."
        elif self.boost_ticks > 0:
            ai_text = "Boost active. Your movement speed is temporarily increased."

        self.canvas.create_text(
            16,
            top + 72,
            anchor="w",
            text=ai_text,
            fill=WARNING_COLOR,
            font=("Consolas", 11),
        )

    def draw_title_screen(self) -> None:
        self.canvas.delete("all")
        self.draw_background()
        self.canvas.create_rectangle(32, 68, WINDOW_WIDTH - 32, WINDOW_HEIGHT - 48, fill="#0c1f31", outline=ACCENT_COLOR, width=2)
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            120,
            text="MIND MAZE",
            fill=TEXT_COLOR,
            font=("Consolas", 30, "bold"),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            160,
            text="A BAD202 AI Concept Game",
            fill=ACCENT_COLOR,
            font=("Consolas", 15, "bold"),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            235,
            text="Collect all memory orbs while escaping the Sentinel AI.",
            fill=TEXT_COLOR,
            font=("Consolas", 13),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            265,
            text="The enemy uses A* pathfinding, predicts your direction, and speeds up as you score.",
            fill=WARNING_COLOR,
            font=("Consolas", 12),
            width=WINDOW_WIDTH - 120,
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            320,
            text="Controls: WASD or Arrow Keys to move    Space for EMP",
            fill=TEXT_COLOR,
            font=("Consolas", 12),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            350,
            text="Purple cube = speed boost    Yellow dots = score orbs",
            fill=TEXT_COLOR,
            font=("Consolas", 12),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            410,
            text="Press any movement key, Space, Enter, or click to start",
            fill=ACCENT_COLOR,
            font=("Consolas", 14, "bold"),
        )

    def draw_game_over(self) -> None:
        self.canvas.create_rectangle(60, 110, WINDOW_WIDTH - 60, WINDOW_HEIGHT - 120, fill="#08111b", outline=ENEMY_COLOR, width=2)
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            180,
            text="GAME OVER",
            fill=ENEMY_COLOR,
            font=("Consolas", 28, "bold"),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            235,
            text=f"Final Score: {self.score}",
            fill=TEXT_COLOR,
            font=("Consolas", 16, "bold"),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            265,
            text=f"Best Score: {self.best_score}",
            fill=ACCENT_COLOR,
            font=("Consolas", 14, "bold"),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            315,
            text="AI concepts used: A* search, predictive movement analysis, adaptive difficulty.",
            fill=WARNING_COLOR,
            font=("Consolas", 12),
        )
        self.canvas.create_text(
            WINDOW_WIDTH // 2,
            360,
            text="Press Enter to play again",
            fill=TEXT_COLOR,
            font=("Consolas", 14, "bold"),
        )

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    MindMazeGame().run()
