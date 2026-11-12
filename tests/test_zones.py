import pytest
from vision.main import build_zone_rects

def test_build_zone_rects_disjoint():
    h, w = 480, 640
    line_n, line_s = 120, 360
    line_e, line_w = 480, 160
    
    rects = build_zone_rects(line_n, line_s, line_e, line_w, h, w)
    
    # NORD: (line_w, 0, line_e, line_n) -> (160, 0, 480, 120)
    assert rects[0] == (160, 0, 480, 120)
    # SUD: (line_w, line_s, line_e, h) -> (160, 360, 480, 480)
    assert rects[1] == (160, 360, 480, 480)
    # EST: (line_e, 0, w, h) -> (480, 0, 640, 480)
    assert rects[2] == (480, 0, 640, 480)
    # VEST: (0, 0, line_w, h) -> (0, 0, 160, 480)
    assert rects[3] == (0, 0, 160, 480)

    # Verificare intersectii (sumara)
    # NORD vs VEST: NORD incepe la x=160, VEST termina la x=160 -> Disjuncte (margine comuna)
    assert rects[0][0] >= rects[3][2]
    # NORD vs EST: NORD termina la x=480, EST incepe la x=480 -> Disjuncte
    assert rects[0][2] <= rects[2][0]
    # SUD vs VEST: SUD incepe la x=160, VEST termina la x=160 -> Disjuncte
    assert rects[1][0] >= rects[3][2]
    # SUD vs EST: SUD termina la x=480, EST incepe la x=480 -> Disjuncte
    assert rects[1][2] <= rects[2][0]
