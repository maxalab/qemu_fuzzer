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
from itertools import repeat
import copy

MAX_IMAGE_SIZE = 10*2**20
# Standard sizes
UINT32_S = 4
UINT64_S = 8

# Percentage of fields will be fuzzed
BIAS = random.uniform(0.1, 0.4)


class Field(object):
    """Describes an image field as a triplet of a data format necessary for
    packing, an offset to the beginning of the image and value of the field.

    Can be iterated as a list [format, offset, value]
    """
    __slots__ = ('fmt', 'offset', 'value')

    def __init__(self, fmt, offset, val):
        self.fmt = fmt
        self.offset = offset
        self.value = val

    def __iter__(self):
        return (x for x in [self.fmt, self.offset, self.value])

    def __repr__(self):
        return "Field(fmt='%s', offset=%d, value=%s)" % (self.fmt, self.offset,
                                                         str(self.value))


def walk(v_struct, func):
    """Walk via structure and apply the specified function to all its non-list
    and non-dict elements
    """
    if isinstance(v_struct, list):
        for item in v_struct:
            walk(item, func)
    else:
        for k, v in v_struct.items():
            if isinstance(v, list):
                walk(v, func)
            else:
                func(v, k)


def fuzz_struct(structure):
    """Select part of fields in the specified structure and assign them invalid
    values

    """
    def coin():
        """Return boolean value proportionally to a portion of fields to be
        fuzzed
        """
        return random.random() < BIAS

    def iter_fuzz(field, name):
        """Fuzz field value if it's selected

        This auxiliary function replaces short circuit conditions not supported
        in Python 2.4
        """
        if coin():
            field.value = getattr(fuzz, name)(field.value)

    tmp = copy.deepcopy(structure)
    walk(tmp, iter_fuzz)

    return tmp


def image_size():
    """Generate a random file size aligned to a random correct cluster size"""
    cluster_bits = random.randrange(9, 21)
    cluster_size = 1 << cluster_bits
    file_size = random.randrange(5*cluster_size, MAX_IMAGE_SIZE + 1,
                                 cluster_size)
    return [cluster_bits, file_size]


def header(cluster_bits, img_size):
    """Generate a random valid header"""
    meta_header = [
        ['>4s', 0, 'magic'],
        ['>I', 4, 'version'],
        ['>Q', 8, 'backing_file_offset'],
        ['>I', 16, 'backing_file_size'],
        ['>I', 20, 'cluster_bits'],
        ['>Q', 24, 'size'],
        ['>I', 32, 'crypt_method'],
        ['>I', 36, 'l1_size'],
        ['>Q', 40, 'l1_table_offset'],
        ['>Q', 48, 'refcount_table_offset'],
        ['>I', 56, 'refcount_table_clusters'],
        ['>I', 60, 'nb_snapshots'],
        ['>Q', 64, 'snapshots_offset'],
        ['>Q', 72, 'incompatible_features'],
        ['>Q', 80, 'compatible_features'],
        ['>Q', 88, 'autoclear_features'],
        ['>I', 96, 'refcount_order'],
        ['>I', 100, 'header_length']
    ]
    values = repeat(0)
    v_header = dict((f[2], Field(f[0], f[1], values.next()))
                    for f in meta_header)

    # Setup of valid values
    v_header['magic'].value = "QFI\xfb"
    v_header['version'].value = random.randint(2, 3)
    v_header['cluster_bits'].value = cluster_bits
    v_header['size'].value = img_size
    if v_header['version'].value == 2:
        v_header['header_length'].value = 72
    else:
        v_header['incompatible_features'].value = random.getrandbits(2)
        v_header['compatible_features'].value = random.getrandbits(1)
        v_header['header_length'].value = 104
    # ---------DEBUG----------
    v_header['backing_file_offset'].value = 480
    # ---------DEBUG----------

    # From the e-mail thread for [PATCH] docs: Define refcount_bits value:
    # Only refcount_order = 4 is supported by QEMU at the moment
    v_header['refcount_order'].value = 4

    return v_header


