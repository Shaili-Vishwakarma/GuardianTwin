"""
SystemCtrl agent — building actuator control stubs.
"""
import time

# Per-zone timer: tracks when a zone first became dangerous
# Sprinklers only activate after SPRINKLER_DELAY_CYCLES cycles of sustained danger
_zone_danger_since: dict = {}   # zone → unix timestamp when first detected dangerous
SPRINKLER_DELAY_S = 15          # seconds of sustained danger before sprinklers activate


def systemctrl_node(state: dict) -> dict:
    """
    Activate building safety systems based on threat level.
    Idempotent — will not duplicate commands already sent.
    Fire-specific systems (sprinklers) only activate in fire scenario.
    """
    level    = state.get('threat_level', 'none')
    scenario = state.get('scenario', 'fire')
    log      = list(state.get('agent_action_log', []))
    updates  = {}
    now      = time.time()

    # HVAC shutdown at medium+ (both scenarios)
    if level in ('medium', 'high', 'critical') and not state.get('hvac_shutdown'):
        log.append('[SystemCtrl] HVAC shutdown command sent')
        updates['hvac_shutdown'] = True

    # Elevator recall and emergency lighting — FIRE SCENARIO ONLY
    # In attacker scenario, lifts stay operational for evacuation
    if scenario == 'fire':
        if level in ('high', 'critical') and not state.get('elevators_recalled'):
            log.append('[SystemCtrl] Elevator recall command sent')
            log.append('[SystemCtrl] Emergency lighting activated')
            updates['elevators_recalled'] = True
            updates['emergency_lighting'] = True
    else:
        # Attacker scenario: emergency lighting on, but lifts stay ON for evacuation
        if level in ('high', 'critical') and not state.get('emergency_lighting'):
            log.append('[SystemCtrl] Emergency lighting activated')
            updates['emergency_lighting'] = True

    # All clear — restore building systems
    if level == 'none':
        if state.get('hvac_shutdown'):
            log.append('[SystemCtrl] ✅ HVAC restored to normal')
            updates['hvac_shutdown'] = False
        if state.get('elevators_recalled'):
            log.append('[SystemCtrl] ✅ Elevators restored to service')
            updates['elevators_recalled'] = False
        if state.get('emergency_lighting'):
            log.append('[SystemCtrl] ✅ Emergency lighting off')
            updates['emergency_lighting'] = False
        if state.get('suppression_active'):
            log.append('[SystemCtrl] 💧 All sprinklers OFF — incident resolved')
            updates['suppression_active'] = []
            _zone_danger_since.clear()
        updates['agent_action_log'] = log
        return updates

    # ── FIRE SCENARIO ONLY: sprinkler logic ──────────────────────────────────
    if scenario == 'attacker':
        # No sprinklers for attacker scenario — water won't stop an intruder
        updates['suppression_active'] = []
        updates['agent_action_log'] = log
        return updates

    # Suppression — sprinklers activate after SPRINKLER_DELAY_S of sustained fire
    dangerous    = state.get('blocked_zones', [])
    already      = state.get('suppression_active', [])
    heatmap      = state.get('fire_heatmap', {})
    extinguished = state.get('extinguished_zones', [])

    for z in dangerous:
        if z not in _zone_danger_since:
            _zone_danger_since[z] = now
            log.append(f'[SystemCtrl] ⚠ Fire detected in {z} — sprinklers in {SPRINKLER_DELAY_S}s')

    for z in list(_zone_danger_since.keys()):
        if (z not in dangerous and z not in already) or z in extinguished:
            del _zone_danger_since[z]

    still_active = [
        z for z in already
        if heatmap.get(z, {}).get('fire_prob', 0) >= 0.05 and z not in extinguished
    ]
    for z in set(already) - set(still_active):
        log.append(f'[SystemCtrl] 💧 Sprinklers OFF — fire out in {z}')
        _zone_danger_since.pop(z, None)

    if level in ('medium', 'high', 'critical'):
        new_zones = [
            z for z in dangerous
            if z not in still_active
            and z not in extinguished
            and (now - _zone_danger_since.get(z, now)) >= SPRINKLER_DELAY_S
        ]
        for z in new_zones:
            log.append(f'[SystemCtrl] 💧 Sprinklers ON: {z}')
        updates['suppression_active'] = still_active + new_zones
    else:
        updates['suppression_active'] = still_active

    updates['agent_action_log'] = log
    return updates
