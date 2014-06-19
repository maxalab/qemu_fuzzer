# Generator of fuzzed qcow2 images
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
import struct
import fuzz


MAX_IMAGE_SIZE = 10*2**20


def fuzz_struct(structure):
    """Select part of fields in the specified structure and assign them invalid
    values

    From 20% to 50% of all fields will be randomly selected and fuzzed
    """
    extract = random.sample(structure,
                            random.randint(len(structure)/5, len(structure)/2))

    def iter_fuzz(field):
        """Fuzz field value if it's selected

        This auxiliary function replaces short circuit conditions not supported
        in Python 2.4
        """
        if field in extract:
            return (field[0:2] + [getattr(fuzz, field[3])(field[2])] +
                    field[-1:])
        else:
            return field

    return [iter_fuzz(field) for field in structure]


def image_size():
    """Generate a random file size aligned to a random correct cluster size"""
    cluster_bits = random.randrange(9, 21)
    cluster_size = 1 << cluster_bits
    file_size = random.randrange(5*cluster_size,
                                 MAX_IMAGE_SIZE + 1,
                                 cluster_size)
    return [cluster_bits, file_size]


def header(cluster_bits, img_size):
    """Generate a random valid header"""
    magic = "QFI\xfb"
    version = random.randint(2, 3)
    # Next two set to zero while qcow emulation is not supported
    backing_file_offset = 0
    backing_file_size = 0
    crypt_method = random.randint(0, 1)
    # All below are zeroes while a corresponding feature is not supported
    l1_size = 0
    l1_table_offset = 0
    refcount_table_offset = 0
    refcount_table_clusters = 0
    nb_snapshots = 0
    snapshots_offset = 0
    # From the e-mail thread for [PATCH] docs: Define refcount_bits value:
    # Only refcount_order = 4 is supported by QEMU at the moment
    refcount_order = 4
    autoclear_features = 0  # doesn't depend on version
    if version == 2:
        incompatible_features = 0
        compatible_features = 0
        header_length = 72
    else:
        incompatible_features = random.getrandbits(2)
        compatible_features = random.getrandbits(1)
        header_length = 104

    return [
        [0, '>4s', magic, 'magic'],
        [4, '>I', version, 'version'],
        [8, '>Q', backing_file_offset, 'backing_file_offset'],
        [16, '>I', backing_file_size, 'backing_file_size'],
        [20, '>I', cluster_bits, 'cluster_bits'],
        [24, '>Q', img_size, 'size'],
        [32, '>I', crypt_method, 'crypt_method'],
        [36, '>I', l1_size, 'l1_size'],
        [40, '>Q', l1_table_offset, 'l1_table_offset'],
        [48, '>Q', refcount_table_offset, 'refcount_table_offset'],
        [56, '>I', refcount_table_clusters, 'refcount_table_clusters'],
        [60, '>I', nb_snapshots, 'nb_snapshots'],
        [64, '>Q', snapshots_offset, 'snapshots_offset'],
        [72, '>Q', incompatible_features, 'incompatible_features'],
        [80, '>Q', compatible_features, 'compatible_features'],
        [88, '>Q', autoclear_features, 'autoclear_features'],
        [96, '>I', refcount_order, 'refcount_order'],
        [100, '>I', header_length, 'header_length']
    ]


def create_image(test_img_path):
    """Write a fuzzed image to the specified file"""
    image_file = open(test_img_path, 'w')
    cluster_bits, v_image_size = image_size()
    # Create an empty image
    # (sparse if FS supports it or preallocated otherwise)
    image_file.seek(v_image_size - 1)
    image_file.write("\0")
    v_header = header(cluster_bits, v_image_size)  # create a valid header
    v_header = fuzz_struct(v_header)  # fuzz the header

    for field in v_header:
        image_file.seek(field[0])
        image_file.write(struct.pack(field[1], field[2]))
    image_file.close()
