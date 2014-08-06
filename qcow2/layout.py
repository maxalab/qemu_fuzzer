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
from math import ceil

MAX_IMAGE_SIZE = 10 * (1 << 20)
# Standard sizes
UINT32_S = 4
UINT64_S = 8


class Field(object):

    """Atomic image element (field).

    The class represents an image field as quadruple of a data format
    of value necessary for its packing to binary form, an offset from
    the beginning of the image, a value and a name.

    The field can be iterated as a list [format, offset, value].
    """

    __slots__ = ('fmt', 'offset', 'value', 'name')

    def __init__(self, fmt, offset, val, name):
        self.fmt = fmt
        self.offset = offset
        self.value = val
        self.name = name

    def __iter__(self):
        return iter([self.fmt, self.offset, self.value])

    def __repr__(self):
        return "Field(fmt='%s', offset=%d, value=%s, name=%s)" % \
            (self.fmt, self.offset, str(self.value), self.name)


class FieldsList(object):

    """List of fields.

    The class allows access to a field in the list by its name and joins
    several list in one via in-place addition.
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
        return iter(self.data)

    def __iadd__(self, other):
        self.data += other.data
        return self

    def __len__(self):
        return len(self.data)


class Image(object):

    """ Qcow2 image object.

    This class allows to create qcow2 images with random valid structures and
    values, fuzz them via external qcow2.fuzz module and write the result to
    a file.
    """

    @staticmethod
    def _size_params():
        """Generate a random image size aligned to a random correct
        cluster size.
        """
        cluster_bits = random.randrange(9, 21)
        cluster_size = 1 << cluster_bits
        img_size = random.randrange(0, MAX_IMAGE_SIZE + 1, cluster_size)
        return (cluster_bits, img_size)

    @staticmethod
    def _get_available_clusters(used, number):
        """Return a set of indices of not allocated clusters.

        'used' contains indices of currently allocated clusters.
        All clusters that cannot be allocated between 'used' clusters will have
        indices appended to the end of 'used'.
        """
        append_id = max(used) + 1
        free = set(range(1, append_id)) - used
        if len(free) >= number:
            return set(random.sample(free, number))
        else:
            return free | set(range(append_id, append_id + number - len(free)))

    @staticmethod
    def _get_adjacent_clusters(used, size):
        """Return an index of the first cluster in the sequence of free ones.

        'used' contains indices of currently allocated clusters. 'size' is the
        length of the sequence of free clusters.
        If the sequence of 'size' is not available between 'used' clusters, its
        first index will be append to the end of 'used'.
        """
        def get_cluster_id(lst, length):
            """Return the first index of the sequence of the specified length
            or None if the sequence cannot be inserted in the list.
            """
            if len(lst) != 0:
                pairs = []
                pair = (lst[0], 1)
                for i in range(1, len(lst)):
                    if lst[i] == lst[i-1] + 1:
                        pair = (lst[i], pair[1] + 1)
                    else:
                        pairs.append(pair)
                        pair = (lst[i], 1)
                pairs.append(pair)
                random.shuffle(pairs)
                for x, s in pairs:
                    if s >= length:
                        return x - length + 1
            return None

        append_id = max(used) + 1
        free = list(set(range(1, append_id)) - used)
        idx = get_cluster_id(free, size)
        if idx is None:
            return append_id
        else:
            return idx

    @staticmethod
    def _alloc_data(img_size, cluster_size):
        """Return a set of random indices of clusters allocated for guest data.
        """
        num_of_cls = img_size/cluster_size
        return set(random.sample(range(1, num_of_cls + 1),
                                 random.randint(0, num_of_cls)))

    def create_header(self, cluster_bits, backing_file_name=None):
        """Generate a random valid header."""
        meta_header = [
            ['>4s', 0, "QFI\xfb", 'magic'],
            ['>I', 4, random.randint(2, 3), 'version'],
            ['>Q', 8, 0, 'backing_file_offset'],
            ['>I', 16, 0, 'backing_file_size'],
            ['>I', 20, cluster_bits, 'cluster_bits'],
            ['>Q', 24, self.image_size, 'size'],
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
            # Only refcount_order = 4 is supported by current (07.2014)
            # implementation of QEMU
            ['>I', 96, 4, 'refcount_order'],
            ['>I', 100, 0, 'header_length']
        ]
        self.header = FieldsList(meta_header)

        if self.header['version'][0].value == 2:
            self.header['header_length'][0].value = 72
        else:
            self.header['incompatible_features'][0].value = \
                                                        random.getrandbits(2)
            self.header['compatible_features'][0].value = random.getrandbits(1)
            self.header['header_length'][0].value = 104

        max_header_len = struct.calcsize(
            self.header['header_length'][0].fmt) + \
            self.header['header_length'][0].offset
        end_of_extension_area_len = 2 * UINT32_S
        free_space = self.cluster_size - max_header_len - \
                     end_of_extension_area_len
        # If the backing file name specified and there is enough space for it
        # in the first cluster, then it's placed in the very end of the first
        # cluster.
        if (backing_file_name is not None) and \
           (free_space >= len(backing_file_name)):
            self.header['backing_file_size'][0].value = len(backing_file_name)
            self.header['backing_file_offset'][0].value = \
                                    self.cluster_size - len(backing_file_name)

    def set_backing_file_name(self, backing_file_name=None):
        """Add the name of the backing file at the offset specified
        in the header.
        """
        if (backing_file_name is not None) and \
           (not self.header['backing_file_offset'][0].value == 0):
            data_len = len(backing_file_name)
            data_fmt = '>' + str(data_len) + 's'
            self.backing_file_name = FieldsList([
                [data_fmt, self.header['backing_file_offset'][0].value,
                 backing_file_name, 'bf_name']
            ])
        else:
            self.backing_file_name = FieldsList()

    def set_backing_file_format(self, backing_file_fmt=None):
        """Generate the header extension for the backing file
        format.
        """
        self.backing_file_format = FieldsList()
        offset = struct.calcsize(self.header['header_length'][0].fmt) + \
                 self.header['header_length'][0].offset

        if backing_file_fmt is not None:
            # Calculation of the free space available in the first cluster
            end_of_extension_area_len = 2 * UINT32_S
            high_border = (self.header['backing_file_offset'][0].value or
                           (self.cluster_size - 1)) - \
                end_of_extension_area_len
            free_space = high_border - offset
            ext_size = 2 * UINT32_S + ((len(backing_file_fmt) + 7) & ~7)

            if free_space >= ext_size:
                ext_data_len = len(backing_file_fmt)
                ext_data_fmt = '>' + str(ext_data_len) + 's'
                ext_padding_len = 7 - (ext_data_len - 1) % 8
                self.backing_file_format = FieldsList([
                    ['>I', offset, 0xE2792ACA, 'ext_magic'],
                    ['>I', offset + UINT32_S, ext_data_len, 'ext_length'],
                    [ext_data_fmt, offset + UINT32_S * 2, backing_file_fmt,
                     'bf_format']
                ])
                offset = self.backing_file_format['bf_format'][0].offset + \
                         struct.calcsize(self.backing_file_format[
                             'bf_format'][0].fmt) + ext_padding_len

        return offset

    def create_feature_name_table(self, offset):
        """Generate a random header extension for names of features used in
        the image.
        """
        def gen_feat_ids():
            """Return random feature type and feature bit."""
            return (random.randint(0, 2), random.randint(0, 63))

        end_of_extension_area_len = 2 * UINT32_S
        high_border = (self.header['backing_file_offset'][0].value or
                       (self.cluster_size - 1)) - \
            end_of_extension_area_len
        free_space = high_border - offset
        # Sum of sizes of 'magic' and 'length' header extension fields
        ext_header_len = 2 * UINT32_S
        fnt_entry_size = 6 * UINT64_S
        num_fnt_entries = min(10, (free_space - ext_header_len) /
                              fnt_entry_size)
        if not num_fnt_entries == 0:
            feature_tables = []
            feature_ids = []
            inner_offset = offset + ext_header_len
            feat_name = 'some cool feature'
            while len(feature_tables) < num_fnt_entries * 3:
                feat_type, feat_bit = gen_feat_ids()
                # Remove duplicates
                while (feat_type, feat_bit) in feature_ids:
                    feat_type, feat_bit = gen_feat_ids()
                feature_ids.append((feat_type, feat_bit))
                feat_fmt = '>' + str(len(feat_name)) + 's'
                feature_tables += [['B', inner_offset,
                                    feat_type, 'feature_type'],
                                   ['B', inner_offset + 1, feat_bit,
                                    'feature_bit_number'],
                                   [feat_fmt, inner_offset + 2,
                                    feat_name, 'feature_name']
                ]
                inner_offset += fnt_entry_size
            # No padding for the extension is necessary, because
            # the extension length is multiple of 8
            self.feature_name_table = FieldsList([
                ['>I', offset, 0x6803f857, 'ext_magic'],
                # One feature table contains 3 fields and takes 48 bytes
                ['>I', offset + UINT32_S, len(feature_tables) / 3 * 48,
                 'ext_length']
            ] + feature_tables)
            offset = inner_offset
        else:
            self.feature_name_table = FieldsList()

        return offset

    def set_end_of_extension_area(self, offset):
        """Generate a mandatory header extension marking end of header
        extensions.
        """
        self.end_of_extension_area = FieldsList([
            ['>I', offset, 0, 'ext_magic'],
            ['>I', offset + UINT32_S, 0, 'ext_length']
        ])

    def create_l2_tables(self, meta_data=None):
        """Generate random valid L2 tables."""
        def create_entry(accum, item):
            """Generate one L2 entry."""
            offset = item[0] * self.cluster_size
            for field in item[1]:
                entry_offset = offset + field[0] * UINT64_S
                cluster_descriptor = field[1] * self.cluster_size
                if not self.header['version'][0].value == 2:
                    cluster_descriptor += random.randint(0, 1)
                # While snapshots are not supported, bit #63 = 1
                # Compressed clusters are not supported => bit #62 = 0
                entry_val = (1 << 63) + cluster_descriptor
                accum.append(['>Q', entry_offset, entry_val, 'l2_entry'])
            return accum
        if len(self.data_clusters) == 0:
            self.l2_tables = FieldsList()
        else:
            if meta_data is None:
                v_meta_data = set([0])
            else:
                v_meta_data = set(meta_data)
            temp = list(self.data_clusters)
            random.shuffle(temp)
            l2_content = []
            # Number of entries in an L2 table
            l2_size = self.cluster_size / UINT64_S
            # Number of L2 tables having entries for all guest image clusters
            max_l2_size = ceil(UINT64_S * self.image_size /
                               float(self.cluster_size**2))
            low_lim = int(ceil(len(temp) / max_l2_size))
            # Binding of data clusters to L2 tables
            # Each table contains from low_lim to l2_size active entries
            while len(temp) > 0:
                num_of_entries = random.randint(low_lim, l2_size)
                if num_of_entries > len(temp):
                    num_of_entries = len(temp)
                entries, temp = temp[:num_of_entries], temp[num_of_entries:]
                entry_ids = random.sample(range(l2_size), num_of_entries)
                l2_content.append(zip(entry_ids, entries))

                l2_clusters = self._get_available_clusters(self.data_clusters |
                                                           v_meta_data,
                                                           len(l2_content))
            l2 = reduce(create_entry, zip(l2_clusters, l2_content), [])
            self.l2_tables = FieldsList(l2)

    def create_l1_table(self, meta_data=None):
        """Generate a random valid L1 table."""
        # Number of clusters used by L2 tables having entries for all
        # guest image clusters
        max_l2_size = int(ceil(UINT64_S * self.image_size /
                               float(self.cluster_size**2)))

        if len(self.data_clusters) == 0:
            # All metadata for an empty guest image needs 4 clusters:
            # header, rfc table, rfc block, L1 table.
            # Header takes cluster #0, other clusters ##1-3 can be used
            l1_offset = random.randint(1, 3) * self.cluster_size
            l1 = [['>Q', l1_offset, 0, 'l1_entry']]
        else:
            if meta_data is None:
                v_meta_data = set([0])
            else:
                v_meta_data = set(meta_data)
            l2_cluster_ids = set()
            for x in self.l2_tables:
                l2_cluster_ids.add(x.offset / self.cluster_size)
            v_meta_data |= l2_cluster_ids
            # Numbers of active L1 entries
            l1_entries_ids = random.sample(range(max_l2_size),
                                           len(l2_cluster_ids))
            # Number of clusters allocated by L1 table
            l1_size = int(ceil(UINT64_S * (max(l1_entries_ids) + 1) /
                               float(self.cluster_size)))
            l1_first_cluster_id = self._get_adjacent_clusters(
                self.data_clusters | v_meta_data, l1_size)
            l1_offset = l1_first_cluster_id * self.cluster_size
            l1 = []
            for f in zip(l1_entries_ids, l2_cluster_ids):
                entry_offset = l1_offset + UINT64_S * f[0]
                # While snapshots are not supported bit #63 = 1
                entry_val = (1 << 63) + f[1] * self.cluster_size
                l1.append(['>Q', entry_offset, entry_val, 'l1_entry'])

        self.l1_table = FieldsList(l1)
        self.header['l1_size'][0].value = max_l2_size
        self.header['l1_table_offset'][0].value = l1_offset

    def __init__(self, backing_file_name=None, backing_file_fmt=None):
        """Create a random valid qcow2 image with the correct inner structure
        and allowable values.
        """
        # Image size is saved as an attribute for the runner needs
        cluster_bits, self.image_size = self._size_params()
        # Saved as an attribute, because it's necessary for writing
        self.cluster_size = 1 << cluster_bits
        self.create_header(cluster_bits, backing_file_name)
        self.set_backing_file_name(backing_file_name)
        offset = self.set_backing_file_format(backing_file_fmt)
        offset = self.create_feature_name_table(offset)
        self.set_end_of_extension_area(offset)
        self.data_clusters = self._alloc_data(self.image_size,
                                              self.cluster_size)
        self.create_l2_tables()
        self.create_l1_table()
        # Container for entire image
        self.data = FieldsList()
        # Percentage of fields will be fuzzed
        self.bias = random.uniform(0.2, 0.5)

    def __iter__(self):
        return iter([self.header,
                     self.backing_file_format,
                     self.feature_name_table,
                     self.end_of_extension_area,
                     self.backing_file_name,
                     self.l1_table,
                     self.l2_tables])

    def _join(self):
        """Join all image structure elements as header, tables, etc in one
        list of fields.
        """
        if len(self.data) == 0:
            for v in self:
                self.data += v

    def fuzz(self, fields_to_fuzz=None):
        """Fuzz an image by corrupting values of a random subset of its fields.

        Without parameters the method fuzzes an entire image.
        If 'fields_to_fuzz' is specified then only fields in this list will be
        fuzzed. 'fields_to_fuzz' can contain both individual fields and more
        general image elements as a header or tables.
        In the first case the field will be fuzzed always.
        In the second a random subset of fields will be selected and fuzzed.
        """
        def coin():
            """Return boolean value proportional to a portion of fields to be
            fuzzed.
            """
            return random.random() < self.bias

        if fields_to_fuzz is None:
            self._join()
            for field in self.data:
                if coin():
                    field.value = getattr(fuzz, field.name)(field.value)
        else:
            for item in fields_to_fuzz:
                if len(item) == 1:
                    for field in getattr(self, item[0]):
                        if coin():
                            field.value = getattr(fuzz,
                                                  field.name)(field.value)
                else:
                    for field in getattr(self, item[0])[item[1]]:
                        try:
                            field.value = getattr(fuzz, field.name)(
                                field.value)
                        except AttributeError:
                            # Some fields can be skipped depending on
                            # references, e.g. FNT header extension is not
                            # generated for a feature mask header field
                            # equal to zero
                            pass

    def write(self, filename):
        """Write an entire image to the file."""
        image_file = open(filename, 'w')
        self._join()
        for field in self.data:
            image_file.seek(field.offset)
            image_file.write(struct.pack(field.fmt, field.value))
        image_file.seek(0, 2)
        # Align the real image size to the cluster size
        size = image_file.tell()
        rounded = (size + self.cluster_size - 1) & ~(self.cluster_size - 1)
        if rounded > size:
            image_file.seek(rounded - 1)
            image_file.write("\0")
        image_file.close()


def create_image(test_img_path, backing_file_name=None, backing_file_fmt=None,
                 fields_to_fuzz=None):
    """Create a fuzzed image and write it to the specified file."""
    image = Image(backing_file_name, backing_file_fmt)
    image.fuzz(fields_to_fuzz)
    image.write(test_img_path)
    return image.image_size
