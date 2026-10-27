import math
from pathlib import Path
import numpy as np
import pygame
from ..scan import transform

BG = (12, 20, 32)
PANEL = (20, 33, 49)
TEXT = (221, 233, 241)
MUTED = (134, 159, 180)
CYAN = (52, 218, 200)
AMBER = (255, 193, 91)


class Dashboard:
    def __init__(self):
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((1360, 900))
        pygame.display.set_caption("CoCommand-USV | 2D Lidar Laboratory")
        self.font = pygame.font.SysFont("Consolas", 18)
        self.small = pygame.font.SysFont("Consolas", 15)
        self.title = pygame.font.SysFont("Segoe UI", 28, bold=True)
        self.world_rect = pygame.Rect(24, 164, 620, 408)
        self.map_rect = pygame.Rect(664, 164, 672, 626)

    def text(self, text, xy, color=TEXT, small=False, title=False):
        font = self.title if title else self.small if small else self.font
        self.screen.blit(font.render(str(text), True, color), xy)

    def panel(self, rect, label):
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=12)
        self.text(label, (rect.x+16, rect.y+12), MUTED, small=True)

    def render(self, session, command, status, input_mode, message=""):
        self.screen.fill(BG)
        self.text("CoCommand / 2D Lidar Laboratory", (24, 20), title=True)
        self.text("MANUAL HELM  +  SCAN MATCHING  +  OCCUPANCY MAPPING", (26, 62), MUTED, small=True)
        self.text(f"SOURCE  {session.mode.upper()}    SCANS  {session.count:05d}    SLAM  {session.slam.status}", (26, 106), CYAN)
        self.panel(self.world_rect, "SIMULATED POOL / TRUTH VIEW" if session.mode == "simulate" else "SENSOR VIEW / NO SIMULATION TRUTH")
        if session.mode == "simulate":
            r = self.world_rect
            scale = min((r.w-36)/18, (r.h-70)/12)
            def point(p):
                return (int(r.x+24+p[0]*scale), int(r.bottom-20-p[1]*scale))
            for i, polygon in enumerate(session.world.polygons):
                pygame.draw.polygon(self.screen, (40, 71, 86) if i == 0 else (93, 119, 136), [point(p) for p in polygon], 2 if i == 0 else 0)
            if len(session.truth) > 1:
                pygame.draw.lines(self.screen, AMBER, False, [point(p) for p in session.truth[-5000:]], 2)
            hull = np.array([[.44, 0], [-.32, .22], [-.22, 0], [-.32, -.22]])
            pygame.draw.polygon(self.screen, CYAN, [point(p) for p in transform(hull, session.boat.pose)])
            self.text("Collision: hull contact" if session.boat.collided else "Free driving / no goal", (r.x+18, r.y+36), AMBER, small=True)
        else:
            self.text("Scan-only localization", (46, 235), CYAN)
            self.text("First scan defines (0, 0, 0).", (46, 276))
            self.text("Move slowly; keep static features visible.", (46, 310), small=True)
            self.text("R resets mapping after a lost relocation.", (46, 345), small=True)
            self.text("SPACE stops input. F5 saves the current map.", (46, 380), small=True)
            self.text(session.source_status[:64], (46, 430), AMBER, small=True)
        self.panel(self.map_rect, "ESTIMATED MAP / SCAN-ONLY FRAME")
        g = session.slam.grid
        rows, cols = np.where(g.observed)
        if len(rows):
            lo = np.maximum([cols.min()-12, rows.min()-12], 0)
            hi = np.minimum([cols.max()+13, rows.max()+13], g.size)
        else:
            lo, hi = np.array([125, 125]), np.array([375, 375])
        crop = g.image()[lo[1]:hi[1], lo[0]:hi[0]]
        image = np.repeat(np.flipud(crop)[:, :, None], 3, axis=2)
        surface = pygame.surfarray.make_surface(image.transpose(1, 0, 2))
        available = pygame.Rect(self.map_rect.x+16, self.map_rect.y+46, self.map_rect.w-32, self.map_rect.h-84)
        scale = min(available.w/crop.shape[1], available.h/crop.shape[0])
        size = (max(1, int(crop.shape[1]*scale)), max(1, int(crop.shape[0]*scale)))
        offset = (available.centerx-size[0]//2, available.centery-size[1]//2)
        self.screen.blit(pygame.transform.scale(surface, size), offset)
        def mapped(p):
            c = (np.asarray(p[:2])-g.origin)/g.resolution
            return (int(offset[0]+(c[0]-lo[0])*scale), int(offset[1]+(hi[1]-c[1])*scale))
        old_clip = self.screen.get_clip()
        self.screen.set_clip(available)
        if len(session.slam.trajectory) > 1:
            pygame.draw.lines(self.screen, (255, 160, 43), False,
                              [mapped(p[1:3]) for p in session.slam.trajectory[-5000:]], 2)
        if session.scan:
            for p in transform(session.scan.points(), session.slam.pose)[::2]:
                pygame.draw.circle(self.screen, (18, 172, 164), mapped(p), 1)
        pygame.draw.circle(self.screen, (225, 54, 86), mapped(session.slam.pose), 5)
        self.screen.set_clip(old_clip)
        self.text("White free | Gray unknown | Black occupied", (682, 762), MUTED, small=True)
        self.panel(pygame.Rect(24, 590, 284, 242), "360 DEG / LOCAL SCAN")
        center, radius = (166, 718), 96
        for rr in [32, 64, 96]:
            pygame.draw.circle(self.screen, (49, 70, 88), center, rr, 1)
        pygame.draw.line(self.screen, MUTED, center, (center[0]+radius, center[1]), 1)
        if session.scan:
            for p in session.scan.points():
                xy = (int(center[0]+p[0]*radius/12), int(center[1]-p[1]*radius/12))
                pygame.draw.circle(self.screen, CYAN, xy, 1)
        self.text("+x forward / +y left", (54, 808), MUTED, small=True)
        self.text(f"THROTTLE  {command.throttle*100:+6.1f}%", (330, 606), CYAN)
        self.text(f"STEERING  {command.steering*100:+6.1f}%", (330, 638), AMBER)
        self.text(f"INPUT     {input_mode}", (330, 670), small=True)
        self.text(f"POSE  {session.slam.pose[0]:+.2f}, {session.slam.pose[1]:+.2f} m", (330, 703), small=True)
        self.text(f"YAW   {math.degrees(session.slam.pose[2]):+.1f} deg", (330, 728), small=True)
        self.text(f"RC    {session.rc['throttle_us']} / {session.rc['steering_us']} us", (330, 753), small=True)
        self.text("PWM EQUIVALENT / NO PHYSICAL OUTPUT", (330, 787), MUTED, small=True)
        self.text(status[:105], (26, 848), AMBER)
        self.text("Enter arm | WASD/arrows drive | Space stop | J input | C calibrate | F5 save | R reset | Esc exit", (26, 876), MUTED, small=True)
        if message:
            self.text(message[:120], (26, 80), MUTED, small=True)
        pygame.display.flip()

    def screenshot(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self.screen, str(path))
