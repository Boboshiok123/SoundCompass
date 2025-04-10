import pygame
import sys
import math
import os
import socket
import threading

pygame.init()

WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("PD + Interactive Animations")

WHITE = (255, 255, 255)
clock = pygame.time.Clock()

# --------------------------------------------------------------------------------
# 1) Socket Logic (PD -> Python)
# --------------------------------------------------------------------------------
HOST, PORT = "localhost", 13001

# param_images structure: param -> {"active": bool, "images": [(surf, rect), ...]}
param_images = {}

def load_image_centered(filename):
    """Loads an image from 'Assets/filename' and returns (surf, rect) centered."""
    path = os.path.join("Assets", filename)
    surf = pygame.image.load(path).convert_alpha()
    rect = surf.get_rect(center=(WIDTH//2, HEIGHT//2))
    return surf, rect

def add_param_images(param, *filenames):
    """Adds multiple images (lines/dots) to one param (e.g., 'notes')."""
    img_list = []
    for f in filenames:
        s, r = load_image_centered(f)
        img_list.append((s, r))
    param_images[param] = {"active": False, "images": img_list}

# Fill out the mapping:
add_param_images("notes",    "VisualDot.png", "VisualLine.png")
add_param_images("beat",     "SoundDot.png",  "SoundLine.png")
add_param_images("drum",     "SmellDot.png",  "SmellLine.png")
add_param_images("drumBeat", "MindDot.png",   "MindLine.png")
add_param_images("ambient",  "TasteDot.png",  "TasteLine.png")
add_param_images("rythmn",   "TouchDot.png",  "TouchLine.png", "GeneralLine.png")

def pd_server_thread():
    """Background thread that receives PD messages like 'notes 1' or 'drumBeat 0'."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, PORT))
    sock.listen(1)
    print(f"[PD Server] Listening on {HOST}:{PORT}")

    while True:
        connection, client_address = sock.accept()
        print(f"[PD Server] Client connected: {client_address}")
        try:
            while True:
                data = connection.recv(128)
                if not data:
                    break
                msg = data.decode("utf-8").replace('\n','').replace('\r','').replace('\t','').replace(';','')
                print(f"[PD Server] Received: {msg}")
                parts = msg.split()
                if len(parts) == 2:
                    param_name, value_str = parts
                    is_active = (value_str == "1")
                    if param_name in param_images:
                        param_images[param_name]["active"] = is_active
                    else:
                        print(f"Unknown param: {param_name}")
        finally:
            connection.close()

# Start PD server thread
thread = threading.Thread(target=pd_server_thread, daemon=True)
thread.start()

# --------------------------------------------------------------------------------
# 2) Interactive Animation Setup (Arcs, Gauge, Handle, etc.)
# --------------------------------------------------------------------------------

# Circle images (not scaled)
mask_surf, mask_rect         = load_image_centered("Mask.png")
boldcircle_surf, boldcircle_rect = load_image_centered("BoldCircle.png")
thincircle_surf, thincircle_rect = load_image_centered("ThinCircle.png")

# Arcs (enlarged on mouse press, animated back)
thickarc_surf, thickarc_rect = load_image_centered("ThickArc.png")
thinarc_surf, thinarc_rect   = load_image_centered("ThinArc.png")

# Gauge (scales & rotates based on handle speed)
gauge_surf, gauge_rect = load_image_centered("Gauge.png")

# Handle (rotation only, not scaled)
handle_surf, handle_rect = load_image_centered("Handle.png")

# We'll keep any lines/dots from PD beneath all of these.

# Animation variables
# Lines/dots scale factor is separate if you like, but let's keep it at 1.0 or custom
# We'll focus on arcs + gauge scale, handle rotation
arc_scale_current  = 1.0
arc_scale_target   = 1.0
gauge_scale_current = 1.0
gauge_scale_target  = 1.0
gauge_angle         = 0.0  # rotation in degrees
gauge_rot_speed_factor = 2.0  # how strongly gauge spins relative to handle rotation
handle_angle = 0.0

# For handle snapping
SNAP_ANGLES = [90, 180]

# For a simple lines/dots scale if you want (clamped min=1.0):
lines_scale_factor = 1.0
MAX_SCALE = 5.0

# Mouse logic
dragging = False
old_angle = 0.0

def get_mouse_angle(mx, my):
    dx = mx - (WIDTH // 2)
    dy = my - (HEIGHT // 2)
    angle_rads = math.atan2(dy, dx)
    return math.degrees(angle_rads)

def snap_to_nearest_angle(angle, angle_list):
    """Snaps angle to whichever in angle_list is closest."""
    return min(angle_list, key=lambda a: abs(a - angle))

def smooth_approach(current, target, factor=0.2):
    """Simple easing/tween approach for animation."""
    return current + (target - current) * factor

# --------------------------------------------------------------------------------
# Main Loop
# --------------------------------------------------------------------------------
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                dragging = True
                mx, my = event.pos
                old_angle = get_mouse_angle(mx, my)

                # Enlarge arcs + gauge
                arc_scale_target    = 1.2
                gauge_scale_target  = 1.1

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                dragging = False

                # Return arcs + gauge to normal
                arc_scale_target   = 1.0
                gauge_scale_target = 1.0

                # Snap handle angle
                handle_angle = snap_to_nearest_angle(handle_angle, SNAP_ANGLES)

        elif event.type == pygame.MOUSEMOTION:
            if dragging:
                mx, my = event.pos
                new_angle = get_mouse_angle(mx, my)
                delta_angle = new_angle - old_angle

                # Normalize to [-180..180]
                if delta_angle > 180:
                    delta_angle -= 360
                elif delta_angle < -180:
                    delta_angle += 360

                # Rotate handle
                handle_angle += delta_angle

                # For lines/dots scale (optional)
                # Clockwise => enlarge, CCW => shrink
                if delta_angle < 0:
                    lines_scale_factor += 0.01
                elif delta_angle > 0:
                    lines_scale_factor -= 0.01

                # Clamp lines_scale_factor
                if lines_scale_factor < 1.0:
                    lines_scale_factor = 1.0
                if lines_scale_factor > MAX_SCALE:
                    lines_scale_factor = MAX_SCALE

                # Gauge rotation based on handle movement
                gauge_angle += delta_angle * gauge_rot_speed_factor

                old_angle = new_angle

    # ------------------- Animate arcs + gauge scales -------------------
    arc_scale_current    = smooth_approach(arc_scale_current, arc_scale_target, 0.2)
    gauge_scale_current  = smooth_approach(gauge_scale_current, gauge_scale_target, 0.2)

    # Clear screen
    screen.fill(WHITE)

    # 1) Draw lines/dots from PD below everything else
    #    If you'd like to scale them as well, you can do a transform here
    for param_name, info in param_images.items():
        if info["active"]:
            for (surf, rect) in info["images"]:
                # Optionally scale lines/dots if you want them bigger/smaller
                if lines_scale_factor != 1.0:
                    orig_w, orig_h = surf.get_size()
                    new_w = int(orig_w * lines_scale_factor)
                    new_h = int(orig_h * lines_scale_factor)
                    lines_surf = pygame.transform.scale(surf, (new_w, new_h))
                    lines_rect = lines_surf.get_rect(center=(WIDTH//2, HEIGHT//2))
                    screen.blit(lines_surf, lines_rect)
                else:
                    # No scaling
                    screen.blit(surf, rect)

    # 2) Draw mask, boldcircle, thincircle as is (no scaling/rotation)
    screen.blit(mask_surf, mask_rect)
    screen.blit(boldcircle_surf, boldcircle_rect)
    screen.blit(thincircle_surf, thincircle_rect)

    # 3) Draw gauge (scaled + rotated)
    #    First scale
    gw, gh = gauge_surf.get_size()
    new_gw = int(gw * gauge_scale_current)
    new_gh = int(gh * gauge_scale_current)
    gauge_scaled = pygame.transform.scale(gauge_surf, (new_gw, new_gh))
    gauge_scaled_rect = gauge_scaled.get_rect(center=(WIDTH//2, HEIGHT//2))

    #    Then rotate
    gauge_rotated = pygame.transform.rotate(gauge_scaled, -gauge_angle)
    gauge_rot_rect = gauge_rotated.get_rect(center=(WIDTH//2, HEIGHT//2))
    screen.blit(gauge_rotated, gauge_rot_rect)

    # 4) Draw thickArc + thinArc (scaled, no rotation)
    tw, th = thickarc_surf.get_size()
    arcw   = int(tw * arc_scale_current)
    arch   = int(th * arc_scale_current)
    thickarc_scaled = pygame.transform.scale(thickarc_surf, (arcw, arch))
    thickarc_rect = thickarc_scaled.get_rect(center=(WIDTH//2, HEIGHT//2))
    screen.blit(thickarc_scaled, thickarc_rect)

    tw2, th2 = thinarc_surf.get_size()
    arcw2   = int(tw2 * arc_scale_current)
    arch2   = int(th2 * arc_scale_current)
    thinarc_scaled = pygame.transform.scale(thinarc_surf, (arcw2, arch2))
    thinarc_rect = thinarc_scaled.get_rect(center=(WIDTH//2, HEIGHT//2))
    screen.blit(thinarc_scaled, thinarc_rect)

    # 5) Draw handle (rotate only)
    rotated_handle = pygame.transform.rotate(handle_surf, -handle_angle)
    handle_rect = rotated_handle.get_rect(center=(WIDTH//2, HEIGHT//2))
    screen.blit(rotated_handle, handle_rect)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()

