"""Generator of fuzzed qcow2 images"""
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
    return [field[0:2] + [getattr(fuzz, field[3])(field[2])] + field[-1:]
            if field in extract else field for field in structure]


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
        [64, '>Q', snapshots_offset, 'snapshots_offset']
    ]


def create_image(v_file):
    """Write a fuzzed image to the specified file"""
    image_file = open(v_file, 'w')
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
