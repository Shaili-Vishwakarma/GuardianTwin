"""
SystemCtrl agent — building actuator control stubs.
"""


def systemctrl_node(state: dict) -> dict:
    """
    Activate building safety systems based on threat level.
    Idempotent — will not duplicate commands already sent.
    """
    level = state.get('threat_level', 'none')
    log = list(state.get('agent_action_log', []))
    updates = {}

    # HVAC shutdown at medium+
    if level in ('medium', 'high', 'critical') and not state.get('hvac_shutdown'):
        log.append('[SystemCtrl] HVAC shutdown command sent')
        updates['hvac_shutdown'] = True

    # Elevator recall and emergency lighting at high+
    if level in ('high', 'critical') and not state.get('elevators_recalled'):
        log.append('[SystemCtrl] Elevator recall command sent')
        log.append('[SystemCtrl] Emergency lighting activated')
        updates['elevators_recalled'] = True
        updates['emergency_lighting'] = True

    # Suppression for zones with fire_prob > 0.6
    dangerous = state.get('blocked_zones', [])
    already = state.get('suppression_active', [])
    heatmap = state.get('fire_heatmap', {})
    new_zones = [
        z for z in dangerous
        if z not in already and heatmap.get(z, {}).get('fire_prob', 0) > 0.6
    ]
    for z in new_zones:
        log.append(f'[SystemCtrl] Suppression activated: {z}')
    updates['suppression_active'] = already + new_zones
    updates['agent_action_log'] = log

    return updates
