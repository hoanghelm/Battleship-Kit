"""
Battle Ship — bot tham chiếu / reference bot.

Cài đặt đúng các chiến thuật trong cẩm nang:

  1. Bắn đón   — giải điểm gặp nhau hai lần (lead_bearing)
  2. Lưới đạn  — rải 3/5/7 viên phủ kín cung thoát hiểm (net_offset)
  3. Né 360°   — chấm điểm mọi hướng, có xét mép bản đồ (best_heading)
  4. Chống kẹt góc — ưu tiên cao nhất, vì vào góc rồi thì không né được nữa
  5. Khóa mục tiêu + chống dao động hướng

Chạy:  python smart_bot.py [--port 11000] [--ship 0|1|2] [--seconds N]
"""

from __future__ import annotations

import argparse
import math
import time
from typing import Any, Dict, List, Optional

from battleship_client import BattleShipClient

# Thông số thân tàu, tra theo máu tối đa mà server trả về.
HULLS = {
    110: {"name": "corvette", "speed": 8.0, "shell": 16.0, "range": 11.0},
    170: {"name": "cruiser", "speed": 6.4, "shell": 15.0, "range": 13.0},
    260: {"name": "gunboat", "speed": 4.9, "shell": 13.0, "range": 15.0},
}

ENEMY_TOP_SPEED = 4.8     # con trinh sát nhanh nhất
LANE = 1.7                # bề rộng "ăn đạn": đạn + thân tàu
HEADING_STEP = 10         # 36 ứng viên hướng


def ang_diff(a: float, b: float) -> float:
    """Góc lệch nhỏ nhất có dấu, từ b sang a."""
    return (a - b + 180.0) % 360.0 - 180.0


def hull_of(me: Dict[str, Any]) -> Dict[str, Any]:
    best = min(HULLS, key=lambda h: abs(h - me.get("healthMax", 170)))
    return HULLS[best]


# --------------------------------------------------------------------- bắn

def lead_bearing(me: Dict[str, Any], tgt: Dict[str, Any], shell_speed: float) -> float:
    """Hướng tuyệt đối tới điểm đón. Giải hai lần vì vòng đầu làm cự ly đổi."""
    h = math.radians(tgt["heading"])
    vx = tgt["speed"] * math.cos(h)
    vy = tgt["speed"] * math.sin(h)

    ax, ay = tgt["x"], tgt["y"]
    for _ in range(2):
        d = math.hypot(ax - me["x"], ay - me["y"])
        t = d / shell_speed
        ax = tgt["x"] + vx * t
        ay = tgt["y"] + vy * t

    return math.degrees(math.atan2(ay - me["y"], ax - me["x"]))


def escape_cone(shell_speed: float) -> float:
    """Nửa góc nón thoát hiểm, tính bằng độ. Không phụ thuộc cự ly."""
    return math.degrees(math.asin(min(0.99, ENEMY_TOP_SPEED / shell_speed)))


def shells_needed(distance: float, theta: float) -> int:
    """Số viên cần để khép kín cung — xấp xỉ 0.4 x cự ly."""
    width = 2.0 * distance * math.tan(math.radians(theta))
    return max(1, min(7, math.ceil(width / LANE)))


def net_offset(shot_index: int, n: int, theta: float) -> float:
    """Góc lệch của phát bắn thứ shot_index, bắn từ giữa ra hai biên."""
    step = 2.0 * theta / n
    lanes = [-theta + (k + 0.5) * step for k in range(n)]
    lanes.sort(key=abs)
    return lanes[shot_index % n]


# --------------------------------------------------------------------- né

