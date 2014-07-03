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
import qcow2.fuzz

MAX_IMAGE_SIZE = 10*2**20
# Standard sizes
UINT32_S = 4
UINT64_S = 8

# Percentage of fields will be fuzzed
BIAS = random.uniform(0.2, 0.5)


class Field(object):
    """Atomic image element (field)

    The class represents an image field as quadruple of a data format
    of value necessary for its packing to binary form, an offset from
    the beginning of the image, a value and a name.

    The field can be iterated as a list [format, offset, value]
    """
    __slots__ = ('fmt', 'offset', 'value', 'name')

    def __init__(self, fmt, offset, val, name):
        self.fmt = fmt
        self.offset = offset
        self.value = val
        self.name = name

    def __iter__(self):
        return (x for x in [self.fmt, self.offset, self.value])

    def __repr__(self):
        return "Field(fmt='%s', offset=%d, value=%s, name=%s)" % \
            (self.fmt, self.offset, str(self.value), self.name)


class FieldsList(object):
    """List of fields

    The class allows access to a field in the list by its name and joins
    several list in one via in-place addition
    """
    def __init__(self, meta_data=None):
        if meta_data is None:
            self.data = []
        else:
            self.data = [Field(f[0], f[1], f[2], f[3])
                         for f in meta_data]

    def __getitem__(self, name):
        return [x for x in self.data if x.name == name]

    def __iter__(self):
        return (x for x in self.data)

    def __iadd__(self, other):
        self.data += other.data
        return self

    def __len__(self):
        return len(self.data)


