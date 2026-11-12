"""
================================================================
  DETECTIE VIDEO AMBULANTA - Sistem Intersectie Inteligenta
================================================================
  Versiune: 4.1 (Linii Independente)
  Nou in v4.1:
    Cele 4 zone (NORD, SUD, EST, VEST) au acum linii de separare
    independente. Zona dintre ele (mijlocul intersectiei) este
    complet ignorata. Trage de fiecare linie in parte pentru a
    stabili exact marginile de intrare din intersectie.

  Dependente:
    pip install opencv-python pyserial numpy

  Taste globale:
    ENTER / SPATIU  Confirma si trece la pasul urmator
    R               Reseteaza liniile
    Q               Iese din program
================================================================
"""

import cv2
import numpy as np
import serial
import time
import sys
import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

# ── CONFIGURARE GENERALA ──────────────────────────────────────
PORT_SERIAL         = 'COM3'
BAUD_RATE           = 9600
DETECT_TIME         = 2.0
COOLDOWN_TIME       = 10.0
CAMERA_INDEX        = 0

CALIBRATION_SECONDS = 2.0
DIFF_THRESHOLD      = 30
MIN_MOTION_AREA     = 800
MIN_CONTOUR_AREA    = 400
ZONE_CONFIG_FILE    = "zone_config.json"

# ── PRAG CULOARE ALBASTRA (HSV) ───────────────────────────────
BLUE_HSV_LOW  = np.array([100, 120,  70])
BLUE_HSV_HIGH = np.array([130, 255, 255])

# ── ETICHETE SI CULORI ZONE ───────────────────────────────────
ZONE_LABELS = {0: "NORD", 1: "SUD", 2: "EST", 3: "VEST"}
ZONE_COLORS = {
    0: (0,   220, 0),    # Verde
    1: (0,   120, 255),  # Portocaliu
    2: (255, 60,  60),   # Rosu
    3: (220, 0,   220),  # Mov
}


# ── CLASA STARE DETECTIE PER ZONA ────────────────────────────
@dataclass
class ZoneState:
    label:          str
    first_detected: Optional[float] = None
    signal_sent:    bool            = False
    cooldown_until: float           = 0.0

    def reset(self):
        self.first_detected = None
        self.signal_sent    = False

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def start_cooldown(self):
        self.cooldown_until = time.time() + COOLDOWN_TIME
        self.signal_sent    = True
        self.first_detected = None


