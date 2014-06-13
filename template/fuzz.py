"""Fuzzing functions for qcow2 fields"""
import random


UINT32 = 2**32 - 1
UINT64 = 2**64 - 1


def random_from_intervals(intervals):
    """Select a random integer number from the list of specified intervals

    Each interval is a tuple of lower and upper limits of the interval. The
    limits are included. Intervals in a list should not overlap.
    """
    total = reduce(lambda x, y: x + y[1] - y[0] + 1, intervals, 0)
    r = random.randint(0, total-1) + intervals[0][0]
    temp = zip(intervals, intervals[1:])
    for x in temp:
        r = r + (r > x[0][1])*(x[1][0] - x[0][1] - 1)
    return r


def validator(current, intervals):
    """Return a random value from intervals not equal to the current.

    This function is useful for selection from valid values except current one.
    """
    val = random_from_intervals(intervals)
    if val == current:
        return validator(current, intervals)
    else:
        return val


def selector(current, constraints):
    """Select one value from all defined by constraints

    Each constraint produces one random value satisfying to it. The function
    randomly selects one value satisfying at least one constraint (depending on
    constraints overlaps).
    """
    fuzz_values = [validator(current, c) for c in constraints]
    return random.choice(fuzz_values)


def magic(current):
    """Fuzz magic header field

    The function just returns the current magic value and provides uniformity
    of calls for all fuzzing functions
    """
    return current


def version(current):
    """Fuzz version header field"""
    constraints = [
        [(2, 3)],  # correct values
        [(0, 1), (4, UINT32)]
    ]
    return selector(current, constraints)


def backing_file_offset(current):
    """Fuzz backing file offset header field"""
    constraints = [
        [(1, UINT64)]
    ]
    return selector(current, constraints)


def backing_file_size(current):
    """Fuzz backing file size header field"""
    constraints = [
        [(1, UINT32)]
    ]
    return selector(current, constraints)


def cluster_bits(current):
    """Fuzz cluster bits header field"""
    constraints = [
        [(9, 20)],  # correct values
        [(0, 9), (20, UINT32)]
    ]
    return selector(current, constraints)


def size(current):
    """Fuzz image size header field"""
    constraints = [
        [(0, UINT64)]
    ]
    return selector(current, constraints)


def crypt_method(current):
    """Fuzz crypt method header field"""
    constraints = [
        [(0, 1)],
        [(2, UINT32)]
    ]
    return selector(current, constraints)


def l1_size(current):
    """Fuzz L1 table size header field"""
    constraints = [
        [(1, UINT32)]
    ]
    return selector(current, constraints)


def l1_table_offset(current):
    """Fuzz L1 table offset header field"""
    constraints = [
        [(1, UINT64)]
    ]
    return selector(current, constraints)


def refcount_table_offset(current):
    """Fuzz refcount table offset header field"""
    constraints = [
        [(1, UINT64)]
    ]
    return selector(current, constraints)


def refcount_table_clusters(current):
    """Fuzz refcount table clusters header field"""
    constraints = [
        [(1, UINT32)]
    ]
    return selector(current, constraints)


def nb_snapshots(current):
    """Fuzz number of snapshots header field"""
    constraints = [
        [(1, UINT32)]
    ]
    return selector(current, constraints)


def snapshots_offset(current):
    """Fuzz snapshots offset header field"""
    constraints = [
        [(1, UINT64)]
    ]
    return selector(current, constraints)
