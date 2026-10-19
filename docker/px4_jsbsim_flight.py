"""Opt-in normal-estimator PX4 takeoff, hover, reposition/yaw and landing client."""
import json
import math
import sys
import struct
import time


def parameter_value(message):
    """PX4 uses MAVLink bytewise integer parameter encoding, not float casting."""
    formats = {1: "B", 2: "b", 3: "H", 4: "h", 5: "I", 6: "i"}
    if message.param_type == 9:
        return message.param_value
    if message.param_type not in formats:
        raise ValueError(f"unsupported PX4 parameter type {message.param_type}")
    return struct.unpack_from("<"+formats[message.param_type], struct.pack("<f", message.param_value))[0]


def flight_client(endpoint):
    from pymavlink import mavutil
    mav = mavutil.mavlink
    link = mavutil.mavlink_connection(endpoint, source_system=254)
    latest, events, samples = {}, [], []
    last_heartbeat = 0

    def pump(timeout=.2):
        nonlocal last_heartbeat
        if time.monotonic()-last_heartbeat > 1:
            link.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            last_heartbeat = time.monotonic()
        msg = link.recv_match(blocking=True, timeout=timeout)
        if msg is not None and msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
            latest[msg.get_type()] = msg
            if msg.get_type() == "STATUSTEXT":
                events.append(msg.text)
                print(msg.text, file=sys.stderr, flush=True)
            return msg
        return None

    def wait(predicate, timeout, description):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        raise RuntimeError(f"timeout: {description}; recent status: {events[-12:]}")

    def command(command_id, *values):
        latest.pop("COMMAND_ACK", None)
        link.mav.command_long_send(1, 1, command_id, 0, *(list(values)+[0]*(7-len(values))))
        wait(lambda: latest.get("COMMAND_ACK") and latest["COMMAND_ACK"].command == command_id,
             5, f"ACK {command_id}")
        ack = latest["COMMAND_ACK"]
        assert ack.result in (mav.MAV_RESULT_ACCEPTED, mav.MAV_RESULT_IN_PROGRESS), ack.to_dict()

    def armed():
        return bool(latest["HEARTBEAT"].base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)

    def altitude():
        return latest["GLOBAL_POSITION_INT"].relative_alt/1000

    try:
        wait(lambda: "HEARTBEAT" in latest, 15, "PX4 heartbeat")
        assert latest["HEARTBEAT"].autopilot == mav.MAV_AUTOPILOT_PX4
        link.target_system, link.target_component = 1, 1
        for message_id in (mav.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, mav.MAVLINK_MSG_ID_ATTITUDE,
                           mav.MAVLINK_MSG_ID_ESTIMATOR_STATUS):
            command(mav.MAV_CMD_SET_MESSAGE_INTERVAL, message_id, 100000)
        wait(lambda: "GLOBAL_POSITION_INT" in latest and "ATTITUDE" in latest and
             "ESTIMATOR_STATUS" in latest and latest["ESTIMATOR_STATUS"].flags & 1 and
             latest["ESTIMATOR_STATUS"].flags & 16, 60, "normal EKF attitude and absolute position")
        params = {}
        for name in ("EKF2_EN", "IMU_INTEG_RATE", "CA_ROTOR_COUNT", "PWM_MAIN_FUNC1", "PWM_MAIN_FUNC4"):
            latest.pop("PARAM_VALUE", None)
            link.mav.param_request_read_send(1, 1, name.encode(), -1)
            wait(lambda: latest.get("PARAM_VALUE") and latest["PARAM_VALUE"].param_id == name, 5, name)
            params[name] = parameter_value(latest["PARAM_VALUE"])
        assert params == {"EKF2_EN": 1, "IMU_INTEG_RATE": 400, "CA_ROTOR_COUNT": 4,
                          "PWM_MAIN_FUNC1": 101, "PWM_MAIN_FUNC4": 104}, params
        position = latest["GLOBAL_POSITION_INT"]
        target_alt = (position.alt-position.relative_alt)/1000+5
        command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        wait(armed, 10, "normal arming (no force-arm)")
        command(mav.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, float("nan"),
                position.lat*1e-7, position.lon*1e-7, target_alt)
        wait(lambda: altitude() >= 4.5, 40, "takeoff to 5m")
        settle = time.monotonic()+5
        while time.monotonic() < settle:
            pump()
        origin = latest["GLOBAL_POSITION_INT"]
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            msg = pump()
            if msg and msg.get_type() == "GLOBAL_POSITION_INT":
                attitude = latest["ATTITUDE"]
                n = (msg.lat-origin.lat)*1e-7*111319.5
                e = (msg.lon-origin.lon)*1e-7*111319.5*math.cos(math.radians(msg.lat*1e-7))
                sample = {"altitude": altitude(), "drift": math.hypot(n, e),
                          "roll": attitude.roll, "pitch": attitude.pitch}
                samples.append(sample)
                assert 3 <= sample["altitude"] <= 7 and sample["drift"] < 4, sample
                assert abs(sample["roll"]) < .45 and abs(sample["pitch"]) < .45, sample
        assert len(samples) >= 20, "insufficient hover samples"
        position = latest["GLOBAL_POSITION_INT"]
        latest.pop("COMMAND_ACK", None)
        link.mav.command_int_send(1, 1, mav.MAV_FRAME_GLOBAL, mav.MAV_CMD_DO_REPOSITION,
                                  0, 0, -1, 1, 0, 90, position.lat, position.lon, target_alt)
        wait(lambda: latest.get("COMMAND_ACK") and latest["COMMAND_ACK"].command == mav.MAV_CMD_DO_REPOSITION,
             5, "reposition/yaw ACK")
        assert latest["COMMAND_ACK"].result == mav.MAV_RESULT_ACCEPTED, latest["COMMAND_ACK"].to_dict()
        wait(lambda: abs((latest["GLOBAL_POSITION_INT"].hdg/100-90+180)%360-180) < 15,
             30, "yaw to 90 degrees")
        command(mav.MAV_CMD_NAV_LAND, 0, 0, 0, float("nan"), float("nan"), float("nan"), 0)
        wait(lambda: not armed(), 60, "landing and auto-disarm")
        assert altitude() < .5, altitude()
        print(json.dumps({"passed": True, "parameters": params, "hover_samples": samples,
                          "landed_altitude": altitude(), "status_text": events}))
    finally:
        link.close()
