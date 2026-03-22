"""
A* route optimizer on a 20x20 grid.
Fire heatmap values become cell costs so the algorithm avoids dangerous zones.
"""
import heapq

GRID_H, GRID_W = 20, 20

ZONE_TO_REGION = {
    'F3-A': (0, 0),  'F3-B': (0, 5),  'F3-C': (0, 10), 'F3-D': (0, 15),
    'F2-A': (5, 0),  'F2-B': (5, 5),  'F2-C': (5, 10), 'F2-D': (5, 15),
    'F1-A': (10, 0), 'F1-B': (10, 5), 'F1-C': (10, 10), 'F1-D': (10, 15),
}

EXITS = [(19, 0), (19, 5), (19, 10), (19, 15)]


def _cost_grid(heatmap: dict) -> list:
    grid = [[1.0] * GRID_W for _ in range(GRID_H)]
    for zone, data in heatmap.items():
        if zone not in ZONE_TO_REGION:
            continue
        r, c = ZONE_TO_REGION[zone]
        cost = 1.0 + data['fire_prob'] * 99
        for dr in range(5):
            for dc in range(5):
                if r + dr < GRID_H and c + dc < GRID_W:
                    grid[r + dr][c + dc] = cost
    return grid


def _astar(start: tuple, goal: tuple, grid: list):
    open_set = [(0, start)]
    came_from, g = {}, {start: 0}
    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur == goal:
            path = []
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            return list(reversed(path)) + [goal]
        r, c = cur
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < GRID_H and 0 <= nc < GRID_W:
                ng = g[cur] + grid[nr][nc]
                nb = (nr, nc)
                if ng < g.get(nb, 1e9):
                    came_from[nb] = cur
                    g[nb] = ng
                    heapq.heappush(open_set, (ng + abs(nr - goal[0]) + abs(nc - goal[1]), nb))
    return None


def _zone(r: int, c: int) -> str:
    f = 3 - r // 5
    f = max(1, min(3, f))
    z = ['A', 'B', 'C', 'D'][min(c // 5, 3)]
    return f'F{f}-{z}'


def compute_routes(occupants: list, heatmap: dict) -> dict:
    """
    Compute evacuation routes for all occupants.

    Args:
        occupants: list of OccupantPosition dicts
        heatmap: current fire heatmap

    Returns:
        dict mapping person_id → list of RouteWaypoint dicts
    """
    grid = _cost_grid(heatmap)
    routes = {}
    for occ in occupants:
        start = (occ['grid_y'], occ['grid_x'])
        best, best_cost = None, 1e9
        for exit_pt in EXITS:
            path = _astar(start, exit_pt, grid)
            if path:
                cost = sum(grid[r][c] for r, c in path)
                if cost < best_cost:
                    best_cost = cost
                    best = path
        if best:
            routes[occ['person_id']] = [
                {'grid_x': c, 'grid_y': r, 'zone': _zone(r, c)}
                for r, c in best
            ]
    return routes
