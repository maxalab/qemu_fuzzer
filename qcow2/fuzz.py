# Fuzzing functions for qcow2 fields
#
# Copyright (C) 2014 Maria Kustova <maria.k@catit.be>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import random


UINT32 = 2**32 - 1
UINT64 = 2**64 - 1
# Most significant bit orders
UINT32_M = 31
UINT64_M = 63


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


def random_bits(bit_ranges):
    """Generate random binary mask with ones in the specified bit ranges

    Each bit_ranges is a list of tuples of lower and upper limits of bit
    positions will be fuzzed. The limits are included. Random amount of bits
    in range limits will be set to ones. The mask is returned in decimal
    integer format.
    """
    bit_numbers = []
    # Select random amount of random positions in bit_ranges
    for rng in bit_ranges:
        bit_numbers += random.sample(range(rng[0], rng[1] + 1),
                                     random.randint(0, rng[1] - rng[0] + 1))
    val = 0
    # Set bits on selected possitions to ones
    for bit in bit_numbers:
        val |= 1 << bit
    return val


def validator(current, intervals):
    """Return a random value from intervals not equal to the current.

    This function is useful for selection from valid values except current one.
    """
    val = random_from_intervals(intervals)
    if val == current:
        return validator(current, intervals)
    else:
        return val


Backing file format namedef bit_validator(current, bit_ranges):
    """Return a random bit mask not equal to the current.

    This function is useful for selection from valid values except current one.
    """

    val = random_bits(bit_ranges)
    if val == current:
        return bit_validator(current, bit_ranges)
    else:
        return val


def selector(current, constraints, is_bitmask=None):
    """Select one value from all defined by constraints

    Each constraint produces one random value satisfying to it. The function
    randomly selects one value satisfying at least one constraint (depending on
    constraints overlaps).
    """
    if is_bitmask is None:
        validate = validator
    else:
        validate = bit_validator

    def iter_validate(c):
        """Apply validate() only to constraints represented as lists

        This auxiliary function replaces short circuit conditions not supported
        in Python 2.4
        """
        if type(c) == list:
            return validate(current, c)
        else:
            return c
    fuzz_values = [iter_validate(c) for c in constraints]
    # Remove current for cases it's implicitly specified in constraints
    # Duplicate validator functionality to prevent decreasing of probability
    # to get one of allowable values
    # TODO: remove validators after implementation of intelligent selection
    # of fields will be fuzzed
    try:
        fuzz_values.remove(current)
    except ValueError:
        pass
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
        [(0, UINT64)]
    ]
    return selector(current, constraints)


def backing_file_size(current):
    """Fuzz backing file size header field"""
    constraints = [
        [(0, UINT32)]
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
        [(0, UINT32)]
    ]
    return selector(current, constraints)


def l1_table_offset(current):
    """Fuzz L1 table offset header field"""
    constraints = [
        [(0, UINT64)]
    ]
    return selector(current, constraints)


def refcount_table_offset(current):
    """Fuzz refcount table offset header field"""
    constraints = [
        [(0, UINT64)]
    ]
    return selector(current, constraints)


def refcount_table_clusters(current):
    """Fuzz refcount table clusters header field"""
    constraints = [
        [(0, UINT32)]
    ]
    return selector(current, constraints)


def nb_snapshots(current):
    """Fuzz number of snapshots header field"""
    constraints = [
        [(0, UINT32)]
    ]
    return selector(current, constraints)


def snapshots_offset(current):
    """Fuzz snapshots offset header field"""
    constraints = [
        [(0, UINT64)]
    ]
    return selector(current, constraints)


def incompatible_features(current):
    """Fuzz incompatible features header field"""
    constraints = [
        [(0, 1)],  # allowable values
        [(0, UINT64_M)]
    ]
    return selector(current, constraints, 1)


def compatible_features(current):
    """Fuzz compatible features header field"""
    constraints = [
        [(0, UINT64_M)]
    ]
    return selector(current, constraints, 1)


def autoclear_features(current):
    """Fuzz autoclear features header field"""
    constraints = [
        [(0, UINT64_M)]
    ]
    return selector(current, constraints, 1)


def refcount_order(current):
    """Fuzz number of refcount order header field"""
    constraints = [
        [(0, UINT32)]
    ]
    return selector(current, constraints)


def header_length(current):
    """Fuzz number of refcount order header field"""
    constraints = [
        72,
        104,
        [(0, UINT32)]
    ]
    return selector(current, constraints)
