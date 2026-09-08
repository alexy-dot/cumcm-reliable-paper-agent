"""Candidate effective heat-transfer models for the supplied 2020 A experiment."""
import numpy as np
from scipy.signal import lfilter
from scipy.linalg import expm

LENGTH = 25 + 11 * 30.5 + 10 * 5 + 25
ZONE_STARTS = 25 + np.arange(11) * 35.5
BASE_SETTINGS = np.array([175., 195., 235., 255.])


def air_temperature(x, settings, parameters, mode="mixing"):
    x = np.asarray(x, dtype=float)
    a, b, c, d = settings
    nodes = [0, 25, 197.5, 202.5, 233, 238, 268.5, 273.5, 339.5, 344.5, LENGTH]
    values = [25, a, a, b, b, c, c, d, d, 25, 25]
    air = np.interp(x, nodes, values)
    if mode in {"mixing", "radiative"}:
        _, entry_scale, cooling_scale = parameters[:3]
        front = (x >= 0) & (x < 25)
        air[front] = 25 + (a - 25) * np.expm1(x[front] / entry_scale) / np.expm1(25 / entry_scale)
        cooling = x > 339.5
        air[cooling] = 25 + (d - 25) * np.exp(-(x[cooling] - 339.5) / cooling_scale)
    if mode == "two_node":
        scale = parameters[4]
        front = (x >= 0) & (x < 25)
        air[front] = 25 + (a - 25) * np.expm1(x[front] / scale) / np.expm1(25 / scale)
    if mode == "smooth_two_node":
        entry_extra, width = parameters[4:6]
        def smooth(s):
            s = np.clip(s, 0, 1)
            return s * s * (3 - 2 * s)
        air = 25 + (a - 25) * smooth(x / (25 + entry_extra))
        for center, change in [(200, b - a), (235.5, c - b), (271, d - c)]:
            air += change * smooth((x - center + width) / (2 * width))
        air += (25 - d) * np.clip((x - 339.5) / 5, 0, 1)
    return air


def _two_node_segment(forcing, dt, alpha, beta, gamma, state):
    continuous = np.array([[-alpha - beta, beta, alpha], [gamma, -gamma, 0], [0, 0, 0]])
    discrete = expm(continuous * dt)
    matrix, input_vector = discrete[:2, :2], discrete[:2, 2]
    trace, determinant = np.trace(matrix), np.linalg.det(matrix)
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    natural_weights = np.linalg.solve(eigenvectors, state)
    natural = eigenvectors @ (natural_weights[:, None] * eigenvalues[:, None] ** np.arange(1, len(forcing) + 1))
    output = np.zeros((2, len(forcing)))
    for index in range(2):
        numerator = [input_vector[index], matrix[index] @ input_vector - trace * input_vector[index]]
        output[index] = lfilter(numerator, [1, -trace, determinant], forcing) + natural[index]
    return output[1], output[:, -1]


def temperature_curve(settings, speed, parameters, mode="mixing", dx=0.25):
    # Uniform x spacing makes the exponential state recurrence exactly computable
    # for midpoint piecewise-constant forcing. Independent validation uses an ODE solver.
    steps = int(np.ceil(LENGTH / dx))
    x = np.linspace(0, LENGTH, steps + 1)
    dt = (x[1] - x[0]) / (speed / 60)
    if len(parameters) == 7:
        midpoint = (x[:-1] + x[1:]) / 2
        drive = zoned_drive(midpoint, settings, parameters)
        tau_index = np.searchsorted([200., 235.5, 271., 342.], midpoint)
        rates = 1 / np.asarray(parameters[:5])[tau_index]
        exponents = np.cumsum(rates * dt)
        deviation = np.exp(-exponents) * np.cumsum(-np.expm1(-rates * dt) * np.exp(exponents) * (drive - 25))
        return x / (speed / 60), np.r_[25., deviation + 25]
    if len(parameters) in (5, 6):
        mode = "two_node" if len(parameters) == 5 else "smooth_two_node"
        midpoint = (x[:-1] + x[1:]) / 2
        forcing = air_temperature(midpoint, settings, parameters, mode) - 25
        split = int(np.searchsorted(midpoint, 342.))
        alpha_hot, alpha_cold, beta, gamma = parameters[:4]
        hot, state = _two_node_segment(forcing[:split], dt, alpha_hot, beta, gamma, np.zeros(2))
        cold, _ = _two_node_segment(forcing[split:], dt, alpha_cold, beta, gamma, state)
        return x / (speed / 60), np.r_[25., hot + 25, cold + 25]
    if len(parameters) == 4 and mode != "baseline":
        mode = "radiative"
    alpha = np.exp(-dt / parameters[0])
    forcing = air_temperature((x[:-1] + x[1:]) / 2, settings, parameters, mode)
    if mode == "radiative":
        rate = heat_rate(forcing, parameters)
        exponents = np.cumsum(rate * dt)
        deviation = np.exp(-exponents) * np.cumsum(-np.expm1(-rate * dt) * np.exp(exponents) * (forcing - 25))
    else:
        deviation = lfilter([1 - alpha], [1, -alpha], forcing - 25)
    temperature = np.r_[25., deviation + 25]
    return x / (speed / 60), temperature


