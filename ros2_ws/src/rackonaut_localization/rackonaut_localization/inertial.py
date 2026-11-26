"""Short-horizon propagation from angular velocity and specific force."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

GRAVITY = np.array([0., 0., 9.81])


@dataclass(frozen=True)
class State:
    time: float
    xyz: np.ndarray
    velocity: np.ndarray
    attitude: Rotation


def propagate(state, end, samples, gyro_bias, acceleration_bias):
    position = state.xyz.copy()
    velocity = state.velocity.copy()
    attitude = state.attitude
    time = state.time
    previous = None
    for stamp, gyro, acceleration in samples:
        if stamp <= time:
            previous = gyro, acceleration
            continue
        dt = min(end, stamp) - time
        if dt <= 0.:
            break
        rate, force = previous or (gyro, acceleration)
        attitude *= Rotation.from_rotvec((rate - gyro_bias) * dt)
        linear = attitude.apply(force - acceleration_bias) - GRAVITY
        position += velocity * dt + linear * (.5 * dt * dt)
        velocity += linear * dt
        time += dt
        previous = gyro, acceleration
        if time >= end:
            break
    if time < end:
        position += velocity * (end - time)
    return State(end, position, velocity, attitude)
