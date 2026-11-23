import math
import numpy as np

_rng = np.random.default_rng()   # seeded from OS entropy: unpredictable


def set_seed(seed):
    """For tests only: makes the noise repeatable."""
    global _rng
    _rng = np.random.default_rng(seed)


def laplace_scale(sensitivity, epsilon):
    return sensitivity / epsilon


def gaussian_sigma(sensitivity, epsilon, delta):
    # Classic Gaussian mechanism, valid for 0 < epsilon < 1
    return sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon


def add_noise(true_value, sensitivity, epsilon, mechanism="laplace", delta=1e-5):
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if sensitivity < 0:
        raise ValueError("sensitivity must be non-negative")

    if mechanism == "laplace":
        scale = laplace_scale(sensitivity, epsilon)
        noise = float(_rng.laplace(0.0, scale))
    elif mechanism == "gaussian":
        if epsilon >= 1:
            raise ValueError("gaussian mechanism requires epsilon < 1")
        scale = gaussian_sigma(sensitivity, epsilon, delta)
        noise = float(_rng.normal(0.0, scale))
    else:
        raise ValueError("unknown mechanism")

    return {
        "noisy_value": float(true_value) + noise,
        "noise": noise,
        "scale": scale,
        "mechanism": mechanism,
    }