class Image(object):
    """ Qcow2 image object

    This class allows to create valid qcow2 images with random structure,
    fuzz them via external qcow2.fuzz module and write to files.
    """
    @staticmethod
    def _size_params():
        """Generate a random file size aligned to a random correct cluster size
        """
        cluster_bits = random.randrange(9, 21)
        cluster_size = 1 << cluster_bits
        # Minimal image size is equal to 5 clusters as for qcow2 empty image
        # created by qemu-img
        file_size = random.randrange(5*cluster_size, MAX_IMAGE_SIZE + 1,
                                     cluster_size)
        return [cluster_bits, file_size]

    @staticmethod
    def _header(cluster_bits, img_size):
        """Generate a random valid header"""
        meta_header = [
            ['>4s', 0, "QFI\xfb", 'magic'],
            ['>I', 4, random.randint(2, 3), 'version'],
            ['>Q', 8, 0, 'backing_file_offset'],
            ['>I', 16, 0, 'backing_file_size'],
            ['>I', 20, cluster_bits, 'cluster_bits'],
            ['>Q', 24, img_size, 'size'],
            ['>I', 32, 0, 'crypt_method'],
            ['>I', 36, 0, 'l1_size'],
            ['>Q', 40, 0, 'l1_table_offset'],
            ['>Q', 48, 0, 'refcount_table_offset'],
            ['>I', 56, 0, 'refcount_table_clusters'],
            ['>I', 60, 0, 'nb_snapshots'],
            ['>Q', 64, 0, 'snapshots_offset'],
            ['>Q', 72, 0, 'incompatible_features'],
            ['>Q', 80, 0, 'compatible_features'],
            ['>Q', 88, 0, 'autoclear_features'],
            # From the e-mail thread for [PATCH] docs: Define refcount_bits
            # value: Only refcount_order = 4 is supported by QEMU at the moment
            ['>I', 96, 4, 'refcount_order'],
            ['>I', 100, 0, 'header_length']
        ]
        v_header = FieldsList(meta_header)

        if v_header['version'][0].value == 2:
            v_header['header_length'][0].value = 72
        else:
            v_header['incompatible_features'][0].value = random.getrandbits(2)
            v_header['compatible_features'][0].value = random.getrandbits(1)
            v_header['header_length'][0].value = 104

        return v_header

    @staticmethod
    def _backing_file_format_ext(header):
        """Generate a random header extension for name of backing file
        format

        If the header doesn't contain information about the backing file,
        this extension is left empty
        """
        offset = struct.calcsize(header['header_length'][0].fmt) + \
                 header['header_length'][0].offset

        if not header['backing_file_offset'][0].value == 0:
            # Till real backup image is not supported, a random valid fmt
            # is set
            ext_data = random.choice(['raw', 'qcow', 'qcow2', 'qed',
                                      'cow', 'vdi', 'vmdk', 'vpc',
                                      'vhdx', 'bochs', 'cloop',
                                      'dmg', 'parallels'])
            ext_data_len = len(ext_data)
            ext_data_padded = '>' + str(ext_data_len) + 's' + \
                              str(7 - (ext_data_len - 1) % 8) + 'x'
            ext = FieldsList([
                ['>I', offset, 0xE2792ACA, 'ext_magic'],
                ['>I', offset + UINT32_S, ext_data_len, 'ext_length'],
                [ext_data_padded, offset + UINT32_S*2, ext_data,
                 'bf_data']
            ])
            offset = ext['bf_data'][0].offset + \
                     struct.calcsize(ext['bf_data'][0].fmt)
        else:
            ext = FieldsList()
        return (ext, offset)

    @staticmethod
    def _feature_name_table_ext(header, offset):
        """Generate a random header extension for names of features used in
        the image

        If all features bit masks in the header are set to zeroes,
        this extension is left empty
        """
        feature_tables = []
        # Current offset + magic and length fields of the feature table
        # extension
        inner_offset = offset + 2*UINT32_S

        # Each tuple is (bit value in the corresponding header field, feature
        # type, number of the bit in the header field, feature name)
        feature_list = [
            (header['incompatible_features'][0].value & 1, 0,
             1, 'dirty bit'),
            (header['incompatible_features'][0].value & 2, 0,
             2, 'corrupt bit'),
            (header['compatible_features'][0].value & 1, 1,
             1, 'lazy refcounts bit')
        ]
        for item in feature_list:
            if not item[0] == 0:
                name_len = len(item[3])
                name_padded_fmt = '>' + str(name_len) + 's' + \
                                  str(46 - name_len) + 'x'
                feature_tables += [['B', inner_offset, item[1], 'feat_type'],
                                   ['B', inner_offset + 1,
                                    item[2], 'feat_bit_number'],
                                   [name_padded_fmt, inner_offset + 2,
                                    item[3], 'feat_name']
                ]
                inner_offset = inner_offset + 2 + \
                               struct.calcsize(name_padded_fmt)

        if not len(feature_tables) == 0:
            # No padding for the extension is necessary, because
            # the extension length = 8 + 48*N is multiple of 8
            ext = FieldsList([
                ['>I', offset, 0x6803f857, 'ext_magic'],
                ['>I', offset + UINT32_S, len(feature_tables)*48,'ext_length']
            ] + feature_tables)
            offset = inner_offset
        else:
            ext = FieldsList()

        return (ext, offset)

    @staticmethod
    def _end_ext(offset):
        """Generate a mandatory header extension marking end of header
        extensions
        """
        ext = FieldsList([
            ['>I', offset, 0, 'ext_magic'],
            ['>I', offset + UINT32_S, 0, 'ext_length']
        ])
        return (ext, offset)

    def __init__(self):
        """Create a random valid qcow2 image with the correct inner structure
        and allowable values
        """
        # Image size is necessary for writing, but the field with it can be
        # fuzzed so it's saved separately.
        cluster_bits, self.image_size = self._size_params()
        self.header = self._header(cluster_bits, self.image_size)
        self.backing_file_format_ext, \
            offset = self._backing_file_format_ext(self.header)
        self.feature_name_table_ext, \
            offset = self._feature_name_table_ext(self.header, offset)
        self.end_ext, offset = self._end_ext(offset)
        # Container for entire image
        self.data = FieldsList()

    def __iter__(self):
        return (x for x in [self.header, self.backing_file_format_ext,
                            self.feature_name_table_ext, self.end_ext])

    def _join(self):
        """Join all image structure elements as header, tables, etc in one
        list of fields
        """
        if len(self.data) == 0:
            for v in self:
                self.data += v

    def fuzz(self, fields_to_fuzz=None):
        """Fuzz an image by corrupting values of a random subset of its fields

        Without parameters the method fuzzes an entire image.
        If 'fields_to_fuzz' is specified then only fields in this list will be
        fuzzed. 'fields_to_fuzz' can contain both individual fields and more
        general image elements as header or tables.
        In the first case the single field will be fuzzed always.
        In the second a random subset of fields will be selected and fuzzed.
        """
        def coin():
            """Return boolean value proportional to a portion of fields to be
            fuzzed
            """
            return random.random() < BIAS

        if fields_to_fuzz is None:
            self._join()
            for field in self.data:
                if coin():
                    field.value = getattr(qcow2.fuzz, field.name)(field.value)
        else:
            for item in fields_to_fuzz:
                if len(item) == 1:
                    for field in self.__dict__[item[0]]:
                        if coin():
                            field.value = getattr(qcow2.fuzz,
                                                  field.name)(field.value)
                else:
                    for field in self.__dict__[item[0]][item[1]]:
                        try:
                            field.value = getattr(qcow2.fuzz, field.name)(
                                field.value)
                        except AttributeError:
                            # Some fields can be skipped depending on
                            # references, e.g. FNT header extension is not
                            # generated for a feature mask header field
                            # equal to zero
                            pass

    def write(self, filename):
        """Writes an entire image to the file"""
        image_file = open(filename, 'w')
        # Create an empty image
        # (sparse if FS supports it or preallocated otherwise)
        image_file.seek(self.image_size - 1)
        image_file.write("\0")
        self._join()
        for field in self.data:
            print field
            image_file.seek(field.offset)
            image_file.write(struct.pack(field.fmt, field.value))

        image_file.close()


def create_image(test_img_path, fields_to_fuzz=None):
    """Create a fuzzed image and write it to the specified file"""
    image = Image()
    image.fuzz(fields_to_fuzz)
    image.write(test_img_path)
