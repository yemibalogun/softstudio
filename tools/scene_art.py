"""Generate the hero planet's surface art: app/static/images/planet-cells.svg.

A pointy-top hexagon grid laid on a tangent plane is wrapped onto a sphere
(inverse azimuthal-equidistant) and projected orthographically, so cells
foreshorten toward the limb like a real curved surface. Only the upper part
of the disc is emitted (the part the hero ever shows). A few cells are lit
and twinkle via CSS inside the SVG, which browsers run for SVG images.

    python tools/scene_art.py
"""
import math
import random
from pathlib import Path

R = 500.0          # sphere radius in SVG units (viewBox is 2R square)
CELL = 20.0        # hexagon circumradius on the tangent plane
KEEP_BELOW = 0.18  # emit cells whose centre is above y = +KEEP_BELOW * R
SEED = 11

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "images" / "planet-cells.svg"


def project(u, v):
    """Tangent-plane point -> screen point on the visible hemisphere (or None)."""
    rho = math.hypot(u, v)
    c = rho / R
    if c >= math.pi / 2:
        return None
    theta = math.atan2(v, u)
    s = R * math.sin(c)
    return s * math.cos(theta), s * math.sin(theta)


def corners(cx, cy):
    return [
        (cx + CELL * math.cos(math.radians(60 * i - 30)), cy + CELL * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]


def fmt(p):
    return f"{p[0] + R:.1f} {p[1] + R:.1f}".replace(".0 ", " ").removesuffix(".0")


def main():
    rng = random.Random(SEED)
    w = math.sqrt(3) * CELL
    h = 1.5 * CELL
    limit = R * math.pi / 2
    rows = int(limit / h) + 2
    cols = int(limit / w) + 2

    edges = set()
    edge_paths = []
    lit = {"a": [], "b": [], "c": []}

    for row in range(-rows, rows + 1):
        for col in range(-cols, cols + 1):
            cx = col * w + (w / 2 if row % 2 else 0)
            cy = row * h
            centre = project(cx, cy)
            if centre is None or centre[1] > KEEP_BELOW * R:
                continue
            pts = corners(cx, cy)
            if any(project(*p) is None for p in pts):
                continue

            # Each shared edge once. Near the limb, where the surface visibly
            # curves, the edge gets a midpoint so it bends with the sphere.
            curved = math.hypot(cx, cy) / R > 0.8
            for i in range(6):
                a, b = pts[i], pts[(i + 1) % 6]
                key = tuple(sorted(((round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2)))))
                if key in edges:
                    continue
                edges.add(key)
                seg = (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b) if curved else (a, b)
                edge_paths.append("M" + " L".join(fmt(project(*p)) for p in seg))

            if rng.random() < 0.07:
                shape = "M" + " L".join(fmt(project(*p)) for p in pts) + "Z"
                lit[rng.choice("abc")].append((shape, rng.uniform(0.25, 0.85)))

    def lit_group(name):
        return "".join(f'<path d="{d}" fill-opacity="{o:.2f}"/>' for d, o in lit[name])

    lit_groups = "".join(f'<g class="{name}">{lit_group(name)}</g>' for name in "abc")
    stroke = 'stroke-width="1" stroke-opacity=".55" stroke-linejoin="round"'
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {2 * R:.0f} {2 * R:.0f}">
<style>
.l{{fill:#1f6bff}}
.a,.b,.c{{animation:t 9s ease-in-out infinite}}
.b{{animation-delay:-3s}}
.c{{animation-delay:-6s}}
@keyframes t{{50%{{opacity:.15}}}}
</style>
<g class="l">{lit_groups}</g>
<path d="{''.join(edge_paths)}" fill="none" stroke="#8fc9ff" {stroke}/>
</svg>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"{OUT.relative_to(OUT.parents[3])}: {len(svg) // 1024} KB, {len(edges)} edges, "
          f"{sum(len(v) for v in lit.values())} lit cells")


if __name__ == "__main__":
    main()