def header_extensions(header):
    """Generate a random valid header"""
    output = []
    start_offset = struct.calcsize(header['header_length'].fmt) + \
                   header['header_length'].offset

    # Backing file format
    if not header['backing_file_offset'].value == 0:
        # Till real backup image is not supported, a random valid fmt is set
        backing_img_fmt = random.choice(['raw', 'qcow', 'qcow2', 'qed',
                                         'cow', 'vdi', 'vmdk', 'vpc',
                                         'vhdx', 'bochs', 'cloop',
                                         'dmg', 'parallels'])
        bi_fmt_len = len(backing_img_fmt)
        bf_fmt_padded = '>' + str(bi_fmt_len) + 's' + \
                        str(7 - (bi_fmt_len - 1) % 8) + 'x'
        bf_ext = dict([('ext_magic', Field('>I', start_offset, 0xE2792ACA)),
                       ('ext_length', Field('>I', start_offset + UINT32_S,
                                            bi_fmt_len)),
                       ('bf_data', Field(bf_fmt_padded, start_offset +
                                         UINT32_S*2, backing_img_fmt))])
        output.append(bf_ext)
        start_offset = bf_ext['bf_data'].offset + \
                       struct.calcsize(bf_ext['bf_data'].fmt)

    feature_tables = []
    # Current offset + magic and length fields of the feature table extension
    inner_offset = start_offset + 2*UINT32_S

    # Each tuple is (bit value in the corresponding header field, feature type,
    # number of the bit in the header field, feature name
    # TODO: Replace hardcode with generation of feature_list
    feature_list = [
        (header['incompatible_features'].value & 1, 0, 1, 'dirty bit'),
        (header['incompatible_features'].value & 2, 0, 2, 'corrupt bit'),
        (header['compatible_features'].value & 1, 1, 1, 'lazy refcounts bit')
    ]
    for item in feature_list:
        if not item[0] == 0:
            name_len = len(item[3])
            name_padded_fmt = '>' + str(name_len) + 's' + \
                              str(46 - name_len) + 'x'
            feature = dict([
                ('feat_type', Field('B', inner_offset, item[1])),
                ('feat_bit_number', Field('B', inner_offset + 1, item[2])),
                ('feat_name', Field(name_padded_fmt, inner_offset + 2,
                                    item[3])),
            ])
            feature_tables.append(feature)
            inner_offset = feature['feat_name'].offset + \
                           struct.calcsize(feature['feat_name'].fmt)

    if not len(feature_tables) == 0:
        # No padding for the extension is necessary, because
        # the extension length = 8 + 48*N is multiple of 8
        fnt_ext = dict([('ext_magic', Field('>I', start_offset, 0x6803f857)),
                        ('ext_length', Field('>I', start_offset + UINT32_S,
                                             len(feature_tables)*48)),
                        ('fnt_data', feature_tables)])
        output.append(fnt_ext)
        start_offset = inner_offset

    end_ext = dict([
        ('ext_magic', Field('>I', start_offset, 0)),
        ('ext_length', Field('>I', start_offset + UINT32_S, 0))
    ])
    output.append(end_ext)

    return output


def create_image(test_img_path):
    """Write a fuzzed image to the specified file"""
    image_file = open(test_img_path, 'w')
    cluster_bits, v_image_size = image_size()
    # Create an empty image
    # (sparse if FS supports it or preallocated otherwise)
    image_file.seek(v_image_size - 1)
    image_file.write("\0")
    # Image as inner references
    meta_img = [
        lambda x: header(cluster_bits, v_image_size),
        lambda x: header_extensions(x[0])
    ]

    # Valid image
    img = []

    for ref in meta_img:
        img.append(ref(img))

    # Fuzzed image
    img_fuzzed = [fuzz_struct(substruct) for substruct in img]

    # Writing to file
    def write_field(field, _):
        """Write a field to file"""
        image_file.seek(field.offset)
        image_file.write(struct.pack(field.fmt, field.value))

    walk(img_fuzzed, write_field)
    image_file.close()