# ══════════════════════════════════════════════════════════════
#  EDITOR VIZUAL DE ZONE (4 LINII INDEPENDENTE)
# ══════════════════════════════════════════════════════════════
def zone_editor(cap) -> Tuple[int, int, int, int]:
    WIN = "Editor Zone | ENTER=confirma  R=reset  Q=iesire"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    ret, frame = cap.read()
    if not ret:
        print("[EROARE] Nu pot citi cadru pentru editor.")
        sys.exit(1)
    h, w = frame.shape[:2]

    # Valori implicite
    line_n = h // 4
    line_s = 3 * h // 4
    line_e = 3 * w // 4
    line_w = w // 4

    if os.path.exists(ZONE_CONFIG_FILE):
        try:
            with open(ZONE_CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            line_n = int(cfg.get("line_n", line_n))
            line_s = int(cfg.get("line_s", line_s))
            line_e = int(cfg.get("line_e", line_e))
            line_w = int(cfg.get("line_w", line_w))
            # Limitare la limitele ecranului
            line_n = max(10, min(h - 10, line_n))
            line_s = max(10, min(h - 10, line_s))
            line_e = max(10, min(w - 10, line_e))
            line_w = max(10, min(w - 10, line_w))
            print(f"[EDITOR] Configuratie incarcata din '{ZONE_CONFIG_FILE}'.")
        except Exception as e:
            print(f"[EDITOR] Eroare incarcare config: {e}. Folosesc default.")

    # Stare mouse
    SNAP_DIST = 15
    dragging = {'n': False, 's': False, 'e': False, 'w': False}

    def mouse_cb(event, mx, my, flags, param):
        nonlocal line_n, line_s, line_e, line_w, dragging

        if event == cv2.EVENT_LBUTTONDOWN:
            dists = {
                'n': abs(my - line_n),
                's': abs(my - line_s),
                'e': abs(mx - line_e),
                'w': abs(mx - line_w)
            }
            closest = min(dists, key=dists.get)
            if dists[closest] <= SNAP_DIST:
                dragging[closest] = True

        elif event == cv2.EVENT_MOUSEMOVE:
            if dragging['n']: line_n = max(10, min(h - 10, my))
            if dragging['s']: line_s = max(10, min(h - 10, my))
            if dragging['e']: line_e = max(10, min(w - 10, mx))
            if dragging['w']: line_w = max(10, min(w - 10, mx))

        elif event == cv2.EVENT_LBUTTONUP:
            dragging = {k: False for k in dragging}

    cv2.setMouseCallback(WIN, mouse_cb)

    print("[EDITOR] 4 Linii Independente.")
    print("  • Trage linia VERDE       (NORD)")
    print("  • Trage linia PORTOCALIE  (SUD)")
    print("  • Trage linia ROSIE       (EST)")
    print("  • Trage linia MOV         (VEST)")

    while True:
        ret, frame = cap.read()
        if not ret: break
        h, w = frame.shape[:2]

        overlay = frame.copy()

        # Deseneaza zonele active
        cv2.rectangle(overlay, (0, 0),      (w, line_n), ZONE_COLORS[0], -1) # NORD
        cv2.rectangle(overlay, (0, line_s), (w, h),      ZONE_COLORS[1], -1) # SUD
        cv2.rectangle(overlay, (line_e, 0), (w, h),      ZONE_COLORS[2], -1) # EST
        cv2.rectangle(overlay, (0, 0),      (line_w, h), ZONE_COLORS[3], -1) # VEST
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

        # Deseneaza liniile (mai groase daca sunt trase)
        cv2.line(frame, (0, line_n), (w, line_n), ZONE_COLORS[0], 3 if dragging['n'] else 2)
        cv2.line(frame, (0, line_s), (w, line_s), ZONE_COLORS[1], 3 if dragging['s'] else 2)
        cv2.line(frame, (line_e, 0), (line_e, h), ZONE_COLORS[2], 3 if dragging['e'] else 2)
        cv2.line(frame, (line_w, 0), (line_w, h), ZONE_COLORS[3], 3 if dragging['w'] else 2)

        # Etichete texte pe linii
        cv2.putText(frame, "Limita NORD", (10, line_n - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ZONE_COLORS[0], 2)
        cv2.putText(frame, "Limita SUD",  (10, line_s + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ZONE_COLORS[1], 2)
        cv2.putText(frame, "Limita EST",  (line_e + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ZONE_COLORS[2], 2)
        cv2.putText(frame, "Limita VEST", (line_w - 110, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ZONE_COLORS[3], 2)

        # Instructiuni UI
        cv2.putText(frame, "EDITOR ZONE | Seteaza marginile de intrare in intersectie",
                    (10, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, "Mijlocul va fi ignorat! ENTER=confirma  R=reset",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        cv2.imshow(WIN, frame)
        key = cv2.waitKey(20) & 0xFF

        if key in (13, 32):   # ENTER / SPATIU
            break
        elif key == ord('r'): # Reset
            line_n, line_s, line_e, line_w = h // 4, 3 * h // 4, 3 * w // 4, w // 4
        elif key == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            sys.exit(0)

    cv2.destroyWindow(WIN)

    # Salveaza config
    cfg = {"line_n": line_n, "line_s": line_s, "line_e": line_e, "line_w": line_w}
    try:
        with open(ZONE_CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[EDITOR] Eroare salvare: {e}")

    return line_n, line_s, line_e, line_w


# ══════════════════════════════════════════════════════════════
#  CONSTRUCTIE DREPTUNGHIURI DIN 4 LINII
# ══════════════════════════════════════════════════════════════
def build_zone_rects(line_n, line_s, line_e, line_w, h, w):
    return [
        (0,      0,      w,      line_n), # 0: NORD (de sus pana la line_n)
        (0,      line_s, w,      h),      # 1: SUD  (de la line_s in jos)
        (line_e, 0,      w,      h),      # 2: EST  (de la line_e in dreapta)
        (0,      0,      line_w, h),      # 3: VEST (din stanga pana la line_w)
    ]


def _draw_zone_lines(frame, line_n, line_s, line_e, line_w, w, h):
    cv2.line(frame, (0, line_n), (w, line_n), ZONE_COLORS[0], 2)
    cv2.line(frame, (0, line_s), (w, line_s), ZONE_COLORS[1], 2)
    cv2.line(frame, (line_e, 0), (line_e, h), ZONE_COLORS[2], 2)
    cv2.line(frame, (line_w, 0), (line_w, h), ZONE_COLORS[3], 2)


# ══════════════════════════════════════════════════════════════
#  FUNCTIE PRINCIPALA
# ══════════════════════════════════════════════════════════════
def main():
    arduino = None
    try:
        arduino = serial.Serial(PORT_SERIAL, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"[SERIAL] Conectat pe {PORT_SERIAL}.")
    except serial.SerialException as e:
        print(f"[AVERTISMENT] {e} — mod DEMO activ.")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[EROARE] Nu pot accesa camera {CAMERA_INDEX}.")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n[PASUL 1/3] EDITOR ZONE — pozitioneaza marginile.")
    line_n, line_s, line_e, line_w = zone_editor(cap)

    zones        = [ZoneState(label=ZONE_LABELS[i]) for i in range(4)]
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    background_ref  = None
    bg_accumulator  = None
    bg_frame_count  = 0
    calibrated      = False
    calibration_end = None

    print(f"\n[PASUL 2/3] CALIBRARE FUNDAL — {CALIBRATION_SECONDS}s.")

    while True:
        ret, frame = cap.read()
        if not ret: break

        now  = time.time()
        h, w = frame.shape[:2]

        zone_rects = build_zone_rects(line_n, line_s, line_e, line_w, h, w)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)

        if not calibrated:
            if calibration_end is None:
                calibration_end = now + CALIBRATION_SECONDS
                bg_accumulator  = np.float32(gray)
                bg_frame_count  = 1
            else:
                bg_accumulator += np.float32(gray)
                bg_frame_count += 1

            if now >= calibration_end:
                background_ref = bg_accumulator / bg_frame_count
                calibrated = True
                print("[PASUL 3/3] DETECTIE ACTIVA.")

            _draw_zone_lines(frame, line_n, line_s, line_e, line_w, w, h)
            cv2.putText(frame, "CALIBRARE FUNDAL...", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 100, 255), 2)
            cv2.imshow("Intersectie Inteligenta", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            continue

        # ── Detecție mișcare + Albastru ──
        diff = cv2.absdiff(gray, np.uint8(background_ref))
        _, motion_mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN,  kernel_small)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_CLOSE, kernel_large)

        motion_contours, _ = cv2.findContours(motion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_clean = np.zeros_like(motion_mask)
        for cnt in motion_contours:
            if cv2.contourArea(cnt) >= MIN_MOTION_AREA:
                cv2.drawContours(motion_clean, [cnt], -1, 255, -1)

        frame_blur = cv2.GaussianBlur(frame, (7, 7), 0)
        hsv        = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2HSV)
        blue_mask  = cv2.inRange(hsv, BLUE_HSV_LOW, BLUE_HSV_HIGH)

        combined_mask = cv2.bitwise_and(blue_mask, motion_clean)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN,  kernel_small)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel_large)

        # ── Procesare per zona ──
        for idx, (x1, y1, x2, y2) in enumerate(zone_rects):
            zone     = zones[idx]
            color_ui = ZONE_COLORS[idx]

            zone_mask = np.zeros_like(combined_mask)
            zone_mask[y1:y2, x1:x2] = combined_mask[y1:y2, x1:x2]

            contours, _ = cv2.findContours(zone_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            detected = False
            for cnt in contours:
                if cv2.contourArea(cnt) >= MIN_CONTOUR_AREA:
                    detected = True
                    cv2.drawContours(frame, [cnt], -1, (0, 255, 255), 2)
                    break

            if detected and not zone.in_cooldown():
                if zone.first_detected is None:
                    zone.first_detected = now
                elapsed = now - zone.first_detected

                if elapsed >= DETECT_TIME and not zone.signal_sent:
                    command = str(idx + 1)
                    if arduino and arduino.is_open:
                        arduino.write(command.encode())
                    print(f"[DETECTIE] Zona {zone.label} confirmata!")
                    zone.start_cooldown()

                # Progress bar UI
                progress = min(elapsed / DETECT_TIME, 1.0)
                cv2.rectangle(frame, (x1 + 5, y1 + 5), (x1 + int((x2 - x1 - 10) * progress), y1 + 13), (0, 255, 255), -1)

            elif not detected and not zone.in_cooldown():
                zone.reset()

            # UI Text si Chenar
            thickness = 3 if detected and not zone.in_cooldown() else 1
            cv2.rectangle(frame, (x1, y1), (x2, y2), color_ui, thickness)

            label_text = f"{zone.label} [COOLDOWN]" if zone.in_cooldown() else zone.label
            cv2.putText(frame, label_text, (x1 + 5, y2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_ui, 2)

        _draw_zone_lines(frame, line_n, line_s, line_e, line_w, w, h)

        # Traseaza un X mare semi-transparent peste centrul mort pentru feedback vizual
        overlay_deadzone = frame.copy()
        cv2.rectangle(overlay_deadzone, (line_w, line_n), (line_e, line_s), (0, 0, 0), -1)
        cv2.addWeighted(overlay_deadzone, 0.3, frame, 0.7, 0, frame)
        cv2.putText(frame, "IGNORAT", (line_w + 10, line_n + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

        cv2.imshow("Intersectie Inteligenta", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if arduino and arduino.is_open:
        arduino.close()


if __name__ == "__main__":
    main()