def heat_rate(air, parameters):
    # Effective linearized radiation h_r scales approximately with absolute T^3.
    fraction = parameters[3] if len(parameters) == 4 else 0.
    return ((1 - fraction) + fraction * ((np.asarray(air) + 273.15) / 448.15) ** 3) / parameters[0]


def zoned_drive(x, settings, parameters):
    # Cooling drive represents an effective thermal reservoir, NOT measured air
    # temperature or an override of the 25 C cooling-zone controller setting.
    drive = np.interp(x, [0, 25, 197.5, 202.5, 233, 238, 268.5, 273.5, 339.5, LENGTH],
                      [25, settings[0], settings[0], settings[1], settings[1], settings[2], settings[2], settings[3], settings[3], 25])
    s = np.clip(np.asarray(x) / (25 + parameters[5]), 0, 1)
    front = np.asarray(x) < 25 + parameters[5]
    drive[front] = 25 + (settings[0] - 25) * (3 * s[front] ** 2 - 2 * s[front] ** 3)
    cooling = np.asarray(x) > 339.5
    drive[cooling] = 25 + (settings[3] - 25) * np.exp(-(np.asarray(x)[cooling] - 339.5) / parameters[6])
    return drive


def crossing(t, temperature, level, ascending=True):
    delta = temperature - level
    hit = np.where((delta[:-1] <= 0) & (delta[1:] > 0) if ascending
                   else (delta[:-1] > 0) & (delta[1:] <= 0))[0]
    if not len(hit):
        return None
    i = hit[0] if ascending else hit[-1]
    return float(t[i] + (level - temperature[i]) / (temperature[i + 1] - temperature[i]) * (t[i + 1] - t[i]))


def curve_metrics(settings, speed, parameters, dx=0.25):
    t, temp = temperature_curve(settings, speed, parameters, dx=dx)
    peak_index = int(np.argmax(temp))
    peak_time, peak = float(t[peak_index]), float(temp[peak_index])
    if 0 < peak_index < len(temp) - 1:
        left, middle, right = temp[peak_index - 1:peak_index + 2]
        denominator = left - 2 * middle + right
        if denominator < 0:
            offset = .5 * (left - right) / denominator
            peak_time += float(offset * (t[1] - t[0]))
            peak = float(middle - .25 * (left - right) * offset)
    t150, t190, up, down = (crossing(t, temp, 150), crossing(t, temp, 190),
                           crossing(t, temp, 217), crossing(t, temp, 217, False))
    # Invalid threshold crossings remain infeasible, never converted into a result.
    soak = t190 - t150 if t150 is not None and t190 is not None else -1.
    liquid = down - up if up is not None and down is not None else -1.
    area, symmetry = 0., 1e3
    if up is not None and down is not None and peak > 217:
        mask = (t > up) & (t < peak_time)
        area = float(np.trapezoid(np.r_[0., temp[mask] - 217, peak - 217], np.r_[up, t[mask], peak_time]))
        duration = max(peak_time - up, down - peak_time)
        u = np.linspace(0, duration, 401)
        left = np.maximum(np.interp(peak_time - u, t, temp, left=25, right=25) - 217, 0)
        right = np.maximum(np.interp(peak_time + u, t, temp, left=25, right=25) - 217, 0)
        symmetry = float(np.trapezoid((left - right) ** 2, u) / (duration * (peak - 217) ** 2))
    if len(parameters) == 7:
        position = t * (speed / 60)
        drive = zoned_drive(position, settings, parameters)
        rates = 1 / np.asarray(parameters[:5])[np.searchsorted([200., 235.5, 271., 342.], position)]
        slope = (drive - temp) * rates
    elif len(parameters) in (5, 6):
        slope = np.gradient(temp, t)
    else:
        air = air_temperature(t * (speed / 60), settings, parameters)
        slope = (air - temp) * heat_rate(air, parameters)
    return {"peak": peak, "peak_time": peak_time, "max_rise": float(np.max(slope)),
            "max_cooling": float(-np.min(slope)), "soak_150_190": float(soak),
            "time_above_217": float(liquid), "area_rising_above_217": area,
            "symmetry": symmetry, "t217_up": up, "t217_down": down}


def margins(metrics):
    return np.array([3 - metrics["max_rise"], 3 - metrics["max_cooling"],
                     metrics["soak_150_190"] - 60, 120 - metrics["soak_150_190"],
                     metrics["time_above_217"] - 40, 90 - metrics["time_above_217"],
                     metrics["peak"] - 240, 250 - metrics["peak"]])