def shell_miss_distance(shell: Dict[str, Any], px: float, py: float,
                        my_vx: float, my_vy: float, x0: float, y0: float) -> float:
    """Khoảng cách gần nhất giữa tàu và viên đạn trong ~1 giây tới."""
    closest = float("inf")
    for t in (0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        sx = shell["x"] + shell["vx"] * t
        sy = shell["y"] + shell["vy"] * t
        mx = x0 + my_vx * t
        my = y0 + my_vy * t
        closest = min(closest, math.hypot(sx - mx, sy - my))
    return closest


def wall_margin(state: Dict[str, Any], x: float, y: float) -> float:
    """Khoảng cách tới mép gần nhất."""
    hw = state.get("arenaHalfWidth", 19.0)
    hh = state.get("arenaHalfHeight", 12.0)
    return min(hw - abs(x), hh - abs(y))


def walls_near(state: Dict[str, Any], x: float, y: float, limit: float = 4.5) -> int:
    """Số mép đang ở gần. 2 nghĩa là đang trong góc."""
    hw = state.get("arenaHalfWidth", 19.0)
    hh = state.get("arenaHalfHeight", 12.0)
    return int(hw - abs(x) < limit) + int(hh - abs(y) < limit)


def heading_score(state: Dict[str, Any], deg: float, hull: Dict[str, Any]) -> float:
    """Chấm điểm một hướng: mô phỏng 1.5 giây rồi cộng trừ.

    Bài học rút ra từ đo đạc: KHÔNG thưởng cho "ở xa địch". Trong một bản đồ
    có biên, "xa địch" và "tránh mép" mâu thuẫn trực tiếp, và vế xa địch sẽ
    thắng, đẩy tàu ra sát biên rồi kẹt góc. Chỉ phạt khi quá gần, thế là đủ.
    """
    me = state["self"]
    a = math.radians(deg)
    vx = math.cos(a) * hull["speed"]
    vy = math.sin(a) * hull["speed"]

    px = me["x"] + vx * 1.5
    py = me["y"] + vy * 1.5

    if wall_margin(state, px, py) < 0.5:
        return -1e9

    score = 0.0

    # 1. Đạn địch đang bay tới.
    for s_ in state.get("shells", []):
        if not s_.get("hostile"):
            continue
        d = shell_miss_distance(s_, px, py, vx, vy, me["x"], me["y"])
        score -= 90.0 / (0.6 + d)

    # 2. Mép bản đồ — số hạng cứu mạng, phải đủ mạnh để luôn thắng.
    margin = wall_margin(state, px, py)
    if margin < 8.0:
        score -= (8.0 - margin) ** 2 * 3.0

    # 3. Chỉ phạt khi quá gần địch. Không có phần thưởng cho việc chạy xa.
    for e in state.get("enemies", []):
        d = math.hypot(e["x"] - px, e["y"] - py)
        if d < 6.0:
            score -= (6.0 - d) * 6.0

    # 4. Kéo nhẹ về giữa bản đồ: ở giữa thì luôn còn nhiều hướng để né.
    score -= math.hypot(px, py) * 0.35
    return score


def best_heading(state: Dict[str, Any], hull: Dict[str, Any],
                 current: float) -> float:
    """Quét 360 độ. Giữ hướng cũ trừ khi hướng mới hơn hẳn (chống dao động)."""
    best, best_score = current, heading_score(state, current, hull)
    for deg in range(0, 360, HEADING_STEP):
        s = heading_score(state, float(deg), hull)
        # Ngưỡng 4 điểm: đủ bỏ qua nhiễu, vẫn đổi khi thật sự cần.
        if s > best_score + 4.0:
            best, best_score = float(deg), s
    return best


def centre_bearing(me: Dict[str, Any]) -> float:
    return math.degrees(math.atan2(-me["y"], -me["x"]))


# --------------------------------------------------------------------- bot

class SmartBot:
    def __init__(self, use_net: bool = True, use_dodge: bool = True) -> None:
        self.heading = 0.0
        self.target_id: Optional[int] = None
        self.shot_index = 0
        self.last_target_id: Optional[int] = None
        self.use_net = use_net
        self.use_dodge = use_dodge
        self.shots = 0
        self.corner_ticks = 0

    def pick_target(self, foes: List[Dict[str, Any]], rng: float) -> Dict[str, Any]:
        alive = {e["id"]: e for e in foes}
        if self.target_id in alive:
            return alive[self.target_id]
        pool = [e for e in foes if e["distance"] <= rng] or foes
        pick = min(pool, key=lambda e: (e["health"], e["distance"]))
        self.target_id = pick["id"]
        return pick

    def decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        me = state["self"]
        hull = hull_of(me)
        foes = state.get("enemies", [])

        # ---- Lái ----
        in_corner = walls_near(state, me["x"], me["y"]) >= 2
        if in_corner:
            # Vào góc rồi thì không còn chỗ né: cắm đầu về giữa bản đồ.
            # Nhưng VẪN BẮN — sống sót và gây sát thương không loại trừ nhau.
            self.corner_ticks += 1
            self.heading = centre_bearing(me)
        elif self.use_dodge:
            self.heading = best_heading(state, hull, self.heading)
        elif foes:
            near = min(foes, key=lambda e: e["distance"])
            self.heading = near["bearing"] + 180.0

        turn = max(-25.0, min(25.0, ang_diff(self.heading, me["heading"]) / 3.0))

        if not foes:
            return {"speed": 50, "angle": turn, "turret": None, "fire": False}

        # ---- Bắn ----
        target = self.pick_target(foes, hull["range"])
        if target["id"] != self.last_target_id:
            self.shot_index = 0
            self.last_target_id = target["id"]

        aim = lead_bearing(me, target, hull["shell"])
        if self.use_net:
            theta = escape_cone(hull["shell"])
            n = shells_needed(target["distance"], theta)
            aim += net_offset(self.shot_index, n, theta)

        in_range = target["distance"] <= hull["range"] * 0.95
        laid_on = abs(ang_diff(aim, me["turret"])) < 12.0
        fire = bool(me["reloaded"]) and in_range and laid_on
        if fire:
            self.shot_index += 1
            self.shots += 1

        return {
            "speed": 90 if in_corner else 80,
            "angle": turn,
            "turret": aim,
            "fire": fire,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Battle Ship smart bot")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11000)
    ap.add_argument("--ship", type=int, default=1, help="0 corvette, 1 cruiser, 2 gunboat")
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = chạy tới khi chìm")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--net", type=int, default=1, help="1 bat luoi dan, 0 chi ban don")
    ap.add_argument("--dodge", type=int, default=1, help="1 ne 360do, 0 chay nguoc dich")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    bot = SmartBot(use_net=bool(args.net), use_dodge=bool(args.dodge))
    with BattleShipClient(args.host, args.port) as c:
        c.choose_ship(args.ship)
        state = c.wait_for_match()

        started = time.time()
        best_wave, best_score = 0, 0
        tick = 0

        while True:
            if state.get("gameOver"):
                break
            if args.seconds and time.time() - started > args.seconds:
                break

            best_wave = max(best_wave, state.get("wave", 0))
            best_score = max(best_score, state.get("score", 0))

            act = bot.decide(state)
            c.set_control(act["speed"], act["angle"], act["turret"], act["fire"])

            tick += 1
            if not args.quiet and tick % 120 == 0:
                me = state["self"]
                print(f"wave {state.get('wave')}  score {state.get('score')}  "
                      f"hull {me['health']:.0f}/{me['healthMax']:.0f}  "
                      f"contacts {len(state.get('enemies', []))}")

            time.sleep(1 / 60)
            state = c.get_state()

        me = state.get("self", {})
        print(f"KETQUA {args.label} wave={best_wave} score={best_score} "
              f"hull={me.get('health', 0):.0f} song={time.time()-started:.0f}s "
              f"ban={bot.shots} ticks_goc={bot.corner_ticks}")


if __name__ == "__main__":
    main()
